import asyncio
import logging
import time
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


def _perf_log(msg: str, *args) -> None:
    if settings.chat_perf_logging:
        logger.info("[chat-perf] " + msg, *args)


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

SYSTEM_PROMPT = _SYSTEM_PROMPT_BASE


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
    t_build_start = time.perf_counter()

    search_query = message
    if history:
        recent_user = [t["content"] for t in history[-4:] if t["role"] == "user"]
        if recent_user:
            search_query = " ".join(recent_user[-2:]) + " " + message

    t0 = time.perf_counter()
    query_vector = await embedder.embed_text(search_query)
    _perf_log("embedding(BGE-M3): %.3fs", time.perf_counter() - t0)

    t0 = time.perf_counter()
    chroma_hits = await vector_store.search(
        query_vector=query_vector,
        top_k=settings.retrieval_top_k,
        doc_ids=document_ids,
    )
    _perf_log(
        "chroma-search: %.3fs (%d hits)",
        time.perf_counter() - t0, len(chroma_hits),
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

    t0 = time.perf_counter()
    image_candidates = await _fetch_image_descriptions(doc_page_pairs)
    _perf_log(
        "image-desc(db): %.3fs (%d imgs)",
        time.perf_counter() - t0, len(image_candidates),
    )

    pool = text_candidates + image_candidates
    if not pool:
        _perf_log(
            "retrieval total: %.3fs (pool vacío)",
            time.perf_counter() - t_build_start,
        )
        return [], []

    t0 = time.perf_counter()
    reranked = await reranker_svc.rerank(message, pool, top_k=settings.rerank_top_k)
    _perf_log(
        "rerank(BGE-ce): %.3fs (%d->%d)",
        time.perf_counter() - t0, len(pool), len(reranked),
    )

    text_contexts = [c for c in reranked if c["type"] == "text"]
    image_sources = [c for c in reranked if c["type"] == "image"]

    _perf_log(
        "retrieval total: %.3fs",
        time.perf_counter() - t_build_start,
    )

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

    # Métricas de inferencia compartidas con el scope async (rellenadas en el executor)
    llm_stats: dict[str, float] = {"start": 0.0, "first_token": 0.0, "end": 0.0, "n_tokens": 0}

    def _run_llm() -> None:
        llm = get_chat_llm()
        llm_stats["start"] = time.perf_counter()
        try:
            stream = llm.create_chat_completion(
                messages=messages,
                max_tokens=settings.chat_max_tokens,
                stream=True,
                stop=["<|eot_id|>", "<|end_of_text|>", "Usuario:", "\nUser:"],
                temperature=settings.chat_temperature,
                top_p=settings.chat_top_p,
                top_k=settings.chat_top_k,
                repeat_penalty=settings.chat_repeat_penalty,
            )
            for chunk in stream:
                content: str = chunk["choices"][0]["delta"].get("content") or ""
                if not content:
                    continue
                if llm_stats["n_tokens"] == 0:
                    llm_stats["first_token"] = time.perf_counter()
                llm_stats["n_tokens"] += 1
                asyncio.run_coroutine_threadsafe(
                    token_queue.put(content), loop
                ).result(timeout=30)
        except Exception as exc:
            logger.error("Error de inferencia LLM: %s", exc)
            asyncio.run_coroutine_threadsafe(
                token_queue.put(f"{_ERROR_PREFIX}{exc}"), loop
            ).result(timeout=5)
        finally:
            llm_stats["end"] = time.perf_counter()
            asyncio.run_coroutine_threadsafe(
                token_queue.put(None), loop
            ).result(timeout=5)

    t_request = time.perf_counter()
    async with inference_queue.acquire():
        _perf_log("cola-llm wait: %.3fs", time.perf_counter() - t_request)
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

        n_tokens = int(llm_stats["n_tokens"])
        if n_tokens > 0 and llm_stats["first_token"] > 0:
            prefill = llm_stats["first_token"] - llm_stats["start"]
            gen_time = llm_stats["end"] - llm_stats["first_token"]
            tok_per_s = n_tokens / gen_time if gen_time > 0 else 0.0
            _perf_log("prefill(TTFT chat): %.3fs", prefill)
            _perf_log(
                "generacion(chat): %d tokens en %.2fs -> %.1f tok/s",
                n_tokens, gen_time, tok_per_s,
            )
        else:
            _perf_log("generacion(chat): sin tokens generados")

    yield "", sources
