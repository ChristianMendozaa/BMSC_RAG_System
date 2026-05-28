import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat_message import ChatMessage
from app.db.models.chat_session import ChatSession
from app.db.models.document import PGDocument
from app.db.models.user import PGUser
from app.db.session import get_pg_db
from app.dependencies import get_current_user
from app.schemas import BlockerItem, ChatMessageOut, ChatSessionDetail, ChatSessionListItem, ResumeCheckOut
from app.services.chat_access import check_collection_access, check_doc_access

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


async def _get_session_or_404(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> ChatSession:
    res = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
    )
    session = res.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    return session


@router.get("", response_model=list[ChatSessionListItem])
async def list_conversations(
    current_user: PGUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_pg_db),
):
    res = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(100)
    )
    sessions = res.scalars().all()

    return [
        ChatSessionListItem(
            id=s.id,
            title=s.title,
            collection_id=s.collection_id,
            document_ids=s.document_ids,
            updated_at=s.updated_at,
            document_count=len(s.document_ids or []),
        )
        for s in sessions
    ]


@router.get("/{session_id}", response_model=ChatSessionDetail)
async def get_conversation(
    session_id: uuid.UUID,
    current_user: PGUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_pg_db),
):
    session = await _get_session_or_404(session_id, current_user.id, db)

    msgs_res = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = msgs_res.scalars().all()

    msg_out = []
    for m in messages:
        sources: list = []
        if m.sources_json:
            try:
                sources = json.loads(m.sources_json)
            except Exception:
                sources = []
        msg_out.append(
            ChatMessageOut(id=m.id, role=m.role, content=m.content, sources=sources)
        )

    return ChatSessionDetail(
        id=session.id,
        title=session.title,
        collection_id=session.collection_id,
        document_ids=session.document_ids,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=msg_out,
    )


@router.post("/{session_id}/resume-check", response_model=ResumeCheckOut)
async def resume_check(
    session_id: uuid.UUID,
    current_user: PGUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_pg_db),
):
    session = await _get_session_or_404(session_id, current_user.id, db)

    doc_uuids = [uuid.UUID(str(d)) for d in (session.document_ids or [])]
    access_map = await check_doc_access(db, current_user, doc_uuids, require_ready=True)

    # Fetch current titles for docs that still exist (for user-facing messages)
    existing_ids = [k for k, v in access_map.items() if v != "doc_hard_deleted"]
    titles_by_id: dict[uuid.UUID, str] = {}
    if existing_ids:
        docs_res = await db.execute(
            select(PGDocument).where(PGDocument.id.in_(existing_ids))
        )
        for d in docs_res.scalars():
            titles_by_id[d.id] = d.title

    blockers: list[BlockerItem] = []

    # Check collection first
    if session.collection_id is not None:
        col_blocker = await check_collection_access(db, session.collection_id)
        if col_blocker:
            blockers.append(BlockerItem(doc_id=None, doc_title_snapshot="", reason=col_blocker))

    # Check each doc
    for doc_id, reason in access_map.items():
        if reason is not None:
            title = titles_by_id.get(doc_id, str(doc_id))
            blockers.append(BlockerItem(doc_id=str(doc_id), doc_title_snapshot=title, reason=reason))

    return ResumeCheckOut(
        can_resume=len(blockers) == 0,
        blockers=blockers,
        collection_id=str(session.collection_id) if session.collection_id else None,
        document_ids=[str(d) for d in (session.document_ids or [])],
    )


@router.delete("/{session_id}", status_code=204)
async def delete_conversation(
    session_id: uuid.UUID,
    current_user: PGUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_pg_db),
):
    session = await _get_session_or_404(session_id, current_user.id, db)
    await db.delete(session)
    await db.commit()
