"""
Loads models from local cache at startup.
Run `python download_models.py` first to download them.

All LLM inference must go through inference_queue (app.utils.inference_queue).
The reranker (cross-encoder) runs outside the queue — it is fast and CPU-orthogonal.
"""

import logging
import os
from pathlib import Path
from typing import Any
import asyncio

logger = logging.getLogger(__name__)

_vision_llm: Any = None   # Gemma-4 multimodal — SOLO captioning durante ingesta
_chat_llm: Any = None     # Llama-3.2-3B texto puro — SOLO generación de respuestas RAG
_embedder: Any = None     # BGE-M3
_reranker: Any = None     # BGE-reranker-v2-m3


def _resolve_device(settings: Any) -> str:
    """Resuelve el dispositivo de inferencia desde settings.

    "auto"  → usa CUDA si torch lo detecta, si no CPU.
    "cuda"  → CUDA explícito (falla en arranque si no hay GPU).
    "cpu"   → CPU siempre.
    """
    dev = settings.inference_device.lower()
    if dev == "auto":
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    return dev  # "cpu" | "cuda"


def _load_all_sync() -> None:
    global _vision_llm, _chat_llm, _embedder, _reranker

    from app.config import settings

    cache = Path(settings.hf_cache_dir)
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    from huggingface_hub import hf_hub_download
    from llama_cpp import Llama

    device = _resolve_device(settings)
    n_gpu_layers = settings.llm_n_gpu_layers if device == "cuda" else 0

    total_cores = os.cpu_count() or 4
    n_threads = settings.llm_n_threads or max(1, total_cores - 2)

    logger.info("=" * 60)
    if device == "cuda":
        logger.info("⚡ Dispositivo de inferencia: CUDA (n_gpu_layers=%d)", n_gpu_layers)
    else:
        logger.info("💻 Dispositivo de inferencia: CPU")
    logger.info("[1/4] LLM Visión (Gemma-4) — %s", settings.llm_gguf_repo)

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
            "Gemma-4 no encontrado en caché local. "
            "Ejecuta primero: python download_models.py"
        )

    logger.info("      GGUF:   %s", gguf_path)
    logger.info("      mmproj: %s", mmproj_path)
    logger.info("      Hilos: %d (%d cores, 2 reservados al SO)", n_threads, total_cores)

    # El shorthand clip_model_path en Llama() NO conecta el proyector multimodal
    # (en llama-cpp-python 0.3.x ni siquiera es un kwarg válido: se ignora y las
    # imágenes se descartan). Hay que pasar un chat_handler explícito que cargue
    # el mmproj y renderice la plantilla de turnos de Gemma.
    from app.utils.gemma_vision_handler import make_gemma4_handler

    vision_handler = make_gemma4_handler()(
        clip_model_path=mmproj_path,
        verbose=False,
    )

    _vision_llm = Llama(
        model_path=gguf_path,
        chat_handler=vision_handler,
        n_ctx=settings.llm_n_ctx,
        n_batch=2048,        # mismo que el chat — prefill en un solo lote para imágenes de 272 tokens
        n_threads=n_threads,
        n_threads_batch=n_threads,
        n_gpu_layers=n_gpu_layers,  # 0 en CPU, -1 (todas) en CUDA
        use_mmap=False,
        use_mlock=True,
        verbose=False,
    )
    logger.info("      Gemma-4 (visión) listo.")

    logger.info("[2/4] LLM Chat (Llama-3.2-3B) — %s", settings.chat_gguf_repo)

    try:
        chat_path = hf_hub_download(
            repo_id=settings.chat_gguf_repo,
            filename=settings.chat_gguf_filename,
            cache_dir=str(cache),
            local_files_only=True,
        )
    except Exception:
        raise RuntimeError(
            "Llama-3.2-3B no encontrado en caché local. "
            "Ejecuta primero: python download_models.py"
        )

    logger.info("      GGUF: %s", chat_path)
    logger.info("      Hilos: %d", n_threads)

    _chat_llm = Llama(
        model_path=chat_path,
        n_ctx=settings.chat_n_ctx,
        n_batch=2048,   # prefill en menos lotes -> mejor throughput (menor TTFT)
        n_threads=n_threads,
        n_threads_batch=n_threads,
        n_gpu_layers=n_gpu_layers,  # 0 en CPU, -1 (todas) en CUDA
        use_mmap=False,
        use_mlock=True,
        verbose=False,
    )
    logger.info("      Llama-3.2-3B (chat) listo.")

    from sentence_transformers import SentenceTransformer

    logger.info("[3/4] Embeddings — %s", settings.embed_model_id)

    embed_path = cache / "bge-m3"
    if not (embed_path / "config.json").exists():
        raise RuntimeError(
            "BGE-M3 no encontrado en caché local. "
            "Ejecuta primero: python download_models.py"
        )

    _embedder = SentenceTransformer(str(embed_path), device=device)

    test_vec = _embedder.encode("test", normalize_embeddings=True)
    actual_dim = len(test_vec)
    if actual_dim != settings.embedding_dims:
        raise RuntimeError(
            f"BGE-M3 produjo vectores de {actual_dim} dims pero config espera "
            f"{settings.embedding_dims}."
        )
    logger.info("      BGE-M3 listo (%d dims).", actual_dim)

    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    logger.info("[4/4] Reranker — %s", settings.reranker_model_id)

    reranker_path = cache / "bge-reranker-v2-m3"
    if not (reranker_path / "config.json").exists():
        raise RuntimeError(
            "BGE-reranker-v2-m3 no encontrado en caché local. "
            "Ejecuta primero: python download_models.py"
        )

    reranker_tokenizer = AutoTokenizer.from_pretrained(str(reranker_path))
    # En GPU usamos fp16 si reranker_use_fp16=True (menos VRAM, más rápido).
    # En CPU siempre float32 (fp16 no tiene ventaja en CPU).
    rerank_dtype = (
        torch.float16
        if (device == "cuda" and settings.reranker_use_fp16)
        else torch.float32
    )
    reranker_model = AutoModelForSequenceClassification.from_pretrained(
        str(reranker_path), torch_dtype=rerank_dtype
    ).to(device)
    reranker_model.eval()
    _reranker = (reranker_tokenizer, reranker_model)
    logger.info("      BGE-reranker-v2-m3 listo.")

    logger.info("=" * 60)
    logger.info("Todos los modelos cargados (visión + chat + embedder + reranker).")
    logger.info("=" * 60)


async def download_and_load_all() -> None:
    await asyncio.to_thread(_load_all_sync)


def get_vision_llm() -> Any:
    if _vision_llm is None:
        raise RuntimeError("LLM de visión no cargado — ejecuta python download_models.py primero")
    return _vision_llm


def get_chat_llm() -> Any:
    if _chat_llm is None:
        raise RuntimeError("LLM de chat no cargado — ejecuta python download_models.py primero")
    return _chat_llm


def get_embedder() -> Any:
    if _embedder is None:
        raise RuntimeError("Embedder no cargado — ejecuta python download_models.py primero")
    return _embedder


def get_reranker() -> Any:
    if _reranker is None:
        raise RuntimeError("Reranker no cargado — ejecuta python download_models.py primero")
    return _reranker


def models_loaded() -> bool:
    return (
        _vision_llm is not None
        and _chat_llm is not None
        and _embedder is not None
        and _reranker is not None
    )
