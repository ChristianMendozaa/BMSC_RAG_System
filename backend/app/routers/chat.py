import json
import logging
import re
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.database import AsyncSessionLocal, get_db
from app.models import Conversation, Document, DocumentFigure, DocumentImage
from app.schemas import ChatRequest
from app.services import file_storage, rag
from app.config import settings as cfg

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


async def _get_history(conversation_id: str) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Conversation)
            .where(Conversation.conversation_id == conversation_id)
            .order_by(Conversation.created_at.asc())
        )
        rows = result.scalars().all()
        return [{"role": r.role, "content": r.content} for r in rows]


async def _save_turn(conversation_id: str, role: str, content: str, sources_json: str | None = None) -> None:
    async with AsyncSessionLocal() as session:
        turn = Conversation(
            conversation_id=conversation_id,
            role=role,
            content=content,
            sources_json=sources_json,
        )
        session.add(turn)
        await session.commit()


# ── Regex patterns for mention-based page / figure extraction ─────────────
_PAGE_PATTERNS = [
    re.compile(r'\bpáginas?\s+(\d+)', re.IGNORECASE),   # "página 84"
    re.compile(r'\bp[aá]g\.?\s*(\d+)', re.IGNORECASE),  # "pág. 84" / "p.84"
    re.compile(r'\bpage\s+(\d+)', re.IGNORECASE),        # "page 84"
]
# Generic figure/diagram/table reference: "Figura 22", "Diagrama 3", "Tabla 7"
_FIG_REF = re.compile(
    r'\b(?:Figura|Fig\.?|Diagrama|Tabla|Imagen|Esquema)\s+(\d+)',
    re.IGNORECASE,
)


def _extract_mentioned_pages(text_contexts: list[dict]) -> set[int]:
    pages: set[int] = set()
    for ctx in text_contexts:
        content = ctx.get("content", "")
        for pat in _PAGE_PATTERNS:
            for m in pat.finditer(content):
                pages.add(int(m.group(1)))
    return pages


async def _pages_from_figure_refs(text_contexts: list[dict]) -> set[int]:
    """Resolve generic figure/diagram/table references to page numbers."""
    doc_id_set = {ctx["doc_id"] for ctx in text_contexts if ctx.get("doc_id")}
    fig_nums: set[int] = set()
    for ctx in text_contexts:
        for m in _FIG_REF.finditer(ctx.get("content", "")):
            fig_nums.add(int(m.group(1)))
    if not doc_id_set or not fig_nums:
        return set()
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DocumentFigure.page_number)
            .where(DocumentFigure.document_id.in_(list(doc_id_set)))
            .where(DocumentFigure.figure_number.in_(list(fig_nums)))
        )
        return {r for (r,) in result.all() if r}


async def _images_for_text_pages(text_contexts: list[dict]) -> list[dict]:
    """Cross-modal boost: fetch images on pages near matching text chunks.

    These boosts are merged with vector-search results in the chat handler;
    they are NOT a substitute for proper retrieval. The score returned is
    derived from the originating text-chunk's score (multiplied by 0.9 since
    the link is positional, not semantic).
    """
    doc_id_set = {ctx["doc_id"] for ctx in text_contexts if ctx.get("doc_id")}
    if not doc_id_set:
        return []

    # Build a page → originating-score map so each image inherits a real,
    # non-hardcoded score derived from the text hit that anchors it.
    page_score: dict[tuple[str, int], float] = {}
    for ctx in text_contexts:
        doc_id = ctx.get("doc_id")
        page = ctx.get("page")
        score = ctx.get("score", 0.0)
        if not doc_id or not page:
            continue
        for p in (page - 1, page, page + 1):
            key = (doc_id, p)
            if score > page_score.get(key, 0.0):
                page_score[key] = score

    # Pages explicitly named in the text ("página 84")
    for page in _extract_mentioned_pages(text_contexts):
        for doc_id in doc_id_set:
            key = (doc_id, page)
            page_score.setdefault(key, 0.75)

    # Pages resolved via the figure-page index ("Figura 22" → p.84, etc.)
    fig_pages = await _pages_from_figure_refs(text_contexts)
    for page in fig_pages:
        for doc_id in doc_id_set:
            key = (doc_id, page)
            page_score.setdefault(key, 0.88)

    if not page_score:
        return []

    page_set = {p for _, p in page_score.keys()}
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DocumentImage, Document.original_filename)
            .join(Document, Document.id == DocumentImage.document_id)
            .where(DocumentImage.document_id.in_(list(doc_id_set)))
            .where(DocumentImage.page_number.in_(list(page_set)))
        )
        rows = result.all()

    return [
        {
            "image_id": img.id,
            "doc_id": img.document_id,
            "filename": filename,
            "page": img.page_number,
            "content": img.description or "",
            # Inherit the score from the text hit anchoring this image.
            # Capped at 0.92 so strong semantic image results can still win.
            "score": min(page_score.get((img.document_id, img.page_number), 0.50), 0.92),
        }
        for img, filename in rows
    ]


