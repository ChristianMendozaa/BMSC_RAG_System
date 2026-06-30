import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.db.models.chat_session import ChatSession
from app.db.models.collection_permission import CollectionPermission
from app.db.models.document import PGDocument
from app.db.models.document_version import DocumentVersion
from app.db.models.rag_document import RagDocument
from app.db.models.role_document_permission import RoleDocumentPermission
from app.db.models.user import PGUser
from app.db.models.user_collection_permission import UserCollectionPermission
from app.db.models.user_document_permission import UserDocumentPermission
from app.db.session import get_pg_db
from app.dependencies import get_current_user
from app.schemas import ChatRequest
from app.services import chat_runner
from app.services.chat_access import check_collection_access, check_doc_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


# ── Permission resolution (first-message expansion) ───────────────────────────

async def _resolve_allowed_docs(
    user: PGUser,
    request: ChatRequest,
    db: AsyncSession,
) -> list[str]:
    is_admin = user.role.can_manage_collections

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

    if request.document_ids:
        doc_uuids = [uuid.UUID(d) for d in request.document_ids]
        docs_res = await db.execute(
            select(PGDocument, RagDocument)
            .join(
                RagDocument,
                and_(
                    RagDocument.id == PGDocument.id,
                    RagDocument.status == "ready",
                ),
            )
            .where(
                PGDocument.id.in_(doc_uuids),
                PGDocument.status == "ACTIVE",
            )
        )
        return [str(doc.id) for doc, _ in docs_res.all() if _can_chat(doc.id, doc.collection_id)]

    if request.collection_id:
        col_uuid = uuid.UUID(request.collection_id)

        if is_admin:
            docs_res = await db.execute(
                select(PGDocument).where(
                    PGDocument.collection_id == col_uuid,
                    PGDocument.status == "ACTIVE",
                )
            )
            return [str(d.id) for d in docs_res.scalars()]

        docs_res = await db.execute(
            select(PGDocument, DocumentVersion)
            .join(
                DocumentVersion,
                and_(
                    DocumentVersion.document_id == PGDocument.id,
                    DocumentVersion.is_current == True,  # noqa: E712
                    DocumentVersion.index_status == "READY",
                ),
            )
            .where(PGDocument.collection_id == col_uuid, PGDocument.status == "ACTIVE")
        )
        return [
            str(doc.id)
            for doc, _ in docs_res.all()
            if _can_chat(doc.id, col_uuid)
        ]

    return []


# ── Subscriber SSE helper ──────────────────────────────────────────────────────

def _make_subscriber_generator(
    gen: chat_runner.ActiveGeneration,
    session_id: str,
) -> AsyncGenerator[dict, None]:
    async def _generator() -> AsyncGenerator[dict, None]:
        q = await chat_runner.subscribe(gen)
        try:
            yield {"data": json.dumps({"type": "session", "session_id": session_id})}
            while True:
                item = await q.get()
                if item is None:
                    break
                yield {"data": item}
                payload = json.loads(item)
                if payload.get("type") in ("done", "stopped", "error"):
                    break
        finally:
            chat_runner.unsubscribe(gen, q)

    return _generator()


# ── Chat endpoint ──────────────────────────────────────────────────────────────

@router.post("/chat")
async def chat(
    request: ChatRequest,
    current_user: PGUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_pg_db),
):
    session_id: str

    if request.session_id is not None:
        try:
            sid = uuid.UUID(request.session_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="session_id inválido")

        sess_res = await db.execute(
            select(ChatSession).where(
                ChatSession.id == sid,
                ChatSession.user_id == current_user.id,
            )
        )
        session = sess_res.scalar_one_or_none()
        if session is None:
            raise HTTPException(status_code=404, detail="Sesión no encontrada")

        doc_uuids = [uuid.UUID(str(d)) for d in (session.document_ids or [])]
        if doc_uuids:
            access_map = await check_doc_access(db, current_user, doc_uuids, require_ready=True)
            blockers = [
                {"doc_id": str(k), "reason": v}
                for k, v in access_map.items()
                if v is not None
            ]
            if blockers:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "session_invalid", "blockers": blockers},
                )

        if session.collection_id is not None:
            col_blocker = await check_collection_access(db, session.collection_id)
            if col_blocker:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "session_invalid", "blockers": [{"reason": col_blocker}]},
                )

        allowed_doc_ids: list[str] = (
            [str(d) for d in session.document_ids] if session.document_ids else []
        )
        session_id = str(session.id)

    else:
        allowed_doc_ids = await _resolve_allowed_docs(current_user, request, db)

        if len(allowed_doc_ids) == 0:
            raise HTTPException(
                status_code=403,
                detail="No tienes acceso a ningún documento en el scope seleccionado",
            )

        title = request.message[:60] + ("…" if len(request.message) > 60 else "")
        session = ChatSession(
            user_id=current_user.id,
            title=title,
            collection_id=uuid.UUID(request.collection_id) if request.collection_id else None,
            document_ids=[uuid.UUID(d) for d in allowed_doc_ids],
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        session_id = str(session.id)

    if chat_runner.is_running(session_id):
        raise HTTPException(status_code=409, detail="Ya hay una generación en curso para esta sesión")

    gen = chat_runner.start(session_id, request.message, allowed_doc_ids)
    return EventSourceResponse(_make_subscriber_generator(gen, session_id))


# ── Stop endpoint ──────────────────────────────────────────────────────────────

@router.post("/chat/{session_id}/stop")
async def stop_generation(
    session_id: str,
    current_user: PGUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_pg_db),
):
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="session_id inválido")

    sess_res = await db.execute(
        select(ChatSession).where(
            ChatSession.id == sid,
            ChatSession.user_id == current_user.id,
        )
    )
    if sess_res.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    chat_runner.request_stop(session_id)
    return {"stopped": True}


# ── Active generation status endpoint ─────────────────────────────────────────

@router.get("/chat/{session_id}/active")
async def get_active_generation(
    session_id: str,
    current_user: PGUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_pg_db),
):
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="session_id inválido")

    sess_res = await db.execute(
        select(ChatSession).where(
            ChatSession.id == sid,
            ChatSession.user_id == current_user.id,
        )
    )
    if sess_res.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    gen = chat_runner.get(session_id)
    if gen is None:
        return {"active": False, "status": "idle", "text": ""}

    return {
        "active": gen.status == "running",
        "status": gen.status,
        "stage": gen.stage,
        "stage_message": gen.stage_message,
        "text": gen.text,
    }


# ── Re-subscribe stream endpoint ──────────────────────────────────────────────

@router.get("/chat/{session_id}/stream")
async def resume_stream(
    session_id: str,
    current_user: PGUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_pg_db),
):
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="session_id inválido")

    sess_res = await db.execute(
        select(ChatSession).where(
            ChatSession.id == sid,
            ChatSession.user_id == current_user.id,
        )
    )
    if sess_res.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    gen = chat_runner.get(session_id)
    if gen is None:
        raise HTTPException(status_code=404, detail="No hay generación activa para esta sesión")

    return EventSourceResponse(_make_subscriber_generator(gen, session_id))
