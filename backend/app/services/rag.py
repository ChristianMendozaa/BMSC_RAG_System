import asyncio
import logging
import re
from typing import AsyncGenerator

from app.config import settings
from app.schemas import Source
from app.services import embedder, vector_store
from app.utils.model_manager import get_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres un asistente experto del banco. Tu función es ayudar a los empleados
a consultar la documentación interna del banco de manera precisa y útil.

Directrices:
- Responde siempre en español, de manera clara y profesional.
- Basa tus respuestas exclusivamente en el contexto proporcionado.
- Si la información no está en el contexto, indícalo claramente.
- Cita las fuentes cuando sea relevante (nombre del documento y página).
- Para procedimientos, usa listas numeradas. Para información general, usa párrafos.
- Nunca inventes información que no esté en los documentos proporcionados.
- El contexto puede incluir descripciones de imágenes extraídas del documento (indicadas como
  "[Imagen de: ...]"). Cada descripción combina: una descripción visual en español, el texto
  literal extraído por OCR de la imagen, y el contexto de la página.
- Si la pregunta es sobre un diagrama, figura, esquema o imagen y el contexto incluye al menos
  una imagen ([Imagen de: ...]) — incluso si su descripción es corta o limitada — describe
  lo que sepas a partir de ella e indica "La imagen correspondiente se muestra a continuación.".
  Nunca respondas "no encuentro" si hay al menos una imagen relevante en el contexto.
