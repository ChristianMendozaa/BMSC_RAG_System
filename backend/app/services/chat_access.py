"""
Shared permission + readiness validation for chat sessions.

check_doc_access()  — validates a list of doc_ids against current state.
check_collection_access() — validates a collection_id against current state.

Both return blocker codes (strings) or None for "all clear".
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.collection import Collection
from app.db.models.collection_permission import CollectionPermission
from app.db.models.document import PGDocument
from app.db.models.rag_document import RagDocument
from app.db.models.role_document_permission import RoleDocumentPermission
from app.db.models.user import PGUser
from app.db.models.user_collection_permission import UserCollectionPermission
from app.db.models.user_document_permission import UserDocumentPermission


async def check_doc_access(
    db: AsyncSession,
    user: PGUser,
    doc_ids: list[uuid.UUID],
    *,
    require_ready: bool = True,
) -> dict[uuid.UUID, str | None]:
    """
    Returns {doc_id: blocker_code | None}.
    None = document is fully chateable by this user right now.

    Blocker codes: doc_hard_deleted | doc_obsolete | doc_not_ready | doc_no_access
    """
    if not doc_ids:
        return {}

    is_admin = user.role is not None and user.role.can_manage_collections

    # Load permission maps (non-admins only)
    udp_map: dict[uuid.UUID, bool] = {}
    rdp_map: dict[uuid.UUID, bool] = {}
    ucp_map: dict[uuid.UUID, bool] = {}
    cp_map: dict[uuid.UUID, bool] = {}

    if not is_admin:
        udp_res = await db.execute(
            select(UserDocumentPermission).where(UserDocumentPermission.user_id == user.id)
        )
        udp_map = {p.document_id: p.can_chat for p in udp_res.scalars()}

        rdp_res = await db.execute(
            select(RoleDocumentPermission).where(RoleDocumentPermission.role_id == user.role_id)
        )
        rdp_map = {p.document_id: p.can_chat for p in rdp_res.scalars()}

        ucp_res = await db.execute(
            select(UserCollectionPermission).where(UserCollectionPermission.user_id == user.id)
        )
        ucp_map = {p.collection_id: p.can_chat for p in ucp_res.scalars()}

        cp_res = await db.execute(
            select(CollectionPermission).where(CollectionPermission.role_id == user.role_id)
        )
        cp_map = {p.collection_id: p.can_chat for p in cp_res.scalars()}

    def _can_chat(doc_id: uuid.UUID, col_id: uuid.UUID | None) -> bool:
        if is_admin:
            return True
        if doc_id in udp_map:
            return udp_map[doc_id]
        if doc_id in rdp_map:
            return rdp_map[doc_id]
        if col_id is not None:
            if col_id in ucp_map:
                return ucp_map[col_id]
            if col_id in cp_map:
                return cp_map[col_id]
        return False

    # Fetch PGDocument rows
    docs_res = await db.execute(
        select(PGDocument).where(PGDocument.id.in_(doc_ids))
    )
    docs_by_id: dict[uuid.UUID, PGDocument] = {d.id: d for d in docs_res.scalars()}

    # Fetch RagDocument rows (single source of truth for indexing readiness)
    rag_docs_by_id: dict[uuid.UUID, RagDocument] = {}
    if require_ready:
        rag_res = await db.execute(
            select(RagDocument).where(RagDocument.id.in_(doc_ids))
        )
        rag_docs_by_id = {r.id: r for r in rag_res.scalars()}

    results: dict[uuid.UUID, str | None] = {}

    for doc_id in doc_ids:
        if doc_id not in docs_by_id:
            results[doc_id] = "doc_hard_deleted"
            continue

        doc = docs_by_id[doc_id]

        if doc.status != "ACTIVE":
            results[doc_id] = "doc_obsolete"
            continue

        if require_ready:
            rag = rag_docs_by_id.get(doc_id)
            if rag is None or rag.status != "ready" or rag.chunk_count == 0:
                results[doc_id] = "doc_not_ready"
                continue

        if not _can_chat(doc_id, doc.collection_id):
            results[doc_id] = "doc_no_access"
            continue

        results[doc_id] = None

    return results


async def check_collection_access(
    db: AsyncSession,
    collection_id: uuid.UUID | None,
) -> str | None:
    """
    Returns blocker_code for the collection, or None if OK / not set.
    Blocker codes: collection_gone | collection_inactive
    """
    if collection_id is None:
        return None
    col_res = await db.execute(
        select(Collection).where(Collection.id == collection_id)
    )
    col = col_res.scalar_one_or_none()
    if col is None:
        return "collection_gone"
    if not col.is_active:
        return "collection_inactive"
    return None