async def _load_image_bytes(image_contexts: list[dict]) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for ctx in image_contexts:
        image_id = ctx.get("image_id", "")
        if not image_id:
            continue
        try:
            async with AsyncSessionLocal() as session:
                img_result = await session.execute(
                    select(DocumentImage).where(DocumentImage.id == image_id)
                )
                img = img_result.scalar_one_or_none()
                if img:
                    data = await file_storage.get_object_bytes(
                        cfg.minio_bucket_images, img.minio_path
                    )
                    result[image_id] = data
        except Exception as exc:
            logger.warning("Failed to load image %s for RAG: %s", image_id, exc)
    return result


@router.post("/chat")
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    conversation_id = request.conversation_id or str(uuid.uuid4())

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            history = await _get_history(conversation_id)
            await _save_turn(conversation_id, "user", request.message)

            text_contexts, image_contexts = await rag.build_context(
                request.message,
                request.document_ids,
                history=history,
            )

            # Cross-modal positional boost: images sitting on the same pages as
            # matching text chunks. Merge by image_id, keeping the best score
            # so RAG-retrieved images and positional-boost images compete fairly.
            page_images = await _images_for_text_pages(text_contexts)
            if page_images:
                by_id: dict[str, dict] = {}
                for ctx in image_contexts + page_images:
                    img_id = ctx.get("image_id")
                    if not img_id:
                        continue
                    existing = by_id.get(img_id)
                    if existing is None or ctx["score"] > existing["score"]:
                        by_id[img_id] = ctx
                merged = sorted(by_id.values(), key=lambda c: c["score"], reverse=True)
                visual_mode = rag._is_visual_query(request.message)
                cap = cfg.visual_query_max_images if visual_mode else cfg.max_context_images
                image_contexts = merged[:cap]

            image_bytes_map = await _load_image_bytes(image_contexts)

            full_response = ""
            final_sources = None

            async for token, sources in rag.stream_chat(
                message=request.message,
                text_contexts=text_contexts,
                image_contexts=image_contexts,
                history=history,
                image_bytes_map=image_bytes_map,
            ):
                if sources is not None:
                    final_sources = sources
                elif token:
                    full_response += token
                    yield {
                        "data": json.dumps({"type": "token", "content": token})
                    }

            sources_data = (
                [s.model_dump() for s in final_sources] if final_sources else []
            )
            await _save_turn(
                conversation_id,
                "assistant",
                full_response,
                json.dumps(sources_data),
            )

            yield {
                "data": json.dumps({
                    "type": "done",
                    "conversation_id": conversation_id,
                    "sources": sources_data,
                })
            }

        except Exception as exc:
            logger.error("Chat stream error: %s", exc)
            yield {
                "data": json.dumps({"type": "error", "message": str(exc)})
            }

    return EventSourceResponse(event_generator())


@router.get("/chat/history/{conversation_id}")
async def get_conversation_history(conversation_id: str) -> list[dict]:
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
