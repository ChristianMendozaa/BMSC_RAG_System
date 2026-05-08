import asyncio
import io
import logging

from PIL import Image

from app.config import settings
from app.utils.model_manager import (
    get_blip,
    get_clip_image,
    get_clip_text,
    get_embedder,
)

logger = logging.getLogger(__name__)


def _needs_e5_prefix() -> bool:
    return "e5" in settings.embed_model_id.lower()


def _query_prefix(text: str) -> str:
    """Prepend 'query: ' for multilingual-e5 asymmetric retrieval."""
    return f"query: {text}" if _needs_e5_prefix() else text


def _passage_prefix(text: str) -> str:
    """Prepend 'passage: ' for multilingual-e5 asymmetric retrieval."""
    return f"passage: {text}" if _needs_e5_prefix() else text


# ── Text embeddings (384 dims) ─────────────────────────────────────────────
def _embed_text_sync(text: str) -> list[float]:
    model = get_embedder()
    vector = model.encode(_query_prefix(text), normalize_embeddings=True, show_progress_bar=False)
    return vector.tolist()


async def embed_text(text: str) -> list[float]:
    return await asyncio.to_thread(_embed_text_sync, text)


def _embed_texts_batch_sync(texts: list[str]) -> list[list[float]]:
    model = get_embedder()
    prefixed = [_passage_prefix(t) for t in texts]
    vectors = model.encode(
        prefixed,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=32,
    )
    return [v.tolist() for v in vectors]


async def embed_texts_batch(texts: list[str]) -> list[list[float]]:
    """Encode all texts in a single model.encode() call — 3-5x faster than one-by-one."""
    if not texts:
        return []
    return await asyncio.to_thread(_embed_texts_batch_sync, texts)


# ── CLIP multilingual (text ↔ image in shared 512-dim space) ───────────────
def _embed_text_clip_sync(text: str) -> list[float]:
    model = get_clip_text()
    vector = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
    return vector.tolist()


async def embed_text_clip(text: str) -> list[float]:
    return await asyncio.to_thread(_embed_text_clip_sync, text)


def _embed_image_sync(image_bytes: bytes) -> list[float]:
    import torch
    import torch.nn.functional as F

    processor, model = get_clip_image()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    pixel_values = processor(images=image, return_tensors="pt")["pixel_values"]

    with torch.no_grad():
        output = model.get_image_features(pixel_values=pixel_values)
        # Some transformers versions return BaseModelOutputWithPooling instead of a tensor
        if not isinstance(output, torch.Tensor):
            output = output.pooler_output
        features = F.normalize(output, p=2, dim=-1)
    return features[0].cpu().tolist()


async def embed_image(image_bytes: bytes) -> list[float]:
    return await asyncio.to_thread(_embed_image_sync, image_bytes)


# ── Image captioning via BLIP-base (fast CPU-friendly, ~2-5s/image) ────────
def _describe_image_sync(image_bytes: bytes) -> str:
    import torch

    processor, model = get_blip()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    # Resize to 512px max — BLIP internally uses 384px anyway, avoids OOM on large images
    image.thumbnail((512, 512), Image.LANCZOS)

    inputs = processor(image, return_tensors="pt")
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=settings.blip_max_new_tokens)
    caption = processor.decode(out[0], skip_special_tokens=True)
    return caption.strip()


async def describe_image(image_bytes: bytes) -> str:
    return await asyncio.to_thread(_describe_image_sync, image_bytes)


async def check_health() -> bool:
    from app.utils.model_manager import models_loaded
    return models_loaded()