- Las imágenes reales se muestran automáticamente al usuario en la interfaz. Nunca digas que
  no puedes ver imágenes: tienes acceso a sus descripciones."""


# Visual-query detector: when the user is clearly asking about something that
# lives inside an image, we relax the image filters and boost visual recall.
_VISUAL_TERMS = re.compile(
    r'\b('
    r'diagrama|figura|imagen|im[aá]genes|esquema|gr[aá]fico|tabla|captura|'
    r'mapa|flujo|arquitectura|cronograma|mockup|pantalla|interfaz|'
    r'foto|fotograf[ií]a|ilustraci[oó]n|dibujo|plano|p[aá]gina'
    r')\b',
    re.IGNORECASE,
)


def _is_visual_query(message: str) -> bool:
    return bool(_VISUAL_TERMS.search(message or ""))


async def build_context(
    message: str,
    document_ids: list[str] | None,
    history: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    search_query = message
    if history:
        recent_user = [t["content"] for t in history[-4:] if t["role"] == "user"]
        if recent_user:
            search_query = " ".join(recent_user[-2:]) + " " + message

    visual_mode = _is_visual_query(message)
    max_images = (
        settings.visual_query_max_images if visual_mode else settings.max_context_images
    )
    min_image_score = (
        settings.visual_query_min_image_score if visual_mode else settings.min_image_score
    )

    # ── 1. Text-space search (MiniLM) — returns texto + image_descriptions ──
    text_query_vector = await embedder.embed_text(search_query)
    total_k = settings.max_context_chunks + max_images
    text_results = await vector_store.search(
        query_vector=text_query_vector,
        top_k=total_k * 2,  # over-fetch so the text-vs-image split has enough of both
        doc_ids=document_ids,
    )

    text_contexts: list[dict] = []
    image_contexts_text_space: list[dict] = []
    for r in text_results:
        if not r.payload:
            continue
        chunk_type = r.payload.get("chunk_type", "text")
        base = {
            "content": r.payload.get("content", ""),
            "doc_id": r.payload.get("doc_id", ""),
            "filename": r.payload.get("filename", ""),
            "page": r.payload.get("page_number"),
            "score": r.score,
        }
        if chunk_type == "image_description":
            if len(image_contexts_text_space) < max_images * 3:
                image_contexts_text_space.append({
                    **base,
                    "image_id": r.payload.get("image_id"),
                    "caption": r.payload.get("caption", ""),
                })
        else:
            if len(text_contexts) < settings.max_context_chunks:
                text_contexts.append(base)

    # ── 2. Visual-space search (CLIP multilingual → image vectors) ─────────
    image_contexts_visual_space: list[dict] = []
    try:
        clip_query_vector = await embedder.embed_text_clip(search_query)
        visual_results = await vector_store.search_image_visual(
            query_vector=clip_query_vector,
            top_k=max_images * 3,
            doc_ids=document_ids,
        )
        for r in visual_results:
            if not r.payload:
                continue
            image_id = r.payload.get("image_id") or str(r.id)
            image_contexts_visual_space.append({
                "image_id": image_id,
                "doc_id": r.payload.get("doc_id", ""),
                "filename": r.payload.get("filename", ""),
                "page": r.payload.get("page_number"),
                "content": r.payload.get("caption") or "",
                "caption": r.payload.get("caption", ""),
                "score": r.score,
            })
    except Exception as exc:
        logger.warning("Visual search failed: %s", exc)

    # ── 3. Reciprocal Rank Fusion of the two image lists ──────────────────
    image_contexts = _rrf_merge_images(
        image_contexts_text_space,
        image_contexts_visual_space,
        k=settings.rrf_k,
    )[: max_images * 2]  # leave headroom; final filter applied below

    # ── 4. Apply absolute floor + (only when not in visual mode) gap filter ─
    if image_contexts:
        if not visual_mode and len(image_contexts) > 1:
            best = image_contexts[0]["score"]
            relative_floor = best * settings.image_score_gap
            image_contexts = [image_contexts[0]] + [
                ctx for ctx in image_contexts[1:]
                if ctx["score"] >= min_image_score
                and ctx["score"] >= relative_floor
            ]
        else:
            # visual mode: keep the winner unconditionally, drop only sub-floor
            image_contexts = [image_contexts[0]] + [
                ctx for ctx in image_contexts[1:]
                if ctx["score"] >= min_image_score
            ]
        image_contexts = image_contexts[:max_images]

    return text_contexts, image_contexts


def _rrf_merge_images(
    text_space: list[dict],
    visual_space: list[dict],
    k: int = 60,
) -> list[dict]:
    """Merge two ranked image lists with Reciprocal Rank Fusion.

    Each image's RRF score is sum(1/(k+rank)) over the lists it appears in.
    The original cosine score is preserved on the surviving record (used later
    for absolute floors and for the Source.score sent to the frontend).
    """
    combined: dict[str, dict] = {}
    rrf_scores: dict[str, float] = {}

    for rank, ctx in enumerate(text_space):
        img_id = ctx.get("image_id")
        if not img_id:
            continue
        rrf_scores[img_id] = rrf_scores.get(img_id, 0.0) + 1.0 / (k + rank + 1)
        if img_id not in combined:
            combined[img_id] = ctx

    for rank, ctx in enumerate(visual_space):
        img_id = ctx.get("image_id")
        if not img_id:
            continue
        rrf_scores[img_id] = rrf_scores.get(img_id, 0.0) + 1.0 / (k + rank + 1)
        if img_id not in combined:
            combined[img_id] = ctx
        else:
            # Prefer richer content from text-space, but adopt the higher cosine score
            existing = combined[img_id]
            if ctx["score"] > existing["score"]:
                existing["score"] = ctx["score"]
            if not existing.get("caption") and ctx.get("caption"):
                existing["caption"] = ctx["caption"]
                if not existing.get("content"):
                    existing["content"] = ctx["caption"]

    merged = list(combined.values())
    merged.sort(key=lambda c: rrf_scores.get(c["image_id"], 0.0), reverse=True)
    return merged


def _build_sources(text_contexts: list[dict], image_contexts: list[dict]) -> list[Source]:
    sources: list[Source] = []
    for ctx in text_contexts:
        sources.append(Source(
            type="text",
            doc_id=ctx["doc_id"],
            filename=ctx["filename"],
            page=ctx["page"],
            image_id=None,
            score=ctx["score"],
        ))
    for ctx in image_contexts:
        sources.append(Source(
            type="image",
            doc_id=ctx["doc_id"],
            filename=ctx["filename"],
            page=ctx["page"],
            image_id=ctx.get("image_id"),
            score=ctx["score"],
        ))
    return sources


# Max chars sent to the LLM per chunk (embeddings use the full text; LLM gets a summary).
# ~4 chars ≈ 1 token; these limits keep total prompt well under 8192 ctx.
_MAX_TEXT_CHUNK_CHARS = 900
_MAX_IMAGE_CHUNK_CHARS = 600


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


def _build_messages(
    message: str,
    text_contexts: list[dict],
    image_contexts: list[dict],
    history: list[dict],
) -> list[dict]:
    context_text = ""
    for i, ctx in enumerate(text_contexts, 1):
        src = f"[Fuente {i}: {ctx['filename']}"
        if ctx["page"]:
            src += f", página {ctx['page']}"
        src += "]"
        context_text += f"\n{src}\n{_truncate(ctx['content'], _MAX_TEXT_CHUNK_CHARS)}\n"

    image_context_text = ""
    for ctx in image_contexts:
        src = f"[Imagen de: {ctx['filename']}"
        if ctx["page"]:
            src += f", página {ctx['page']}"
        src += "]"
        image_context_text += f"\n{src}\n{_truncate(ctx['content'], _MAX_IMAGE_CHUNK_CHARS)}\n"

    context_block = (context_text + image_context_text).strip()

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


_SENTINEL = object()
_ERROR_PREFIX = "\x00ERR\x00"


async def stream_chat(
    message: str,
    text_contexts: list[dict],
    image_contexts: list[dict],
    history: list[dict],
    image_bytes_map: dict[str, bytes],  # noqa: ARG001 — kept for API compat; LLM is text-only
) -> AsyncGenerator[tuple[str, list[Source] | None], None]:
    messages = _build_messages(message, text_contexts, image_contexts, history)
    sources = _build_sources(text_contexts, image_contexts)

    loop = asyncio.get_running_loop()
    token_queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _run_llm() -> None:
        llm = get_llm()
        try:
            stream = llm.create_chat_completion(
                messages=messages,
                max_tokens=settings.llm_max_tokens,
                stream=True,
                stop=["Usuario:", "\nUser:", "<|im_end|>"],
                temperature=0.7,
            )
            for chunk in stream:
                delta = chunk["choices"][0]["delta"]
                content: str = delta.get("content") or ""
                if content:
                    asyncio.run_coroutine_threadsafe(
                        token_queue.put(content), loop
                    ).result(timeout=30)
        except Exception as exc:
            logger.error("LLM inference error: %s", exc)
            asyncio.run_coroutine_threadsafe(
                token_queue.put(f"{_ERROR_PREFIX}{exc}"), loop
            ).result(timeout=5)
        finally:
            asyncio.run_coroutine_threadsafe(
                token_queue.put(None), loop
            ).result(timeout=5)

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
