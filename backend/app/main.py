import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import chat, documents, ingest
from app.schemas import HealthResponse, HealthService
from app.services import embedder, file_storage, vector_store
from app.utils.model_manager import download_and_load_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("=" * 60)
    logger.info("Bank Documentation RAG — Starting up")
    logger.info("=" * 60)

    logger.info("[1/4] Downloading / loading HuggingFace models...")
    logger.info("      First run downloads ~2.5 GB — progress bars shown below.")
    await download_and_load_all()

    logger.info("[2/4] Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def _migrate(sync_conn):
            cols = {
                row[1] for row in sync_conn.exec_driver_sql(
                    "PRAGMA table_info(document_images)"
                ).fetchall()
            }
            if "ocr_text" not in cols:
                sync_conn.exec_driver_sql(
                    "ALTER TABLE document_images ADD COLUMN ocr_text TEXT"
                )
                logger.info("      Migration: added document_images.ocr_text")

        await conn.run_sync(_migrate)

    logger.info("[3/4] Initializing embedded Qdrant vector store...")
    await vector_store.ensure_collections()

    logger.info("[4/4] Ensuring local storage directories...")
    await file_storage.ensure_buckets()

    logger.info("=" * 60)
    logger.info("Server ready!  http://localhost:8000")
    logger.info("API docs:      http://localhost:8000/docs")
    logger.info("=" * 60)
    yield

    logger.info("Shutting down...")
    await engine.dispose()


app = FastAPI(
    title="Bank Documentation RAG API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router)
app.include_router(documents.router)
app.include_router(chat.router)


@app.get("/api/health", response_model=HealthResponse)
async def health():
    services: list[HealthService] = []

    qdrant_ok = await vector_store.check_health()
    services.append(HealthService(
        name="qdrant_embedded",
        status="ok" if qdrant_ok else "error",
        detail=None if qdrant_ok else f"Embedded Qdrant not accessible at {settings.qdrant_path}",
    ))

    storage_ok = await file_storage.check_health()
    services.append(HealthService(
        name="local_storage",
        status="ok" if storage_ok else "error",
        detail=None if storage_ok else f"Storage path not accessible: {settings.storage_path}",
    ))

    models_ok = await embedder.check_health()
    services.append(HealthService(
        name="hf_models",
        status="ok" if models_ok else "error",
        detail=None if models_ok else "HuggingFace models not loaded",
    ))

    overall = "ok" if all(s.status == "ok" for s in services) else "degraded"
    return HealthResponse(status=overall, services=services)
