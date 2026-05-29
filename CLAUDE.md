# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**DocuMind RAG** — a self-hosted RAG system for enterprise document intelligence. Targeted at internal bank employees (Banco Mercantil Santa Cruz). All inference runs on-premise: no external AI API calls. Primary UI language is Spanish.

## Development Commands

### Backend (FastAPI)
```bash
cd backend
pip install -r requirements.txt

# One-time: download ~11 GB of model weights to ./models_cache/
python download_models.py

# Dev server
uvicorn app.main:app --reload --port 8000
# API docs: http://localhost:8000/docs
```

On startup, `app/main.py` (lifespan) auto-loads all four models, seeds the initial admin user, initializes ChromaDB, and creates storage directories. There is no separate migration step — the DB schema is in `sql/bd.sql` and tables are created on first run.

### Frontend (Next.js 16)
```bash
cd frontend
pnpm install   # uses pnpm, not npm/yarn
pnpm dev       # http://localhost:3000
```

**Important:** This project uses **Next.js 16 with React 19** — APIs, conventions, and file structure may differ from training data. Before editing frontend code, check `node_modules/next/dist/docs/` for the relevant guide.

### Environment
```bash
cd backend
cp .env.example .env
# At minimum, set DATABASE_URL and SECRET_KEY
```

Frontend: set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local`.

## Architecture

### System Layers

```
Browser → Next.js 16 frontend → FastAPI 0.115 backend
                                       ↓
                         ┌─────────────┴──────────────┐
                    PostgreSQL                    ChromaDB (embedded)
                (users, RBAC, metadata,          (HNSW, cosine, in-process)
                 conversations, chunks)
                                       ↓
                          Local Inference (CPU-only)
                          ├── Gemma-4 E4B Q4_K_M GGUF (~5.4 GB)  ← imagen captioning SOLO durante ingesta
                          ├── mmproj vision adapter (~1.0 GB)      ← proyector multimodal para Gemma
                          ├── Qwen3-4B Q4_K_M GGUF (~2.6 GB)      ← generación de texto en chat RAG
                          ├── BGE-M3 embeddings, 1024-d (~1.1 GB)  ← embeddings de chunks y queries
                          └── BGE-reranker-v2-m3 (~1.1 GB)         ← reranking cross-encoder
