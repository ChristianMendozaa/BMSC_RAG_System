import asyncio
import logging
import uuid
from typing import AsyncGenerator

from sqlalchemy import select

from app.config import settings
from app.schemas import Source
from app.services import embedder, vector_store
from app.services import reranker as reranker_svc
from app.utils.model_manager import get_chat_llm
from app.utils.inference_queue import inference_queue

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_BASE = """Eres un asistente experto del banco. Tu función es ayudar a los empleados
a consultar la documentación interna del banco de manera precisa y útil.

Directrices:
- Responde siempre en español, de manera clara y profesional.
- Basa tus respuestas exclusivamente en el contexto proporcionado.
- Si la información no está en el contexto, indícalo claramente.
- Cita las fuentes cuando sea relevante (nombre del documento y página).
- Para procedimientos, usa listas numeradas. Para información general, usa párrafos.
- Nunca inventes información que no esté en los documentos proporcionados.
- El contexto puede incluir fragmentos de texto y descripciones textuales de figuras, tablas o
  diagramas extraídas de los documentos. Úsalas para responder preguntas sobre contenido visual."""

SYSTEM_PROMPT = (
    "/no_think\n" if settings.qwen_disable_thinking else ""
) + _SYSTEM_PROMPT_BASE


async def _fetch_image_descriptions(
    doc_page_pairs: set[tuple[str, int]],
) -> list[dict]:
    """Recupera descripciones de document_images para las páginas de los chunks recuperados."""
    if not doc_page_pairs:
        return []

    from app.db.session import PGAsyncSessionLocal as AsyncSessionLocal
    from app.db.models.rag_document_image import RagDocumentImage as DocumentImage
    from app.db.models.rag_document import RagDocument as Document

    doc_ids = {pair[0] for pair in doc_page_pairs}
    pages = {pair[1] for pair in doc_page_pairs if pair[1] is not None}

    if not pages:
        return []

    doc_uuids = [uuid.UUID(d) for d in doc_ids]

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DocumentImage, Document.original_filename)
            .join(Document, Document.id == DocumentImage.document_id)
            .where(
                DocumentImage.document_id.in_(doc_uuids),
                DocumentImage.page_number.in_(list(pages)),
                DocumentImage.description.isnot(None),
            )
        )
        rows = result.all()

    candidates = []
    for img, filename in rows:
        desc = (img.description or "").strip()
        if not desc:
            continue
        # Enriquecer con OCR si existe
        if img.ocr_text:
            desc = desc + " " + img.ocr_text.strip()
        candidates.append({
            "type": "image",
            "content": desc,
            "image_id": str(img.id),
            "doc_id": str(img.document_id),
            "filename": filename,
            "page": img.page_number,
            "score": 0.85,
        })

    return candidates


