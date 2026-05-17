"""
Descarga los modelos necesarios antes de iniciar el servidor.

Uso (desde backend/ con el venv activado):
    python download_models.py

Descarga:
  [1/3] google_gemma-4-E4B-it-Q4_K_M.gguf   (~5.4 GB)
  [2/3] mmproj-google_gemma-4-E4B-it-f16.gguf (~1.0 GB)
  [3/3] BAAI/bge-m3                            (~1.1 GB)
"""

import os
import time
from pathlib import Path

# Cargar .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# Asegurar que tqdm muestre las barras de progreso
os.environ.pop("HF_HUB_DISABLE_PROGRESS_BARS", None)
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

HF_CACHE_DIR      = os.getenv("HF_CACHE_DIR",       "./models_cache")
LLM_GGUF_REPO     = os.getenv("LLM_GGUF_REPO",      "bartowski/google_gemma-4-E4B-it-GGUF")
LLM_GGUF_FILENAME = os.getenv("LLM_GGUF_FILENAME",  "google_gemma-4-E4B-it-Q4_K_M.gguf")
LLM_MMPROJ_FILE   = os.getenv("LLM_MMPROJ_FILENAME","mmproj-google_gemma-4-E4B-it-f16.gguf")
EMBED_MODEL_ID    = os.getenv("EMBED_MODEL_ID",      "BAAI/bge-m3")

cache = Path(HF_CACHE_DIR)
cache.mkdir(parents=True, exist_ok=True)


def _download_file(label: str, repo_id: str, filename: str, max_attempts: int = 8) -> str:
    """
    Descarga un archivo individual con barra de progreso y reintentos.
    Cada intento crea un cliente httpx nuevo, evitando el bug de
    'client has been closed' tras un WinError 10054.
    """
    from huggingface_hub import hf_hub_download

    print(f"\n{label}")
    print(f"  repo : {repo_id}")
    print(f"  file : {filename}", flush=True)

    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                cache_dir=str(cache),
            )
            print(f"  OK -> {path}")
            return path
        except Exception as exc:
            last_exc = exc
            wait = min(2 ** (attempt - 1), 60)
            print(f"\n  [intento {attempt}/{max_attempts}] {exc.__class__.__name__}: {exc}")
            if attempt < max_attempts:
                print(f"  Reintentando en {wait}s...", flush=True)
                time.sleep(wait)

    raise RuntimeError(
        f"No se pudo descargar '{filename}' tras {max_attempts} intentos."
    ) from last_exc


def _download_snapshot(label: str, repo_id: str, local_dir: Path, max_attempts: int = 8) -> str:
    from huggingface_hub import snapshot_download

    print(f"\n{label}")
    print(f"  repo      : {repo_id}")
    print(f"  local_dir : {local_dir}", flush=True)

    local_dir.mkdir(parents=True, exist_ok=True)
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            # local_dir descarga archivos directamente sin symlinks (compatible con Windows)
            path = snapshot_download(
                repo_id=repo_id,
                local_dir=str(local_dir),
            )
            print(f"  OK -> {path}")
            return path
        except Exception as exc:
            last_exc = exc
            wait = min(2 ** (attempt - 1), 60)
            print(f"\n  [intento {attempt}/{max_attempts}] {exc.__class__.__name__}: {exc}")
            if attempt < max_attempts:
                print(f"  Reintentando en {wait}s...", flush=True)
                time.sleep(wait)

    raise RuntimeError(
        f"No se pudo descargar el snapshot de '{repo_id}' tras {max_attempts} intentos."
    ) from last_exc


print("=" * 60)
print("  Descarga de modelos — Bank Documentation RAG")
print("=" * 60)

_download_file("[1/3] LLM principal (~5.4 GB)",    LLM_GGUF_REPO, LLM_GGUF_FILENAME)
_download_file("[2/3] Proyector multimodal (~1 GB)", LLM_GGUF_REPO, LLM_MMPROJ_FILE)
_download_snapshot("[3/3] Embeddings BGE-M3 (~1.1 GB)", EMBED_MODEL_ID, cache / "bge-m3")

print("\n" + "=" * 60)
print("  Todos los modelos descargados correctamente.")
print("  Ahora puedes iniciar el servidor:")
print("    uvicorn app.main:app --reload --port 8000")
print("=" * 60)