```

### Responsabilidades de cada modelo

| Modelo | Responsabilidad | Usado en |
|--------|----------------|----------|
| Gemma-4 E4B (visión) | Captioning de imágenes durante ingesta | `services/embedder.py` → `describe_image()` |
| Qwen3-4B (texto) | Generación de respuestas RAG | `services/rag.py` → `stream_chat()` |
| BGE-M3 | Embeddings de chunks y queries | `services/embedder.py` → `embed_text()` |
| BGE-reranker-v2-m3 | Reranking cross-encoder (top-10 → top-3) | `services/reranker.py` → `rerank()` |

**La cola de inferencia (`inference_queue`, `asyncio.Semaphore(1)`) es compartida entre Gemma-4 y Qwen3. El reranker corre fuera de la cola.**

### Document Ingestion Pipeline (`backend/app/services/`)
1. File uploaded (con o sin `collection_id`) → `file_storage.py` saves to `./data/storage/documents/`. Documentos sin colección quedan en estado "Sin asignar" hasta que un admin los mueva.
2. Format parser (`services/parsers/`) extracts text blocks and embedded images
3. Images saved to `./data/storage/images/`, captioned by **Gemma-4 Vision** (`embedder.describe_image`)
4. Text + captions chunked by `langchain-text-splitters` (800 tokens / 150 overlap)
5. Chunks embedded by BGE-M3 (`services/embedder.py`) → cached in SQLite
6. Vectors upserted to ChromaDB (`services/vector_store.py`)
7. Metadata (chunks, image descriptions) persisted to PostgreSQL

### RAG Query Flow (`backend/app/routers/chat.py` + `services/rag.py`)
1. User message → `POST /api/chat/stream`
2. PostgreSQL: resolve permissions + load last 4 conversation turns
3. BGE-M3 embeds query → ChromaDB cosine search, **top-10 chunks**
4. PostgreSQL: fetch `document_images.description` for pages in those chunks
5. Pool unificado (chunks + descripciones de imágenes) → **BGE-reranker-v2-m3** → top-3 más relevantes
6. Request enqueued in FIFO inference queue (`utils/inference_queue.py`, `asyncio.Semaphore(1)`)
7. **Qwen3-4B** streams tokens with text context (incluyendo descripciones de imágenes como texto) → SSE to frontend
8. SSE closes with `sources` JSON payload; response persisted to PostgreSQL

> **Importante:** El LLM de chat (Qwen3-4B) es un modelo de texto puro. Solo recibe texto como contexto — las descripciones de imágenes se inyectan como bloques de texto `[Figura N: ...]` en el prompt. El modelo no procesa ni recibe píxeles en ningún momento durante el chat.

### Auth & Permissions (`backend/app/core/`, `routers/auth.py`)
- JWT HS256 with claims `sub`, `jti`, `iat`, `exp`. Token revocation works via two independent paths:
  - **Per-token**: JTI blacklist check against PostgreSQL `revoked_tokens` on every request (explicit logout).
  - **Per-user**: `users.tokens_valid_after TIMESTAMPTZ`. Set to `NOW()` on password reset or user reactivation. Any JWT with `iat < tokens_valid_after` is rejected with 401 — invalidates all active sessions without a per-user JTI list.
- Login rejects users with `role_id IS NULL` (orphaned when their role was deleted) with 403 "Su cuenta no tiene rol asignado."
- Two-tier access control: Role-level defaults + per-document/collection ACL rows
- Resolution order: explicit user permission → role permission → collection membership → deny

### Key Design Decisions
- **Separación de responsabilidades entre LLMs**: Gemma-4 (multimodal) solo capcionea imágenes durante la ingesta. Qwen3-4B (texto puro) solo genera respuestas en el chat. Esto evita cargar el contexto del chat con bytes de imagen y reduce la latencia de prefill.
- **Reranker entre ChromaDB y el LLM**: BGE-reranker-v2-m3 (cross-encoder) recibe el pool de top-10 chunks + descripciones de imágenes y selecciona los 3 más relevantes. Mejora la calidad del contexto sin aumentar el tamaño del prompt.
- **ChromaDB is embedded** (in-process, no external service). It initializes with the app and persists to `./data/chroma/`.
- **Semaphore = 1 compartido**: Gemma-4 y Qwen3 comparten la misma cola FIFO para no contender en cores. El reranker (cross-encoder ligero) corre fuera de la cola.
- **Dual SQLite caches** in `./data/`: one for embedding vectors (keyed by content hash), one for LLM responses. Re-ingesting a seen document skips embedding.
- **BGE-M3 symmetric mode**: no `query:`/`passage:` instruction prefixes needed; simplifies the embed pipeline and supports multilingual docs.
- **SSE not WebSockets**: unidirectional token stream from server to client — simpler connection management.
- **All DB/file I/O is async** (`asyncpg`, `aiofiles`); CPU-bound inference dispatched via `run_in_executor`.
- **Qwen3 thinking mode disabled**: `/no_think` prepended to the system prompt + sampling params (temp=0.7, top_p=0.8, top_k=20) configured for non-thinking mode. The empty `<think></think>` tokens Qwen3 still emits are filtered in `stream_chat` before reaching the SSE stream.
- **FKs nullables con `ON DELETE SET NULL`**: `documents.collection_id` y `users.role_id` aceptan NULL. Un documento sin colección o un usuario sin rol son estados válidos — no errores. Borrar una colección o un rol no rompe filas dependientes; quedan huérfanas y el admin las reasigna desde el panel.
- **Hard delete centralizado**: `services/hard_delete.py::hard_delete_document(doc_id)` purga en orden: vectores ChromaDB, archivos físicos (original + imágenes vía `file_storage`), fila `rag_documents` (CASCADE limpia chunks/images/figures) y fila `documents` (CASCADE limpia versiones/permisos). No commitea — el caller gestiona la transacción. Usado por `DELETE /api/pg-documents/{id}/permanent` y `DELETE /api/collections/{id}?action=delete`.

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/main.py` | App factory, lifespan events (model load, DB/ChromaDB init) |
| `backend/app/config.py` | All env vars via Pydantic Settings |
| `backend/app/schemas.py` | All Pydantic request/response models |
| `backend/app/dependencies.py` | FastAPI dependency injection (auth, DB session, model access) |
| `backend/app/services/rag.py` | RAG orchestration: retrieval, reranking, prompt building, streaming |
| `backend/app/services/reranker.py` | BGE cross-encoder reranker wrapper (transformers, runs outside inference_queue) |
| `backend/app/utils/inference_queue.py` | FIFO LLM concurrency control (shared by Gemma + Qwen) |
| `backend/app/utils/model_manager.py` | Loads and exposes all four models; `get_vision_llm()`, `get_chat_llm()`, `get_reranker()`, `get_embedder()` |
| `frontend/lib/api.ts` | Typed API client (all backend calls go through here) |
| `frontend/lib/auth-context.tsx` | React auth state and token lifecycle |
| `backend/sql/bd.sql` | Full PostgreSQL schema |
| `backend/app/services/hard_delete.py` | Hard delete completo de un documento: Chroma + archivos físicos + Postgres (CASCADE). Sin commit propio. |
| `backend/app/routers/pg_documents.py` | CRUD documentos: upload con/sin colección, patch, reactivate, soft/permanent delete, GET con filtros. |
| `backend/app/routers/collections.py` | Colecciones: `DELETE ?action=auto\|obsolete\|delete` — auto devuelve 409 si hay docs, obsolete los deja huérfanos, delete los purga. |
| `backend/app/routers/users.py` | Gestión de usuarios: `POST /{id}/activate`, `POST /{id}/reset-password`, `PATCH /{id}/role`. |

