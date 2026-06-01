import asyncio
import base64
import logging

from app.config import settings
from app.cache import embedding_cache
from app.utils.model_manager import get_embedder, get_vision_llm
from app.utils.inference_queue import inference_queue

logger = logging.getLogger(__name__)

# BGE-M3 usa recuperación simétrica — NO necesita prefijos query:/passage:


def _embed_text_sync(text: str) -> list[float]:
    model = get_embedder()
    vector = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
    return vector.tolist()


async def embed_text(text: str) -> list[float]:
    cached = await asyncio.to_thread(embedding_cache.get, text)
    if cached is not None:
        return cached
    result = await asyncio.to_thread(_embed_text_sync, text)
    await asyncio.to_thread(embedding_cache.set, text, result)
    return result


def _embed_texts_batch_sync(texts: list[str]) -> list[list[float]]:
    model = get_embedder()
    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=32,
    )
    return [v.tolist() for v in vectors]


async def embed_texts_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return await asyncio.to_thread(_embed_texts_batch_sync, texts)


_CAPTION_INSTRUCTION = (
    "Describe esta imagen en español de forma concisa y detallada. "
    "Incluye todos los elementos visuales relevantes: texto visible, "
    "diagramas, tablas, figuras, y su significado en contexto bancario."
)


async def describe_image(image_bytes: bytes, page_context: str = "") -> str:
    """Genera una descripción en español de la imagen usando Gemma-4 visión.

    `page_context` es el texto de la página donde aparece la imagen; se inyecta
    como contexto (no se copia) para que la VLM interprete mejor la figura.

    Pasa por inference_queue internamente — el caller no necesita hacerlo.
    """
    b64 = base64.b64encode(image_bytes).decode("utf-8")

    prompt_text = _CAPTION_INSTRUCTION
    context = page_context.strip()
    if context:
        prompt_text = (
            "Contexto del documento donde aparece la imagen (úsalo solo para "
            "entender la imagen; NO lo copies ni lo repitas literalmente):\n"
            f'"""\n{context}\n"""\n\n'
            + _CAPTION_INSTRUCTION
        )

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                },
                {
                    "type": "text",
                    "text": prompt_text,
                },
            ],
        }
    ]

    def _run() -> str:
        llm = get_vision_llm()
        response = llm.create_chat_completion(
            messages=messages,
            max_tokens=settings.vision_max_tokens,
            temperature=settings.vision_temperature,
        )
        return response["choices"][0]["message"]["content"].strip()

    async with inference_queue.acquire():
        result = await asyncio.to_thread(_run)
    return result


async def check_health() -> bool:
    from app.utils.model_manager import models_loaded
    return models_loaded()
