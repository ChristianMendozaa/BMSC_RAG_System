"""
Downloads and loads all HuggingFace models at startup.
No token required — all models are public.

Download order (shown with tqdm progress bars):
  [1/4] LLM      bartowski/Qwen2.5-1.5B-Instruct-GGUF       (~1 GB)
  [2/4] Embed    paraphrase-multilingual-MiniLM-L12-v2       (~500 MB)
  [3/4] BLIP     Salesforce/blip-image-captioning-base       (~450 MB)
  [4/4] CLIP     clip-ViT-B-32-multilingual-v1               (~600 MB)

OCR uses pytesseract (system Tesseract binary) — no model download needed.
On subsequent starts, cached files are found instantly — no re-download.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Module-level singletons — loaded once at startup, read-only afterwards
_llm: Any = None
_embedder: Any = None
_blip_processor: Any = None
_blip_model: Any = None
_clip_text: Any = None
_clip_image_model: Any = None
_clip_image_processor: Any = None


def _load_all_sync() -> None:
    global _llm, _embedder, _blip_processor, _blip_model, _clip_text, _clip_image_model, _clip_image_processor

    from app.config import settings

    cache = Path(settings.hf_cache_dir)
    cache.mkdir(parents=True, exist_ok=True)

    # Avoid spurious HF symlink warnings on Windows
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    from huggingface_hub import hf_hub_download

    # ── 1. LLM (GGUF via llama-cpp-python) ───────────────────────────────────
    from llama_cpp import Llama

    logger.info("=" * 60)
    logger.info("[1/4] LLM — %s / %s", settings.llm_gguf_repo, settings.llm_gguf_filename)
    logger.info("      Downloading / checking cache (tqdm bar below)...")

    gguf_path = hf_hub_download(
        repo_id=settings.llm_gguf_repo,
        filename=settings.llm_gguf_filename,
        cache_dir=str(cache),
    )

    n_threads = settings.llm_n_threads or (os.cpu_count() or 4)
    logger.info("      Loading into RAM with %d threads...", n_threads)

    _llm = Llama(
        model_path=gguf_path,
        n_ctx=settings.llm_n_ctx,
        n_threads=n_threads,
        verbose=False,
    )
    logger.info("      LLM ready. (%s)", settings.llm_gguf_filename)

    # ── 2. Text embeddings (sentence-transformers) ────────────────────────────
    from sentence_transformers import SentenceTransformer

    logger.info("[2/4] Embeddings — %s", settings.embed_model_id)
    logger.info("      Downloading / checking cache...")

    _embedder = SentenceTransformer(
        settings.embed_model_id,
        cache_folder=str(cache),
    )
    logger.info("      Embeddings ready.")

    # ── 3. BLIP image captioning (fast CPU-friendly transformer) ─────────────
    from transformers import BlipForConditionalGeneration, BlipProcessor

    logger.info("[3/4] BLIP — %s", settings.blip_model_id)
    logger.info("      Downloading / checking cache...")

    _blip_processor = BlipProcessor.from_pretrained(
        settings.blip_model_id,
        cache_dir=str(cache),
    )
    _blip_model = BlipForConditionalGeneration.from_pretrained(
        settings.blip_model_id,
        cache_dir=str(cache),
    )
    _blip_model.eval()
    logger.info("      BLIP ready.")

    # ── 4. CLIP multilingual (visual ↔ text in shared space) ──────────────────
    from transformers import CLIPModel, CLIPProcessor

    logger.info("[4/4] CLIP multilingual — text: %s, image: %s",
                settings.clip_model_id, settings.clip_image_model_id)
    logger.info("      Downloading / checking cache...")

    _clip_text = SentenceTransformer(
        settings.clip_model_id,
        cache_folder=str(cache),
    )
    _clip_image_processor = CLIPProcessor.from_pretrained(
        settings.clip_image_model_id,
        cache_dir=str(cache),
    )
    _clip_image_model = CLIPModel.from_pretrained(
        settings.clip_image_model_id,
        cache_dir=str(cache),
    )
    _clip_image_model.eval()
    logger.info("      CLIP ready.")

    logger.info("=" * 60)
    logger.info("All models loaded. Server is starting...")
    logger.info("      (OCR uses pytesseract — no model download needed)")
    logger.info("=" * 60)


async def download_and_load_all() -> None:
    """Async entry point — runs blocking model loading in a thread pool."""
    await asyncio.to_thread(_load_all_sync)


def get_llm() -> Any:
    if _llm is None:
        raise RuntimeError("LLM not loaded — call download_and_load_all() first")
    return _llm


def get_embedder() -> Any:
    if _embedder is None:
        raise RuntimeError("Embedder not loaded — call download_and_load_all() first")
    return _embedder


def get_blip() -> tuple[Any, Any]:
    """Returns (processor, model) for BLIP image captioning."""
    if _blip_processor is None or _blip_model is None:
        raise RuntimeError("BLIP not loaded — call download_and_load_all() first")
    return _blip_processor, _blip_model


def get_clip_text() -> Any:
    if _clip_text is None:
        raise RuntimeError("CLIP text encoder not loaded — call download_and_load_all() first")
    return _clip_text


def get_clip_image() -> tuple[Any, Any]:
    """Returns (processor, model) for the OpenAI CLIP vision encoder."""
    if _clip_image_model is None or _clip_image_processor is None:
        raise RuntimeError("CLIP image encoder not loaded — call download_and_load_all() first")
    return _clip_image_processor, _clip_image_model


def models_loaded() -> bool:
    return all(
        x is not None
        for x in (
            _llm, _embedder, _blip_processor, _blip_model,
            _clip_text, _clip_image_model, _clip_image_processor,
        )
    )