async def build_context(
    message: str,
    document_ids: list[str] | None,
    history: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Devuelve (text_contexts, image_sources) — ambos rerankeados, top rerank_top_k en total.
    Las image_sources llevan el campo 'content' con la descripción de la imagen para el prompt.
    """
    search_query = message
    if history:
        recent_user = [t["content"] for t in history[-4:] if t["role"] == "user"]
        if recent_user:
            search_query = " ".join(recent_user[-2:]) + " " + message

    query_vector = await embedder.embed_text(search_query)

    chroma_hits = await vector_store.search(
        query_vector=query_vector,
        top_k=settings.retrieval_top_k,
        doc_ids=document_ids,
    )

    text_candidates: list[dict] = []
    doc_page_pairs: set[tuple[str, int]] = set()

    for r in chroma_hits:
        text_candidates.append({
            "type": "text",
            "content": r["content"],
            "doc_id": r["doc_id"],
            "filename": r["filename"],
            "page": r["page_number"],
            "score": r["score"],
        })
        if r.get("doc_id") and r.get("page_number"):
            doc_page_pairs.add((r["doc_id"], r["page_number"]))

    image_candidates = await _fetch_image_descriptions(doc_page_pairs)

    pool = text_candidates + image_candidates
    if not pool:
        return [], []

    reranked = await reranker_svc.rerank(message, pool, top_k=settings.rerank_top_k)

    text_contexts = [c for c in reranked if c["type"] == "text"]
    image_sources = [c for c in reranked if c["type"] == "image"]

    return text_contexts, image_sources


def _build_sources(
    text_contexts: list[dict],
    image_sources: list[dict],
) -> list[Source]:
    sources: list[Source] = []
    for ctx in text_contexts:
        sources.append(Source(
            type="text",
            doc_id=ctx["doc_id"],
            filename=ctx["filename"],
            page=ctx["page"],
            image_id=None,
            score=ctx.get("rerank_score", ctx["score"]),
        ))
    for img in image_sources:
        sources.append(Source(
            type="image",
            doc_id=img["doc_id"],
            filename=img["filename"],
            page=img["page"],
            image_id=img["image_id"],
            score=img.get("rerank_score", img.get("score", 0.85)),
        ))
    return sources


_MAX_TEXT_CHUNK_CHARS = 900


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


def _build_messages(
    message: str,
    text_contexts: list[dict],
    image_sources: list[dict],
    history: list[dict],
) -> list[dict]:
    context_text = ""
    item_num = 1

    for ctx in text_contexts:
        src = f"[Fuente {item_num}: {ctx['filename']}"
        if ctx.get("page"):
            src += f", página {ctx['page']}"
        src += "]"
        context_text += f"\n{src}\n{_truncate(ctx['content'], _MAX_TEXT_CHUNK_CHARS)}\n"
        item_num += 1

    for img in image_sources:
        desc = (img.get("content") or "").strip()
        if not desc:
            continue
        src = f"[Figura {item_num}: {img['filename']}"
        if img.get("page"):
            src += f", página {img['page']}"
        src += "]"
        context_text += f"\n{src}\n{_truncate(desc, _MAX_TEXT_CHUNK_CHARS)}\n"
        item_num += 1

    context_block = context_text.strip()

    history_text = ""
    for turn in history[-4:]:
        label = "Usuario" if turn["role"] == "user" else "Asistente"
        history_text += f"{label}: {turn['content']}\n"

    user_content = ""
    if context_block:
        user_content += f"CONTEXTO DE DOCUMENTOS:\n{context_block}\n\n"
    if history_text:
        user_content += f"HISTORIAL:\n{history_text}\n"
    user_content += f"Pregunta: {message}"

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


_ERROR_PREFIX = "\x00ERR\x00"


async def stream_chat(
    message: str,
    text_contexts: list[dict],
    image_sources: list[dict],
    history: list[dict],
) -> AsyncGenerator[tuple[str, list[Source] | None], None]:
    messages = _build_messages(message, text_contexts, image_sources, history)
    sources = _build_sources(text_contexts, image_sources)

    loop = asyncio.get_running_loop()
    token_queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _run_llm() -> None:
        llm = get_chat_llm()
        try:
            stream = llm.create_chat_completion(
                messages=messages,
                max_tokens=settings.qwen_max_tokens,
                stream=True,
                stop=["<|im_end|>", "<|endoftext|>", "Usuario:", "\nUser:"],
                temperature=settings.qwen_temperature,
                top_p=settings.qwen_top_p,
                top_k=settings.qwen_top_k,
                repeat_penalty=settings.qwen_repeat_penalty,
            )
            # Filter <think>...</think> blocks that Qwen3 emits even with /no_think
            in_think = False
            think_buf = ""
            for chunk in stream:
                delta = chunk["choices"][0]["delta"]
                content: str = delta.get("content") or ""
                if not content:
                    continue
                think_buf += content
                # Consume known think-block patterns from buffer
                while True:
                    if not in_think:
                        idx = think_buf.find("<think>")
                        if idx == -1:
                            # No think block starting — emit everything
                            emit, think_buf = think_buf, ""
                            break
                        # Emit text before <think>, then enter think mode
                        emit = think_buf[:idx]
                        think_buf = think_buf[idx + len("<think>"):]
                        in_think = True
                        if emit:
                            asyncio.run_coroutine_threadsafe(
                                token_queue.put(emit), loop
                            ).result(timeout=30)
                    else:
                        idx = think_buf.find("</think>")
                        if idx == -1:
                            # Still inside think block — discard buffer
                            think_buf = ""
                            emit = ""
                            break
                        # Exit think mode, keep text after </think>
                        think_buf = think_buf[idx + len("</think>"):].lstrip("\n")
                        in_think = False
                        emit = ""
                        break
                if emit:
                    asyncio.run_coroutine_threadsafe(
                        token_queue.put(emit), loop
                    ).result(timeout=30)
            # Flush remaining buffer (not in a think block)
            if think_buf and not in_think:
                asyncio.run_coroutine_threadsafe(
                    token_queue.put(think_buf), loop
                ).result(timeout=30)
        except Exception as exc:
            logger.error("Error de inferencia LLM: %s", exc)
            asyncio.run_coroutine_threadsafe(
                token_queue.put(f"{_ERROR_PREFIX}{exc}"), loop
            ).result(timeout=5)
        finally:
            asyncio.run_coroutine_threadsafe(
                token_queue.put(None), loop
            ).result(timeout=5)

    async with inference_queue.acquire():
        llm_task = loop.run_in_executor(None, _run_llm)

        try:
            while True:
                item = await token_queue.get()
                if item is None:
                    break
                if isinstance(item, str) and item.startswith(_ERROR_PREFIX):
                    raise RuntimeError(item[len(_ERROR_PREFIX):])
                yield item, None
        finally:
            await llm_task

    yield "", sources
