"""
Loads models from local cache at startup.
Run `python download_models.py` first to download them.

All LLM inference must go through inference_queue (app.utils.inference_queue).
"""

import logging
import os
from pathlib import Path
from typing import Any
import asyncio

logger = logging.getLogger(__name__)

_llm: Any = None
_embedder: Any = None


def _load_all_sync() -> None:
    global _llm, _embedder

    from app.config import settings

    cache = Path(settings.hf_cache_dir)
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    from huggingface_hub import hf_hub_download
    from llama_cpp import Llama

    logger.info("=" * 60)
    logger.info("[1/2] LLM+Visión — %s", settings.llm_gguf_repo)

    try:
        gguf_path = hf_hub_download(
            repo_id=settings.llm_gguf_repo,
            filename=settings.llm_gguf_filename,
            cache_dir=str(cache),
            local_files_only=True,
        )
        mmproj_path = hf_hub_download(
            repo_id=settings.llm_gguf_repo,
            filename=settings.llm_mmproj_filename,
            cache_dir=str(cache),
            local_files_only=True,
        )
    except Exception:
        raise RuntimeError(
            "Modelos no encontrados en caché local. "
            "Ejecuta primero: python download_models.py"
        )

    logger.info("      GGUF:   %s", gguf_path)
    logger.info("      mmproj: %s", mmproj_path)

    total_cores = os.cpu_count() or 4
    n_threads = settings.llm_n_threads or max(1, total_cores - 2)
    logger.info(
        "      Hilos de inferencia: %d (%d cores totales, 2 reservados al SO)",
        n_threads, total_cores,
    )

    _llm = Llama(
        model_path=gguf_path,
        clip_model_path=mmproj_path,
        n_ctx=settings.llm_n_ctx,
        n_batch=512,
        n_threads=n_threads,
        n_threads_batch=n_threads,
        use_mmap=False,
        use_mlock=True,
        verbose=False,
    )
    logger.info("      Gemma-4 (LLM + visión) listo.")

    from sentence_transformers import SentenceTransformer

    logger.info("[2/2] Embeddings — %s", settings.embed_model_id)

    embed_path = cache / "bge-m3"
    if not (embed_path / "config.json").exists():
        raise RuntimeError(
            "Modelo de embeddings no encontrado en caché local. "
            "Ejecuta primero: python download_models.py"
        )

    _embedder = SentenceTransformer(str(embed_path), device="cpu")

    test_vec = _embedder.encode("test", normalize_embeddings=True)
    actual_dim = len(test_vec)
    if actual_dim != settings.embedding_dims:
        raise RuntimeError(
            f"BGE-M3 produjo vectores de {actual_dim} dims pero config espera "
            f"{settings.embedding_dims}."
        )
    logger.info("      BGE-M3 listo (%d dims).", actual_dim)
    logger.info("=" * 60)
    logger.info("Todos los modelos cargados.")
    logger.info("=" * 60)


async def download_and_load_all() -> None:
    await asyncio.to_thread(_load_all_sync)


def get_llm() -> Any:
    if _llm is None:
        raise RuntimeError("LLM no cargado — ejecuta python download_models.py primero")
    return _llm


def get_embedder() -> Any:
    if _embedder is None:
        raise RuntimeError("Embedder no cargado — ejecuta python download_models.py primero")
    return _embedder


def models_loaded() -> bool:
    return _llm is not None and _embedder is not None
