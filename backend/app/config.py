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
    llm_n_ctx: int = 4096
    llm_n_threads: int = 0      # 0 = auto-detect CPU count

    # LLM de chat: Qwen3-4B GGUF — SOLO para generación de respuestas RAG (texto puro)
    qwen_gguf_repo: str = "bartowski/Qwen_Qwen3-4B-GGUF"
    qwen_gguf_filename: str = "Qwen_Qwen3-4B-Q4_K_M.gguf"
    qwen_n_ctx: int = 8192
    qwen_max_tokens: int = 1024
    qwen_temperature: float = 0.7
    qwen_top_p: float = 0.8
    qwen_top_k: int = 20
    qwen_repeat_penalty: float = 1.1
    # Antepone /no_think al system prompt para deshabilitar thinking mode de Qwen3.5
    qwen_disable_thinking: bool = True

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
    retrieval_top_k: int = 10   # chunks que se piden a ChromaDB
    rerank_top_k: int = 3       # items que pasan al prompt tras reranking (texto + imagen unificados)

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
