from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ChromaDB embebido (reemplaza Qdrant)
    chroma_path: str = "./data/chroma"
    chroma_collection: str = "rag_content"

    # Local filesystem storage path
    storage_path: str = "./data/storage"

    # Caché SQLite (embeddings + respuestas LLM)
    cache_dir: str = "./cache"

    # HuggingFace model cache
    hf_cache_dir: str = "./models_cache"

    # LLM de visión: Gemma-4 GGUF — SOLO para captioning de imágenes durante la ingesta
    llm_gguf_repo: str = "bartowski/google_gemma-4-E4B-it-GGUF"
    llm_gguf_filename: str = "google_gemma-4-E4B-it-Q4_K_M.gguf"
    llm_mmproj_filename: str = "mmproj-google_gemma-4-E4B-it-f16.gguf"
    # ~256 tokens de imagen + ~250 de contexto de página + prompt + generación ≈ 860,
    # así que 2048 deja holgura de sobra y achica la KV cache (menos RAM, algo más rápido).
    llm_n_ctx: int = 2048
    llm_n_threads: int = 0      # 0 = auto-detect CPU count
    vision_max_tokens: int = 256    # tope de tokens por descripción de imagen (captioning)
    vision_temperature: float = 0.1  # casi determinista para captions fieles

    # LLM de chat: Llama-3.2-3B-Instruct GGUF — SOLO para generación de respuestas RAG (texto puro)
    chat_gguf_repo: str = "bartowski/Llama-3.2-3B-Instruct-GGUF"
    chat_gguf_filename: str = "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
    chat_n_ctx: int = 8192
    chat_max_tokens: int = 1024
    chat_temperature: float = 0.2   # casi determinista: máxima fidelidad al contexto
    chat_top_p: float = 0.9
    chat_top_k: int = 40
    chat_repeat_penalty: float = 1.1

    # Reranker: BGE-reranker-v2-m3 vía FlagEmbedding (cross-encoder, fuera de inference_queue)
    reranker_model_id: str = "BAAI/bge-reranker-v2-m3"
    reranker_use_fp16: bool = True

    # Embeddings: BGE-M3 — recuperación simétrica, sin prefijos query:/passage:
    embed_model_id: str = "BAAI/bge-m3"
    embedding_dims: int = 1024

    # Ingestion performance knobs
    max_images_per_doc: int = 50
    skip_ocr: bool = False

    # Retrieval knobs
    retrieval_top_k: int = 12   # candidatos que se piden a ChromaDB antes del reranking
    rerank_top_k: int = 3       # items que pasan al prompt tras reranking (texto + imagen unificados)
    rerank_max_images: int = 6  # tope de descripciones de imagen que entran al reranker (coste CPU)

    # Performance logging (off por defecto; se activan desde .env)
    chat_perf_logging: bool = False
    ingest_perf_logging: bool = False

    # Folder names inside storage_path
    minio_bucket_documents: str = "documents"
    minio_bucket_images: str = "images"

    # PostgreSQL (auth/RBAC + RAG metadata)
    database_url: str = "postgresql+asyncpg://localhost/fallback"

    # JWT
    secret_key: str = "change_in_production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # Seed de usuario inicial
    initial_admin_username: str = "admin"
    initial_admin_password: str = "admin123"


settings = Settings()
