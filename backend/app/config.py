from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Local embedded Qdrant path (no Docker needed)
    qdrant_path: str = "./data/qdrant"

    # Local filesystem storage path
    storage_path: str = "./data/storage"

    sqlite_path: str = "./data/db.sqlite"

    # HuggingFace model identifiers
    hf_cache_dir: str = "./models_cache"

    # LLM (text-only) — used for chat answers
    llm_gguf_repo: str = "bartowski/Qwen2.5-1.5B-Instruct-GGUF"
    llm_gguf_filename: str = "Qwen2.5-1.5B-Instruct-Q4_K_M.gguf"

    # Text embeddings — used for the document text and image-description chunks
    embed_model_id: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    # BLIP image captioning — fast CPU-friendly model (~450 MB, 2-5s/image)
    blip_model_id: str = "Salesforce/blip-image-captioning-base"
    blip_max_new_tokens: int = 80

    # Ingestion performance knobs
    max_images_per_doc: int = 50   # with BLIP (~3s/img) 50 imgs ≈ 2-3 min; set in .env to override
    skip_ocr: bool = False         # set to true in .env to disable RapidOCR entirely

    # CLIP-multilingual — used for direct visual ↔ text retrieval (second vector space)
    # The text encoder (multilingual) is a distilled version aligned to OpenAI's
    # CLIP image encoder, so they live in the same 512-dim space.
    clip_model_id: str = "sentence-transformers/clip-ViT-B-32-multilingual-v1"
    clip_image_model_id: str = "openai/clip-vit-base-patch32"
    clip_dims: int = 512

    # llama-cpp inference settings (text LLM)
    llm_n_ctx: int = 8192
    llm_n_threads: int = 0      # 0 = auto-detect CPU count
    llm_max_tokens: int = 1024

    # Retrieval / RAG knobs
    max_context_chunks: int = 5
    max_context_images: int = 3
    min_image_score: float = 0.45   # drop images below this absolute similarity
    image_score_gap: float = 0.80   # drop images below best_image_score * this ratio

    # Visual-query mode (relaxed filters when the query is clearly about images)
    visual_query_max_images: int = 6
    visual_query_min_image_score: float = 0.20
    rrf_k: int = 60                 # RRF constant for hybrid image fusion

    # Folder names inside storage_path
    minio_bucket_documents: str = "documents"
    minio_bucket_images: str = "images"

    qdrant_collection_text: str = "text_chunks"
    qdrant_collection_image_visual: str = "image_visual"
    embedding_dims: int = 384   # paraphrase-multilingual-MiniLM-L12-v2 = 384 dims


settings = Settings()
