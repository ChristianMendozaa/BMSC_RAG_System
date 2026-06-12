import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import chat, documents, ingest, auth, admin
from app.routers import users as users_router
from app.routers import roles as roles_router
from app.routers import permissions as permissions_router
from app.routers.permissions import doc_perm_router
from app.routers import collections as collections_router
from app.routers import pg_documents as pg_documents_router
from app.routers import conversations as conversations_router
from app.schemas import HealthResponse, HealthService
from app.services import embedder, file_storage, vector_store
from app.utils.model_manager import download_and_load_all
from app.db.session import PGAsyncSessionLocal, pg_engine
from app.seed import ensure_created_by_set_null, ensure_lockout_columns, seed_initial_admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("=" * 60)
    logger.info("Bank Documentation RAG — Iniciando")
    logger.info("=" * 60)

    logger.info("[1/5] Descargando / cargando modelos (Gemma-4 visión + Llama-3.2 chat + BGE-M3 + reranker)...")
    logger.info("      Primera ejecución descarga ~8 GB — progreso abajo.")
    await download_and_load_all()

    logger.info("[2/5] Conectando a PostgreSQL y creando datos iniciales...")
    async with PGAsyncSessionLocal() as pg_db:
        await ensure_lockout_columns(pg_db)
        await ensure_created_by_set_null(pg_db)
        await seed_initial_admin(pg_db)

    logger.info("[3/5] Inicializando ChromaDB (vector store embebido)...")
    await vector_store.ensure_collections()

    logger.info("[4/5] Verificando directorios de almacenamiento...")
    await file_storage.ensure_buckets()

    logger.info("[5/5] Inicializando caché SQLite (embeddings + respuestas)...")
    from app.cache import embedding_cache, response_cache
    embedding_cache.init_db(settings.cache_dir)
    response_cache.init_db(settings.cache_dir)

    logger.info("=" * 60)
    logger.info("Servidor listo!  http://localhost:8000")
    logger.info("API docs:        http://localhost:8000/docs")
    logger.info("=" * 60)
    yield

    logger.info("Apagando servidor...")
    await pg_engine.dispose()


app = FastAPI(
    title="Bank Documentation RAG API",
    version="2.0.0",
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
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(users_router.router)
app.include_router(roles_router.router)
app.include_router(permissions_router.router)
app.include_router(doc_perm_router)
app.include_router(collections_router.router)
app.include_router(pg_documents_router.router)
app.include_router(conversations_router.router)


@app.get("/api/health", response_model=HealthResponse)
async def health():
    services: list[HealthService] = []

    chroma_ok = await vector_store.check_health()
    services.append(HealthService(
        name="chroma_embedded",
        status="ok" if chroma_ok else "error",
        detail=None if chroma_ok else f"ChromaDB no accesible en {settings.chroma_path}",
    ))

    storage_ok = await file_storage.check_health()
    services.append(HealthService(
        name="local_storage",
        status="ok" if storage_ok else "error",
        detail=None if storage_ok else f"Storage path no accesible: {settings.storage_path}",
    ))

    models_ok = await embedder.check_health()
    services.append(HealthService(
        name="hf_models",
        status="ok" if models_ok else "error",
        detail=None if models_ok else "Modelos HuggingFace no cargados",
    ))

    overall = "ok" if all(s.status == "ok" for s in services) else "degraded"
    return HealthResponse(status=overall, services=services)