## Admin Endpoints Reference

Endpoints del panel de administración agregados en el overhaul (permisos mínimos indicados entre paréntesis):

| Endpoint | Comportamiento |
|---|---|
| `GET /api/pg-documents` | Filtros query: `search`, `collection_id`, `status`, `uncategorized=true`, `sort=newest\|oldest_obsolete\|name`. |
| `POST /api/pg-documents/upload` | `collection_id` opcional via form-data. Vacío → documento "Sin asignar" (`collection_id=NULL`). |
| `PATCH /api/pg-documents/{id}` | Actualiza `title` y/o `collection_id`. `clear_collection=true` la pone en NULL. (`can_upload_documents`) |
| `POST /api/pg-documents/{id}/reactivate` | OBSOLETE → ACTIVE. Si quedó sin colección, se mantiene "Sin asignar". (`can_upload_documents`) |
| `DELETE /api/pg-documents/{id}` | Soft delete: marca OBSOLETE. Sigue siendo descargable. (`can_delete_documents`) |
| `DELETE /api/pg-documents/{id}/permanent` | Hard delete completo. Requiere `status=OBSOLETE`. (`can_delete_documents`) |
| `DELETE /api/collections/{id}?action=auto` | 409 con `{has_documents, count}` si tiene documentos. Sin docs → hard delete directo. |
| `DELETE /api/collections/{id}?action=obsolete` | Docs → OBSOLETE + `collection_id=NULL`, luego hard delete de la colección. |
| `DELETE /api/collections/{id}?action=delete` | Hard delete completo de todos los docs y la colección. |
| `DELETE /api/roles/{id}` | Elimina el rol aunque tenga usuarios asignados (quedan con `role_id=NULL`). Bloquea solo `is_system=true`. Respuesta: `{deleted, affected_users}`. |
| `POST /api/users/{id}/activate` | `is_active=true` + `tokens_valid_after=NOW()`. (`can_manage_users`) |
| `POST /api/users/{id}/reset-password` | Reset por admin (no requiere contraseña anterior). `tokens_valid_after=NOW()` → invalida todas las sesiones. (`can_manage_users`) |
| `PATCH /api/users/{id}/role` | Asigna o quita rol. Acepta `{role_id: UUID\|null}`. (`can_manage_users`) |

## Environment Variables Reference

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/docmind` |
| `SECRET_KEY` | JWT signing secret (min 32 bytes) |
| `STORAGE_PATH` | Root for document/image files (default: `./data/storage`) |
| `CHROMA_PATH` | ChromaDB persistence dir (default: `./data/chroma`) |
| `HF_CACHE_DIR` | Model weights cache (default: `./models_cache`) |
| `LLM_GGUF_REPO` / `LLM_GGUF_FILENAME` / `LLM_MMPROJ_FILENAME` | Gemma-4 vision model (captioning) |
| `LLM_N_CTX` | Gemma-4 context window in tokens (default: 4096) |
| `LLM_N_THREADS` | CPU threads for inference (`0` = auto-detect) |
| `QWEN_GGUF_REPO` / `QWEN_GGUF_FILENAME` | Qwen3-4B chat model |
| `QWEN_N_CTX` | Qwen3 context window (default: 8192) |
| `QWEN_MAX_TOKENS` | Max tokens per chat response (default: 1024) |
| `QWEN_TEMPERATURE` / `QWEN_TOP_P` / `QWEN_TOP_K` | Qwen3 sampling params (default: 0.7 / 0.8 / 20) |
| `QWEN_DISABLE_THINKING` | Prepend `/no_think` to system prompt (default: true) |
| `RERANKER_MODEL_ID` | BGE reranker HF ID (default: `BAAI/bge-reranker-v2-m3`) |
| `RETRIEVAL_TOP_K` | Chunks fetched from ChromaDB before reranking (default: 10) |
| `RERANK_TOP_K` | Items passed to the LLM after reranking (default: 3) |
| `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD` | Seeded on first startup |
| `CHAT_PERF_LOGGING` | Si `true`, emite logs `[chat-perf]` con tiempos por etapa del chat (embedding, search, rerank, espera en cola, prefill/TTFT, tok/s). Default `false`. |
| `INGEST_PERF_LOGGING` | Si `true`, emite logs `[ingest-perf]` con tiempos por paso de la ingesta (parse, subida/descripción de imágenes con Gemma, embedding batch, upsert ChromaDB, escrituras Postgres). Default `false`. |
