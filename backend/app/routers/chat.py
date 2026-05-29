import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.db.models.chat_message import ChatMessage
from app.db.models.chat_session import ChatSession
from app.db.models.collection_permission import CollectionPermission
from app.db.models.document import PGDocument
from app.db.models.document_version import DocumentVersion
from app.db.models.rag_document import RagDocument
from app.db.models.role_document_permission import RoleDocumentPermission
from app.db.models.user import PGUser
from app.db.models.user_collection_permission import UserCollectionPermission
from app.db.models.user_document_permission import UserDocumentPermission
from app.db.session import PGAsyncSessionLocal as AsyncSessionLocal, get_pg_db
from app.config import settings
from app.dependencies import get_current_user
from app.schemas import ChatRequest
from app.cache import response_cache
from app.services import rag
from app.services.chat_access import check_collection_access, check_doc_access

logger = logging.getLogger(__name__)


def _perf_log(msg: str, *args) -> None:
    if settings.chat_perf_logging:
        logger.info("[chat-perf] " + msg, *args)


router = APIRouter(prefix="/api", tags=["chat"])


# ── Permission resolution (first-message expansion) ───────────────────────────

async def _resolve_allowed_docs(
    user: PGUser,
    request: ChatRequest,
    db: AsyncSession,
) -> list[str]:
    """
    Expands the user's collection/document selection into a validated list of
    doc_id strings for the first message of a new session.
    Always returns a list (never None).
    """
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


# ── Session persistence helpers ────────────────────────────────────────────────

async def _get_history(session_id: str) -> list[dict]:
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == uuid.UUID(session_id))
            .order_by(ChatMessage.created_at.asc())
        )
        rows = result.scalars().all()
        return [{"role": r.role, "content": r.content} for r in rows]


async def _save_turn(
    session_id: str, role: str, content: str, sources_json: str | None = None
) -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db_session:
        msg = ChatMessage(
            session_id=uuid.UUID(session_id),
            role=role,
            content=content,
            sources_json=sources_json,
        )
        db_session.add(msg)
        await db_session.execute(
            update(ChatSession)
            .where(ChatSession.id == uuid.UUID(session_id))
            .values(updated_at=now)
        )
        await db_session.commit()


# ── Chat endpoint ──────────────────────────────────────────────────────────────

@router.post("/chat")
async def chat(
    request: ChatRequest,
    current_user: PGUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_pg_db),
):
    session_id: str

    if request.session_id is not None:
        # --- Existing session: validate ownership and re-check all docs ---
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

        allowed_doc_ids: list[str] | None = (
            [str(d) for d in session.document_ids] if session.document_ids else None
        )
        session_id = str(session.id)

    else:
        # --- New session: resolve scope and create session row ---
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

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            t_total = time.perf_counter()

            t0 = time.perf_counter()
            history = await _get_history(session_id)
            _perf_log("history(db): %.3fs", time.perf_counter() - t0)

            t0 = time.perf_counter()
            await _save_turn(session_id, "user", request.message)
            _perf_log("save-user(db): %.3fs", time.perf_counter() - t0)

            t0 = time.perf_counter()
            cached = await asyncio.to_thread(response_cache.get, request.message)
            _perf_log(
                "cache lookup: %.3fs (%s)",
                time.perf_counter() - t0, "HIT" if cached is not None else "MISS",
            )
            if cached is not None:
                cached_text, cached_sources = cached
                await _save_turn(
                    session_id, "assistant", cached_text, json.dumps(cached_sources)
                )
                _perf_log(
                    "TOTAL chat (cache hit): %.3fs",
                    time.perf_counter() - t_total,
                )
                yield {"data": json.dumps({"type": "token", "content": cached_text})}
                yield {
                    "data": json.dumps({
                        "type": "done",
                        "session_id": session_id,
                        "sources": cached_sources,
                        "from_cache": True,
                    })
                }
                return

            text_contexts, image_sources = await rag.build_context(
                request.message,
                allowed_doc_ids,
                history=history,
            )

            full_response = ""
            final_sources = None

            async for token, sources in rag.stream_chat(
                message=request.message,
                text_contexts=text_contexts,
                image_sources=image_sources,
                history=history,
            ):
                if sources is not None:
                    final_sources = sources
                elif token:
                    full_response += token
                    yield {"data": json.dumps({"type": "token", "content": token})}

            sources_data = (
                [s.model_dump() for s in final_sources] if final_sources else []
            )
            t0 = time.perf_counter()
            await _save_turn(
                session_id,
                "assistant",
                full_response,
                json.dumps(sources_data),
            )
            _perf_log("save-assistant(db): %.3fs", time.perf_counter() - t0)

            if full_response and sources_data:
                await asyncio.to_thread(
                    response_cache.set, request.message, full_response, sources_data
                )

            _perf_log("TOTAL chat: %.3fs", time.perf_counter() - t_total)

            yield {
                "data": json.dumps({
                    "type": "done",
                    "session_id": session_id,
                    "sources": sources_data,
                    "from_cache": False,
                })
            }

        except Exception as exc:
            logger.error("Chat stream error: %s", exc)
            yield {"data": json.dumps({"type": "error", "message": str(exc)})}

    return EventSourceResponse(event_generator())
