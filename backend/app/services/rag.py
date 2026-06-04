import asyncio
import logging
import math
import threading
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


_SYSTEM_PROMPT_BASE = """Eres un asistente experto de soporte del banco. Tu función es guiar a
operarios y empleados resolviendo consultas sobre documentación interna, manuales operativos e
incidencias, de forma precisa, accionable y fiable.

Directrices:
- Responde siempre en español, de forma clara, concisa y profesional.
- Basa tus respuestas EXCLUSIVAMENTE en el contexto proporcionado. Nunca inventes datos, pasos,
  valores ni nombres que no estén en los documentos.
- No describas lo que el documento "podría", "puede" o "suele" contener. Cíñete a lo que aparece
  literalmente en el contexto; no especules ni generalices.
- Las descripciones de figuras del contexto SON la información visual disponible, ya extraída en
  texto. Trátalas como hechos del documento. Nunca digas que no puedes ver imágenes, que no hay
  imágenes adjuntas, ni pidas que se adjunte ninguna imagen.
- Si la información necesaria no está en el contexto, dilo explícitamente ("Esta información no está
  en la documentación disponible") y, si procede, sugiere escalar o consultar al área responsable.
- Para procedimientos e incidencias, responde con pasos numerados en el orden de ejecución; señala
  los requisitos previos, advertencias o riesgos cuando el documento los mencione.
- Para consultas conceptuales, usa párrafos breves.
- Cita la fuente entre paréntesis cuando sea relevante (nombre del documento y página),
  p. ej. (Manual de operaciones, pág. 4).
- El contexto puede incluir fragmentos de texto y descripciones textuales de figuras, tablas o
  diagramas extraídas de los documentos. Trátalas como información válida del documento.
- Cuando el contexto incluya fragmentos de MÚLTIPLES documentos, tu respuesta debe abarcar
  TODOS los documentos presentes en el contexto. No respondas solo sobre uno si hay varios."""

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


def _select_diverse(items: list[dict], k: int, multi: bool) -> list[dict]:
    """Selecciona k items del pool ya ordenado por rerank_score.

    - multi=False → top-k simple (comportamiento original).
    - multi=True  → round-robin por doc_id: cada documento recibe al menos un slot
      antes de que cualquiera reciba el segundo. El orden de turno de los documentos
      se fija por el mejor score de cada uno (el pool ya viene ordenado).
    """
    if not multi:
        return items[:k]

    # Agrupar preservando el orden de llegada (ya ordenado por score desc)
    buckets: dict[str, list[dict]] = {}
    for item in items:
        did = item.get("doc_id", "")
        if did not in buckets:
            buckets[did] = []
        buckets[did].append(item)

    # Orden de turno: el primer elemento de cada bucket ya es el mejor de ese doc
    doc_order = list(buckets.keys())

    selected: list[dict] = []
    while len(selected) < k:
        added_this_round = False
        for did in doc_order:
            if not buckets[did]:
                continue
            selected.append(buckets[did].pop(0))
            added_this_round = True
            if len(selected) == k:
                break
        if not added_this_round:
            break  # pool agotado
    return selected


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

    num_docs = len(document_ids) if document_ids else 0
    multi = num_docs > 1

    t0 = time.perf_counter()
    if multi and num_docs <= settings.retrieval_balanced_max_docs:
        # Recuperación equilibrada: cada documento aporta sus mejores fragmentos al pool.
        per_doc_k = max(2, math.ceil(settings.retrieval_top_k / num_docs))
        results = await asyncio.gather(*[
            vector_store.search(query_vector=query_vector, top_k=per_doc_k, doc_ids=[d])
            for d in document_ids
        ])
        chroma_hits = [h for r in results for h in r]
    else:
        chroma_hits = await vector_store.search(
            query_vector=query_vector,
            top_k=settings.retrieval_top_k,
            doc_ids=document_ids,
        )
    _perf_log(
        "chroma-search: %.3fs (%d hits, multi=%s)",
        time.perf_counter() - t0, len(chroma_hits), multi,
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
    # Cap de imágenes que entran al reranker: cada par extra cuesta CPU en el cross-encoder
    if len(image_candidates) > settings.rerank_max_images:
        image_candidates = image_candidates[:settings.rerank_max_images]
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

    # Presupuesto efectivo: escala con el número de documentos en multi-doc
    effective_top_k = settings.rerank_top_k
    if multi:
        effective_top_k = min(
            settings.rerank_top_k + (num_docs - 1),
            settings.rerank_top_k_max,
        )

    t0 = time.perf_counter()
    # Rerankear TODO el pool para obtener scores completos; la selección diversa recorta después
    reranked_all = await reranker_svc.rerank(message, pool, top_k=len(pool))
    reranked = _select_diverse(reranked_all, effective_top_k, multi)
    _perf_log(
        "rerank(BGE-ce): %.3fs (%d->%d, budget=%d)",
        time.perf_counter() - t0, len(pool), len(reranked), effective_top_k,
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


_MAX_TEXT_CHUNK_CHARS = 1300
_MAX_HISTORY_TURN_CHARS = 500


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
        src = f"[Descripción de figura {item_num} — {img['filename']}"
        if img.get("page"):
            src += f", página {img['page']}"
        src += "]"
        context_text += f"\n{src}\n{_truncate(desc, _MAX_TEXT_CHUNK_CHARS)}\n"
        item_num += 1

    context_block = context_text.strip()

    history_text = ""
    # Solo los 2 últimos turnos y truncados: evita reinyectar respuestas largas en cada prefill
    for turn in history[-2:]:
        label = "Usuario" if turn["role"] == "user" else "Asistente"
        history_text += f"{label}: {_truncate(turn['content'], _MAX_HISTORY_TURN_CHARS)}\n"

    # Cabecera explícita de documentos en scope (solo en multi-doc) para que el LLM
    # sepa cuántos documentos hay y los mencione todos en respuestas de conjunto.
    doc_names = list(dict.fromkeys(
        c["filename"] for c in text_contexts + image_sources if c.get("filename")
    ))

    user_content = ""
    if len(doc_names) > 1:
        names_str = ", ".join(doc_names)
        user_content += f"DOCUMENTOS EN CONSULTA ({len(doc_names)}): {names_str}\n\n"
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
    cancel_flag: threading.Event | None = None,
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
                if cancel_flag is not None and cancel_flag.is_set():
                    break
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
