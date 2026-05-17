import asyncio
import logging
import re
from typing import AsyncGenerator

from app.config import settings
from app.schemas import Source
from app.services import embedder, vector_store
from app.utils.model_manager import get_llm
from app.utils.inference_queue import inference_queue

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
- El contexto incluye descripciones de imágenes integradas en el texto (marcadas como [Figura]).
  Úsalas para responder preguntas sobre diagramas, tablas o figuras técnicas.
- Las imágenes reales se muestran al usuario en la interfaz automáticamente cuando son relevantes."""


_VISUAL_TERMS = re.compile(
    r'\b('
    r'diagrama|figura|imagen|im[aá]genes|esquema|gr[aá]fico|tabla|captura|'
    r'mapa|flujo|arquitectura|cronograma|mockup|pantalla|interfaz|'
    r'foto|fotograf[ií]a|ilustraci[oó]n|dibujo|plano|p[aá]gina|'
    r'uml|clases|clase|entidad|relaci[oó]n|herencia|composici[oó]n|'
    r'componente|secuencia|actividad|paquete|despliegue|modelo'
    r')\b',
    re.IGNORECASE,
)


def _is_visual_query(message: str) -> bool:
    return bool(_VISUAL_TERMS.search(message or ""))


async def build_context(
    message: str,
    document_ids: list[str] | None,
    history: list[dict] | None = None,
) -> tuple[list[dict], list[str]]:
    """Return (text_contexts, image_ids) where image_ids are ordered by retrieval score."""
    search_query = message
    if history:
        recent_user = [t["content"] for t in history[-4:] if t["role"] == "user"]
        if recent_user:
            search_query = " ".join(recent_user[-2:]) + " " + message

    query_vector = await embedder.embed_text(search_query)

    results = await vector_store.search(
        query_vector=query_vector,
        top_k=settings.max_context_chunks * 2,
        doc_ids=document_ids,
    )

    text_contexts: list[dict] = []
    collected_image_ids: list[str] = []
    seen_image_ids: set[str] = set()

    for r in results:
        if len(text_contexts) >= settings.max_context_chunks:
            break
        text_contexts.append({
            "content": r["content"],
            "doc_id": r["doc_id"],
            "filename": r["filename"],
            "page": r["page_number"],
            "score": r["score"],
        })
        raw_ids = r.get("image_ids", "")
        if raw_ids:
            for img_id in raw_ids.split(","):
                img_id = img_id.strip()
                if img_id and img_id not in seen_image_ids:
                    seen_image_ids.add(img_id)
                    collected_image_ids.append(img_id)

    return text_contexts, collected_image_ids


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
            score=ctx["score"],
        ))
    for img in image_sources:
        sources.append(Source(
            type="image",
            doc_id=img["doc_id"],
            filename=img["filename"],
            page=img["page"],
            image_id=img["image_id"],
            score=img.get("score", 0.85),
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
    for i, ctx in enumerate(text_contexts, 1):
        src = f"[Fuente {i}: {ctx['filename']}"
        if ctx["page"]:
            src += f", página {ctx['page']}"
        src += "]"
        context_text += f"\n{src}\n{_truncate(ctx['content'], _MAX_TEXT_CHUNK_CHARS)}\n"

    if image_sources:
        context_text += (
            f"\n[Nota: Se muestran {len(image_sources)} imagen(es) de referencia "
            f"al usuario en la interfaz.]\n"
        )

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
    _image_bytes_map: dict[str, bytes],
) -> AsyncGenerator[tuple[str, list[Source] | None], None]:
    messages = _build_messages(message, text_contexts, image_sources, history)
    sources = _build_sources(text_contexts, image_sources)

    loop = asyncio.get_running_loop()
    token_queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _run_llm() -> None:
        llm = get_llm()
        try:
            stream = llm.create_chat_completion(
                messages=messages,
                max_tokens=settings.llm_max_tokens,
                stream=True,
                stop=["Usuario:", "\nUser:", "<end_of_turn>"],
                temperature=0.7,
                repeat_penalty=settings.llm_repeat_penalty,
            )
            for chunk in stream:
                delta = chunk["choices"][0]["delta"]
                content: str = delta.get("content") or ""
                if content:
                    asyncio.run_coroutine_threadsafe(
                        token_queue.put(content), loop
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
