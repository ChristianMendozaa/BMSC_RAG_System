import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.db.models.collection_permission import CollectionPermission
from app.db.models.document import PGDocument
from app.db.models.document_version import DocumentVersion
from app.db.models.rag_conversation import RagConversation as Conversation
from app.db.models.role_document_permission import RoleDocumentPermission
from app.db.models.user import PGUser
from app.db.models.user_collection_permission import UserCollectionPermission
from app.db.models.user_document_permission import UserDocumentPermission
from app.db.session import PGAsyncSessionLocal as AsyncSessionLocal, get_pg_db
from app.dependencies import get_current_user
from app.schemas import ChatRequest
from app.cache import response_cache
from app.services import rag

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


# ── Permission resolution helpers ─────────────────────────────────────────────

async def _resolve_allowed_docs(
    user: PGUser,
    request: ChatRequest,
    db: AsyncSession,
) -> list[str] | None:
    """
    Devuelve la lista de doc_id strings que el usuario puede consultar en el chat.
    Retorna None si el usuario tiene acceso irrestricto (admins con can_manage_collections).
    """
    if user.role.can_manage_collections:
        return request.document_ids

    udp_res = await db.execute(
        select(UserDocumentPermission).where(UserDocumentPermission.user_id == user.id)
    )
    udp_map: dict[uuid.UUID, bool] = {p.document_id: p.can_chat for p in udp_res.scalars()}

    rdp_res = await db.execute(
        select(RoleDocumentPermission).where(RoleDocumentPermission.role_id == user.role_id)
    )
    rdp_map: dict[uuid.UUID, bool] = {p.document_id: p.can_chat for p in rdp_res.scalars()}

    ucp_res = await db.execute(
        select(UserCollectionPermission).where(UserCollectionPermission.user_id == user.id)
    )
    ucp_map: dict[uuid.UUID, bool] = {p.collection_id: p.can_chat for p in ucp_res.scalars()}

    cp_res = await db.execute(
        select(CollectionPermission).where(CollectionPermission.role_id == user.role_id)
    )
    cp_map: dict[uuid.UUID, bool] = {p.collection_id: p.can_chat for p in cp_res.scalars()}

    def _can_chat(doc_id: uuid.UUID, col_id: uuid.UUID) -> bool:
        if doc_id in udp_map:
            return udp_map[doc_id]
        if doc_id in rdp_map:
            return rdp_map[doc_id]
        if col_id in ucp_map:
            return ucp_map[col_id]
        if col_id in cp_map:
            return cp_map[col_id]
        return False

    if request.document_ids:
        doc_uuids = [uuid.UUID(d) for d in request.document_ids]
        docs_res = await db.execute(
            select(PGDocument).where(PGDocument.id.in_(doc_uuids), PGDocument.status == "ACTIVE")
        )
        docs = docs_res.scalars().all()
        return [str(d.id) for d in docs if _can_chat(d.id, d.collection_id)]

    if request.collection_id:
        col_uuid = uuid.UUID(request.collection_id)
        docs_res = await db.execute(
            select(PGDocument, DocumentVersion)
            .join(
                DocumentVersion,
                and_(
                    DocumentVersion.document_id == PGDocument.id,
                    DocumentVersion.is_current == True,
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


# ── Conversation persistence ───────────────────────────────────────────────────

async def _get_history(conversation_id: str) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Conversation)
            .where(Conversation.conversation_id == conversation_id)
            .order_by(Conversation.created_at.asc())
        )
        rows = result.scalars().all()
        return [{"role": r.role, "content": r.content} for r in rows]


async def _save_turn(
    conversation_id: str, role: str, content: str, sources_json: str | None = None
) -> None:
    async with AsyncSessionLocal() as session:
        turn = Conversation(
            conversation_id=conversation_id,
            role=role,
            content=content,
            sources_json=sources_json,
        )
        session.add(turn)
        await session.commit()


# ── Chat endpoint ──────────────────────────────────────────────────────────────

@router.post("/chat")
async def chat(
    request: ChatRequest,
    current_user: PGUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_pg_db),
):
    allowed_doc_ids = await _resolve_allowed_docs(current_user, request, db)

    if allowed_doc_ids is not None and len(allowed_doc_ids) == 0:
        raise HTTPException(
            status_code=403,
            detail="No tienes acceso a ningún documento en el scope seleccionado",
        )

    conversation_id = request.conversation_id or str(uuid.uuid4())

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            history = await _get_history(conversation_id)
            await _save_turn(conversation_id, "user", request.message)

            cached = await asyncio.to_thread(response_cache.get, request.message)
            if cached is not None:
                cached_text, cached_sources = cached
                await _save_turn(
                    conversation_id, "assistant", cached_text, json.dumps(cached_sources)
                )
                yield {"data": json.dumps({"type": "token", "content": cached_text})}
                yield {
                    "data": json.dumps({
                        "type": "done",
                        "conversation_id": conversation_id,
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
            await _save_turn(
                conversation_id,
                "assistant",
                full_response,
                json.dumps(sources_data),
            )

            if full_response and sources_data:
                await asyncio.to_thread(
                    response_cache.set, request.message, full_response, sources_data
                )

            yield {
                "data": json.dumps({
                    "type": "done",
                    "conversation_id": conversation_id,
                    "sources": sources_data,
                    "from_cache": False,
                })
            }

        except Exception as exc:
            logger.error("Chat stream error: %s", exc)
            yield {"data": json.dumps({"type": "error", "message": str(exc)})}

    return EventSourceResponse(event_generator())


@router.get("/chat/history/{conversation_id}")
async def get_conversation_history(
    conversation_id: str,
    _: PGUser = Depends(get_current_user),
) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Conversation)
            .where(Conversation.conversation_id == conversation_id)
            .order_by(Conversation.created_at.asc())
        )
        rows = result.scalars().all()

    turns = []
    for r in rows:
        sources: list = []
        if r.sources_json:
            try:
                sources = json.loads(r.sources_json)
            except Exception:
                sources = []
        turns.append({"role": r.role, "content": r.content, "sources": sources})
    return turns
