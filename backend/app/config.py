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

    # LLM + visión: Gemma-4 GGUF via llama-cpp-python
    llm_gguf_repo: str = "bartowski/google_gemma-4-E4B-it-GGUF"
    llm_gguf_filename: str = "google_gemma-4-E4B-it-Q4_K_M.gguf"
    # Proyector multimodal para visión (captioning de imágenes)
    llm_mmproj_filename: str = "mmproj-google_gemma-4-E4B-it-f16.gguf"

    # Embeddings: BGE-M3 — recuperación simétrica, sin prefijos query:/passage:
    embed_model_id: str = "BAAI/bge-m3"
    embedding_dims: int = 1024

    # Ingestion performance knobs
    max_images_per_doc: int = 50
    skip_ocr: bool = False

    # llama-cpp inference settings
    llm_n_ctx: int = 4096
    llm_n_threads: int = 0      # 0 = auto-detect CPU count
    llm_max_tokens: int = 1024
    llm_repeat_penalty: float = 1.3

    # Retrieval / RAG knobs
    max_context_chunks: int = 5
    max_context_images: int = 3
    min_image_score: float = 0.35
    image_score_gap: float = 0.80

    # Visual-query mode
    visual_query_max_images: int = 6
    visual_query_min_image_score: float = 0.20

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
