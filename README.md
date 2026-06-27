# BMSC Knowledge Base

> Self-hosted Retrieval-Augmented Generation (RAG) for internal document intelligence at Banco Mercantil Santa Cruz — query PDFs, spreadsheets, presentations, and other documents through a conversational interface powered entirely by on-premise AI inference.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16.2-000000?logo=next.js&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white)
![ChromaDB](https://img.shields.io/badge/ChromaDB-0.5-FF6B35)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Overview

BMSC Knowledge Base is a self-hosted document intelligence platform that ingests organizational documents and makes them queryable through natural language. Targeted at internal bank employees, the system combines dense vector retrieval, cross-encoder reranking, and a quantized language model to answer questions grounded strictly in the uploaded knowledge base — including visual content extracted from figures and diagrams.

The entire stack runs on-premise with **no external API dependencies**. All inference is CPU-only. The UI language is Spanish.

The inference layer uses a **dual-model architecture**:
- **Gemma-4 E4B Q4\_K\_M** (vision/multimodal, via `llama-cpp-python`) — image captioning **during ingestion only**.
- **Llama-3.2-3B-Instruct Q4\_K\_M** (text-only, via `llama-cpp-python`) — RAG answer generation **during chat only**.
- **BGE-reranker-v2-m3** — cross-encoder reranking of the retrieval pool before it reaches the LLM.
- **BGE-M3** — symmetric 1024-d embeddings via `sentence-transformers`.

Vectors are persisted in an embedded **ChromaDB** instance (HNSW, cosine). A hybrid RBAC + per-document ACL model controls which users and roles can view, download, or chat over specific documents and collections.

---

## System Architecture

```mermaid
graph TD
    subgraph Client
        U[User Browser]
    end

    subgraph Frontend["Frontend — Next.js 16 / React 19"]
        FE_CHAT[Chat Interface]
        FE_ADMIN[Admin Panel]
        FE_DOCS[Document Library]
    end

    subgraph API["API Server — FastAPI 0.115 (ASGI / asyncpg)"]
        AUTH[Auth Router\nJWT HS256 + bcrypt]
        CHAT_R[Chat Router\nSSE Streaming]
        INGEST_R[Ingest Router\nBackground Task]
        DOC_R[pg-documents / documents]
        PERM_R[Permissions Router]
        CONV_R[Conversations Router]
        HEALTH[GET /api/health]
    end

    subgraph Inference["Local Inference — CPU only"]
        QUEUE[FIFO Inference Queue\nasyncio.Semaphore 1]
        GEMMA[Gemma-4 E4B Q4_K_M\nimage captioning · ingest only]
        LLAMA[Llama-3.2-3B Q4_K_M\nchat text generation]
        EMBED[BGE-M3 · 1024-d\nsentence-transformers]
        RERANK[BGE-reranker-v2-m3\ncross-encoder · outside queue]
    end

    subgraph Storage["Persistence"]
        PG[(PostgreSQL\nAuth · RBAC · RAG metadata)]
        CHROMA[(ChromaDB embedded\nHNSW · cosine · rag_content)]
        FS[Local Filesystem\ndata/storage/documents\ndata/storage/images]
        EMBC[(SQLite — embeddings.db\nTTL 30 days)]
        RESPC[(SQLite — responses.db\nTTL 24 hours)]
    end

    U --> FE_CHAT & FE_ADMIN & FE_DOCS
    FE_CHAT --> CHAT_R & CONV_R
    FE_DOCS --> INGEST_R & DOC_R
    FE_ADMIN --> AUTH & PERM_R

    INGEST_R --> QUEUE --> GEMMA
    CHAT_R --> QUEUE --> LLAMA
    CHAT_R --> RERANK
    INGEST_R --> EMBED
    CHAT_R --> EMBED
    EMBED --> EMBC
    CHAT_R --> RESPC

    CHAT_R & INGEST_R --> CHROMA
    INGEST_R --> FS

    AUTH & CHAT_R & INGEST_R & DOC_R & PERM_R & CONV_R --> PG
```

---

## Models & Responsibilities

| Model | Role | Loaded in ingestion? | Loaded in chat? | Engine | Getter |
|-------|------|:--------------------:|:---------------:|--------|--------|
| **Gemma-4 E4B-it Q4\_K\_M GGUF** + mmproj f16 | Image captioning (Spanish descriptions of figures/diagrams) | ✅ via inference queue | ❌ | `llama_cpp.Llama` + custom handler | `get_vision_llm()` |
| **Llama-3.2-3B-Instruct Q4\_K\_M GGUF** | RAG answer generation (text-only; receives no image pixels) | ❌ | ✅ via inference queue | `llama_cpp.Llama` | `get_chat_llm()` |
| **BGE-M3** (1024-d, symmetric) | Embedding chunks at ingest; embedding queries at chat | ✅ | ✅ | `sentence_transformers.SentenceTransformer` | `get_embedder()` |
| **BGE-reranker-v2-m3** | Cross-encoder re-scoring of retrieved pool (top-12 → top-3) | ❌ | ✅ **outside queue** | `transformers.AutoModelForSequenceClassification` | `get_reranker()` |

**Inference queue** (`utils/inference_queue.py`): a module-level `asyncio.Semaphore(1)` serializes all GGUF model calls — Gemma captioning (ingest) and Llama chat (chat) share this single FIFO queue. The reranker and BGE-M3 embedder run concurrently, outside the queue.

All models load from local HF cache (`models_cache/`) at startup. First run requires `python download_models.py` (~8 GB download).

---

## Document Ingestion Pipeline

Triggered by `POST /api/ingest` as a FastAPI `BackgroundTask`. Cancellable via `cancel_pipeline()`. Source: `services/ingest_pipeline.py`.

```mermaid
flowchart LR
    A([File Upload\n≤200 MB]) --> B[Store original\ndata/storage/documents/\ndoc_id/filename]
    B --> C{Format Parser}
    C -->|.pdf| D[PyMuPDF\npdfplumber]
    C -->|.docx| E[python-docx]
    C -->|.pptx| F[python-pptx]
    C -->|.xlsx| G[openpyxl]
    C -->|.txt .md| H[plain text decode]
    C -->|image| I[Pillow]
    D & E & F & G & H & I --> J[TextBlocks + ImageBlocks\n+ figure-caption regex]
    J --> K[Upload images\ndata/storage/images/\nmax 50 per doc]
    K --> L[Caption images\nGemma-4 Vision\nsequential · via queue\nvision_max_tokens=256\ntemp=0.1]
    L --> M[Store captions in PostgreSQL\ndocument_images.description]
    M --> N[Merge text + image markers\nper page by y-position\nIMG:uuid markers]
    N --> O[Chunk\nRecursiveCharacterTextSplitter\nsize=800 · overlap=150]
    O --> P[Embed\nBGE-M3 batch_size=32\nnot cached at batch level]
    P --> Q[(ChromaDB upsert\nid: doc_id_chunk_index\ncosine HNSW)]
    P --> R[(PostgreSQL\nchunks + images + figures)]
    Q & R --> S([Status: ready])
```

**Supported formats:** `.pdf` · `.docx` · `.pptx` · `.xlsx` · `.txt` · `.md` · `.jpg` · `.jpeg` · `.png` · `.webp`

**Status progression:** `pending` → `processing` → `indexing_images` → `ready` (or `error`)

**Key parameters:**
- `max_images_per_doc` = 50 (capped; configurable)
- Chunk size = 800 chars, overlap = 150 chars
- Vision captioning: Spanish prompt, 256 max tokens, temperature 0.1 (near-deterministic)
- Batch embedding NOT cached; single-query embedding (chat path) IS SQLite-cached

---

## RAG Query Flow

`POST /api/chat` returns an SSE stream. Sources: `routers/chat.py`, `services/rag.py`, `services/reranker.py`.

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend
    participant API as FastAPI
    participant PG as PostgreSQL
    participant CACHE as SQLite Cache
    participant EMB as BGE-M3
    participant VDB as ChromaDB
    participant RR as BGE-reranker-v2-m3
    participant Q as Inference Queue
    participant LLM as Llama-3.2-3B

    User->>FE: Send message
    FE->>API: POST /api/chat (SSE)
    API->>PG: Resolve session + can_chat ACL
    API->>PG: Load history + persist user turn
    API->>CACHE: Lookup response cache (query hash, TTL 24h)
    alt Cache hit
        CACHE-->>API: Cached response + sources
        API-->>FE: SSE token stream (from_cache=true) + done
    else Cache miss
        API->>EMB: Embed query (SQLite-cached single-query)
        EMB-->>API: 1024-d vector
        API->>VDB: Cosine search — top retrieval_top_k=12
        VDB-->>API: Chunks + scores
        API->>PG: Fetch image descriptions for retrieved pages (cap rerank_max_images=6)
        PG-->>API: document_images.description rows
        API->>RR: Rerank unified pool (text chunks + image descriptions) — OUTSIDE queue
        RR-->>API: Top rerank_top_k=3 items
        API->>Q: Acquire inference queue (Semaphore 1 — FIFO)
        Q->>LLM: Spanish system prompt + context + last 2 history turns + query
        loop Token stream
            LLM-->>API: Token
            API-->>FE: SSE: {type: "token"}
        end
        API-->>FE: SSE: {type: "done", session_id, sources, from_cache: false}
        API->>PG: Persist assistant turn + sources_json
        API->>CACHE: Populate response cache
    end
    FE-->>User: Rendered response + source panel
```

**LLM sampling parameters** (Llama-3.2-3B): `chat_max_tokens=1024`, `temperature=0.2`, `top_p=0.9`, `top_k=40`, `repeat_penalty=1.1`.
Stop tokens: `<|eot_id|>`, `<|end_of_text|>`, `Usuario:`, `\nUser:`

> The chat LLM (Llama-3.2-3B) is text-only. Image descriptions are injected as `[Figura N: ...]` text blocks in the prompt. The model never receives image pixels.

---

## Auth & RBAC

Source: `routers/auth.py`, `core/security.py`, `dependencies.py`, `core/dependencies.py`, `seed.py`.

### JWT
- **Algorithm:** HS256, signed with `SECRET_KEY`.
- **Claims:** `sub` (user UUID), `jti` (random UUID), `iat`, `exp` (now + 480 min).
- **Passwords:** bcrypt.

### Login
Users log in with **email + password** (case-insensitive match on `users.email`).  
Exception: the seeded system admin (`is_system = true`) logs in with **username + password** (`users.username`). This is determined at runtime by `is_system`, not hardcoded.

### Account lockout (brute-force protection)
After `MAX_LOGIN_ATTEMPTS` consecutive failed logins (default 5), the account is locked for `LOCKOUT_MINUTES` (default 15): `users.locked_until = NOW() + LOCKOUT_MINUTES`. While locked, login returns 401 with the remaining minutes **without verifying the password**. The failure counter is incremented atomically (`UPDATE ... SET failed_login_attempts = failed_login_attempts + 1`) to avoid races between concurrent requests, and resets to 0 on successful login.

- **Exempt:** users with `is_system = true` (the seeded admin) never accumulate attempts nor lock — the system can't be left without an administrator by deliberately failing logins.
- **Auto-expiry:** the lock clears itself after `LOCKOUT_MINUTES`; no admin action required.
- **Immediate unlock:** `POST /api/users/{id}/activate` and `POST /api/users/{id}/reset-password` also clear `failed_login_attempts`/`locked_until`.
- **Migration-free:** the two columns are added idempotently at startup (`seed.py::ensure_lockout_columns`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`).

### Token revocation (two independent paths)
| Path | Mechanism |
|------|-----------|
| **Per-token (explicit logout)** | `revoked_tokens` table — logout inserts the current `jti` with its `expires_at`. Any request whose `jti` appears in this table → 401. |
| **Per-user (bulk invalidation)** | `users.tokens_valid_after TIMESTAMPTZ` — set to `NOW()` on password reset or user reactivation. Any JWT with `iat < tokens_valid_after` → 401, invalidating all active sessions without a per-token list. |

### Permission model
**Role-level capabilities** (boolean flags on each role):

| Flag | Grants |
|------|--------|
| `can_manage_users` | Create/edit/deactivate users, assign roles, reset passwords |
| `can_manage_collections` | Create/edit/delete collections, manage all ACLs |
| `can_upload_documents` | Upload and manage documents |
| `can_delete_documents` | Soft-delete and permanently delete documents |

**Per-document / per-collection ACLs** (three actions: `can_view`, `can_download`, `can_chat`):

Resolution precedence (highest → lowest):
```
UserDocumentPermission → RoleDocumentPermission → UserCollectionPermission → CollectionPermission → deny
```
`can_manage_collections` bypasses all ACL checks for chat scope.

**Seed roles** (created by `sql/bd.sql`, all `is_system = true`):
- `SUPERADMIN` — all four capabilities enabled.
- `ADMIN` — `can_manage_collections`, `can_upload_documents`, `can_delete_documents`.
- `VISITANTE` — no capabilities (relies entirely on ACL grants).

**Initial admin user** (created by `seed.py` on first startup when `users` table is empty): `username = INITIAL_ADMIN_USERNAME`, `email = NULL`, `is_system = true`, role = SUPERADMIN.

---

## Data Dictionary

### PostgreSQL

> **Prerequisite:** the `pgcrypto` extension must be enabled (`CREATE EXTENSION IF NOT EXISTS pgcrypto;`) — `gen_random_uuid()` requires it. The schema file `sql/bd.sql` does not create it automatically.

**Enums** (defined as PG custom types):
- `document_status`: `'ACTIVE'` | `'OBSOLETE'`
- `index_status`: `'PENDING'` | `'INDEXING'` | `'READY'` | `'ERROR'`

**Trigger function:** `fn_update_updated_at()` — `RETURNS TRIGGER LANGUAGE plpgsql`, sets `NEW.updated_at = NOW()`. Applied via `BEFORE UPDATE` triggers on: `users`, `collections`, `documents`, `rag_documents`, `chat_sessions`.

```mermaid
erDiagram
    roles {
        uuid id PK
        varchar name UK
        text description
        bool is_system
        bool can_manage_users
        bool can_manage_collections
        bool can_upload_documents
        bool can_delete_documents
        timestamptz created_at
    }
    users {
        uuid id PK
        varchar username
        varchar email UK "nullable"
        varchar hashed_password
        uuid role_id FK
        bool is_active
        bool is_system
        timestamptz tokens_valid_after "nullable"
        uuid created_by FK
        timestamptz created_at
        timestamptz updated_at
    }
    collections {
        uuid id PK
        varchar name UK
        text description
        bool is_active
        uuid created_by FK
        timestamptz created_at
        timestamptz updated_at
    }
    collection_permissions {
        uuid id PK
        uuid role_id FK
        uuid collection_id FK
        bool can_view
        bool can_download
        bool can_chat
    }
    user_collection_permissions {
        uuid id PK
        uuid user_id FK
        uuid collection_id FK
        bool can_view
        bool can_download
        bool can_chat
    }
    documents {
        uuid id PK
        varchar title
        uuid collection_id FK "nullable"
        document_status status
        uuid created_by FK
        timestamptz created_at
        timestamptz updated_at
    }
    document_versions {
        uuid id PK
        uuid document_id FK
        int version_number
        varchar original_filename
        varchar file_path
        int file_size_bytes
        varchar mime_type
        bool is_current
        index_status index_status
        text change_notes
        uuid created_by FK
        timestamptz created_at
    }
    role_document_permissions {
        uuid id PK
        uuid role_id FK
        uuid document_id FK
        bool can_view
        bool can_download
        bool can_chat
    }
    user_document_permissions {
        uuid id PK
        uuid user_id FK
        uuid document_id FK
        bool can_view
        bool can_download
        bool can_chat
    }
    revoked_tokens {
        uuid jti PK
        uuid user_id FK
        timestamptz expires_at
    }
    rag_documents {
        uuid id PK
        uuid role_id FK "nullable"
        varchar filename
        varchar original_filename
        varchar file_type
        int file_size
        varchar status
        text error_message
        int chunk_count
        int image_count
        varchar minio_path "nullable - legacy label for local FS path"
        timestamptz created_at
        timestamptz updated_at
    }
    chunks {
        uuid id PK
        uuid document_id FK
        text content
        int chunk_index
        int page_number "nullable"
        varchar chunk_type
        text metadata_json "nullable"
        timestamptz created_at
    }
    document_images {
        uuid id PK
        uuid document_id FK
        varchar minio_path "local FS path"
        int page_number "nullable"
        int image_index
        text description "nullable - Gemma caption"
        text ocr_text "nullable"
        timestamptz created_at
    }
    document_figures {
        uuid id PK
        uuid document_id FK
        int figure_number
        int page_number "nullable"
        text caption "nullable"
        timestamptz created_at
    }
    chat_sessions {
        uuid id PK
        uuid user_id FK
        varchar title
        uuid collection_id FK "nullable"
        uuid[] document_ids
        timestamptz created_at
        timestamptz updated_at
    }
    chat_messages {
        uuid id PK
        uuid session_id FK
        varchar role
        text content
        text sources_json "nullable"
        timestamptz created_at
    }

    roles ||--o{ users : "role_id"
    users ||--o{ user_collection_permissions : "user_id"
    users ||--o{ user_document_permissions : "user_id"
    users ||--o{ revoked_tokens : "user_id"
    users ||--o{ chat_sessions : "user_id"
    roles ||--o{ collection_permissions : "role_id"
    roles ||--o{ role_document_permissions : "role_id"
    roles ||--o{ rag_documents : "role_id"
    collections ||--o{ collection_permissions : "collection_id"
    collections ||--o{ user_collection_permissions : "collection_id"
    collections ||--o{ documents : "collection_id"
    collections ||--o{ chat_sessions : "collection_id"
    documents ||--o{ document_versions : "document_id"
    documents ||--o{ role_document_permissions : "document_id"
    documents ||--o{ user_document_permissions : "document_id"
    rag_documents ||--o{ chunks : "document_id"
    rag_documents ||--o{ document_images : "document_id"
    rag_documents ||--o{ document_figures : "document_id"
    chat_sessions ||--o{ chat_messages : "session_id"
```

---

#### Table: `roles`
| Column | Type | Null | Default | Notes |
|--------|------|:----:|---------|-------|
| `id` | UUID | NOT NULL | `gen_random_uuid()` | PK |
| `name` | VARCHAR(100) | NOT NULL | — | UNIQUE |
| `description` | TEXT | nullable | — | |
| `is_system` | BOOLEAN | NOT NULL | `false` | System roles cannot be deleted |
| `can_manage_users` | BOOLEAN | NOT NULL | `false` | |
| `can_manage_collections` | BOOLEAN | NOT NULL | `false` | |
| `can_upload_documents` | BOOLEAN | NOT NULL | `false` | |
| `can_delete_documents` | BOOLEAN | NOT NULL | `false` | |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |

---

#### Table: `users`
| Column | Type | Null | Default | Notes |
|--------|------|:----:|---------|-------|
| `id` | UUID | NOT NULL | `gen_random_uuid()` | PK |
| `username` | VARCHAR(100) | NOT NULL | — | Derived from `email` part before `@`; NOT unique (multiple emails can share a prefix) |
| `email` | VARCHAR(255) | nullable | — | UNIQUE; NULL for the seeded system admin; login identifier for all other users |
| `hashed_password` | VARCHAR(255) | NOT NULL | — | bcrypt |
| `role_id` | UUID | nullable | — | FK → `roles.id` ON DELETE SET NULL |
| `is_active` | BOOLEAN | NOT NULL | `true` | |
| `is_system` | BOOLEAN | NOT NULL | `false` | `true` for the seeded admin; allows username-based login |
| `tokens_valid_after` | TIMESTAMPTZ | nullable | — | JWTs with `iat` before this value are rejected |
| `failed_login_attempts` | INT | NOT NULL | `0` | Consecutive failed logins; reset on successful login or admin unlock |
| `locked_until` | TIMESTAMPTZ | nullable | — | Account locked until this time after too many failed logins; `is_system` users never lock |
| `must_change_password` | BOOLEAN | NOT NULL | `false` | Forces first-login/admin-reset password change |
| `verification_code` | VARCHAR(10) | nullable | — | Legacy compatibility only; new codes are not stored in clear text |
| `verification_code_hash` | VARCHAR(255) | nullable | — | bcrypt hash for first-login/password-reset code |
| `verification_code_expires_at` | TIMESTAMPTZ | nullable | — | Code expiry |
| `verification_code_attempts` | INT | NOT NULL | `0` | Failed code verification attempts |
| `verification_code_sent_at` | TIMESTAMPTZ | nullable | — | Last code send time for cooldown |
| `verification_code_purpose` | VARCHAR(32) | nullable | — | `first_login` or `password_reset` |
| `created_by` | UUID | nullable | — | FK → `users.id` (self-referential) |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Auto-updated by trigger |

Indexes: `idx_users_role_id` (role_id) · `idx_users_is_active` (is_active) · `idx_users_no_role` partial WHERE role_id IS NULL · `idx_users_is_system` partial WHERE is_system = true

---

#### Table: `collections`
| Column | Type | Null | Default | Notes |
|--------|------|:----:|---------|-------|
| `id` | UUID | NOT NULL | `gen_random_uuid()` | PK |
| `name` | VARCHAR(200) | NOT NULL | — | UNIQUE |
| `description` | TEXT | nullable | — | |
| `is_active` | BOOLEAN | NOT NULL | `true` | |
| `created_by` | UUID | nullable | — | FK → `users.id` |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Auto-updated by trigger |

---

#### Table: `collection_permissions`
Per-role access to a collection.

| Column | Type | Null | Default | Notes |
|--------|------|:----:|---------|-------|
| `id` | UUID | NOT NULL | `gen_random_uuid()` | PK |
| `role_id` | UUID | NOT NULL | — | FK → `roles.id` ON DELETE CASCADE |
| `collection_id` | UUID | NOT NULL | — | FK → `collections.id` ON DELETE CASCADE |
| `can_view` | BOOLEAN | NOT NULL | `false` | |
| `can_download` | BOOLEAN | NOT NULL | `false` | |
| `can_chat` | BOOLEAN | NOT NULL | `false` | |

UNIQUE constraint: `uq_role_collection` (role_id, collection_id).
Indexes: `idx_col_perms_role` · `idx_col_perms_collection`

---

#### Table: `user_collection_permissions`
Per-user override on a collection (higher priority than role-level).

| Column | Type | Null | Default | Notes |
|--------|------|:----:|---------|-------|
| `id` | UUID | NOT NULL | `gen_random_uuid()` | PK |
| `user_id` | UUID | NOT NULL | — | FK → `users.id` ON DELETE CASCADE |
| `collection_id` | UUID | NOT NULL | — | FK → `collections.id` ON DELETE CASCADE |
| `can_view` | BOOLEAN | NOT NULL | `false` | |
| `can_download` | BOOLEAN | NOT NULL | `false` | |
| `can_chat` | BOOLEAN | NOT NULL | `false` | |

UNIQUE: `uq_user_collection` (user_id, collection_id).
Indexes: `idx_user_col_perms_user` · `idx_user_col_perms_col`

---

#### Table: `documents`
Logical document record (DMS side). Physical file stored in `document_versions`.

| Column | Type | Null | Default | Notes |
|--------|------|:----:|---------|-------|
| `id` | UUID | NOT NULL | `gen_random_uuid()` | PK |
| `title` | VARCHAR(500) | NOT NULL | — | |
| `collection_id` | UUID | nullable | — | FK → `collections.id` ON DELETE SET NULL; NULL = "Sin asignar" |
| `status` | `document_status` | NOT NULL | `'ACTIVE'` | ENUM: ACTIVE \| OBSOLETE |
| `created_by` | UUID | nullable | — | FK → `users.id` |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Auto-updated by trigger |

Indexes: `idx_documents_collection` · `idx_documents_status` · `idx_documents_uncategorized` partial WHERE collection_id IS NULL

---

#### Table: `document_versions`
Physical file storage record (one or more versions per document).

| Column | Type | Null | Default | Notes |
|--------|------|:----:|---------|-------|
| `id` | UUID | NOT NULL | `gen_random_uuid()` | PK |
| `document_id` | UUID | NOT NULL | — | FK → `documents.id` ON DELETE CASCADE |
| `version_number` | INTEGER | NOT NULL | — | |
| `original_filename` | VARCHAR(500) | NOT NULL | — | |
| `file_path` | VARCHAR(1000) | NOT NULL | — | Relative path from `STORAGE_PATH` |
| `file_size_bytes` | INTEGER | NOT NULL | — | |
| `mime_type` | VARCHAR(100) | NOT NULL | — | |
| `is_current` | BOOLEAN | NOT NULL | `false` | |
| `index_status` | `index_status` | NOT NULL | `'PENDING'` | ENUM: PENDING \| INDEXING \| READY \| ERROR |
| `change_notes` | TEXT | nullable | — | |
| `created_by` | UUID | nullable | — | FK → `users.id` |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |

UNIQUE: `uq_document_version` (document_id, version_number).
Indexes: `idx_versions_current` (document_id, is_current) · `idx_versions_status` (index_status)

---

#### Table: `role_document_permissions`
Per-role access to a specific document.

| Column | Type | Null | Default | Notes |
|--------|------|:----:|---------|-------|
| `id` | UUID | NOT NULL | `gen_random_uuid()` | PK |
| `role_id` | UUID | NOT NULL | — | FK → `roles.id` ON DELETE CASCADE |
| `document_id` | UUID | NOT NULL | — | FK → `documents.id` ON DELETE CASCADE |
| `can_view` | BOOLEAN | NOT NULL | `false` | |
| `can_download` | BOOLEAN | NOT NULL | `false` | |
| `can_chat` | BOOLEAN | NOT NULL | `false` | |

UNIQUE: `uq_role_document` (role_id, document_id).
Indexes: `idx_role_doc_perms_role` · `idx_role_doc_perms_doc`

---

#### Table: `user_document_permissions`
Per-user override on a specific document (highest priority in ACL resolution).

| Column | Type | Null | Default | Notes |
|--------|------|:----:|---------|-------|
| `id` | UUID | NOT NULL | `gen_random_uuid()` | PK |
| `user_id` | UUID | NOT NULL | — | FK → `users.id` ON DELETE CASCADE |
| `document_id` | UUID | NOT NULL | — | FK → `documents.id` ON DELETE CASCADE |
| `can_view` | BOOLEAN | NOT NULL | `false` | |
| `can_download` | BOOLEAN | NOT NULL | `false` | |
| `can_chat` | BOOLEAN | NOT NULL | `false` | |

UNIQUE: `uq_user_document` (user_id, document_id).
Indexes: `idx_user_doc_perms_user` · `idx_user_doc_perms_doc`

---

#### Table: `revoked_tokens`
JWT blacklist (per-token explicit revocation; complements `tokens_valid_after` bulk revocation).

| Column | Type | Null | Default | Notes |
|--------|------|:----:|---------|-------|
| `jti` | UUID | NOT NULL | — | PK (JWT ID claim) |
| `user_id` | UUID | NOT NULL | — | FK → `users.id` ON DELETE CASCADE |
| `expires_at` | TIMESTAMPTZ | NOT NULL | — | Used for garbage collection |

Index: `idx_revoked_expires` (expires_at)

---

#### Table: `rag_documents`
RAG-side ingestion metadata (one row per uploaded file processed by the pipeline).

> **Note on naming:** columns `minio_path` and `minio_bucket_*` are legacy labels — storage is **local filesystem**, not MinIO.

| Column | Type | Null | Default | Notes |
|--------|------|:----:|---------|-------|
| `id` | UUID | NOT NULL | — (app-supplied, no DB default) | PK |
| `role_id` | UUID | nullable | — | FK → `roles.id` ON DELETE SET NULL |
| `filename` | VARCHAR(500) | NOT NULL | — | Internal storage filename |
| `original_filename` | VARCHAR(500) | NOT NULL | — | User-uploaded filename |
| `file_type` | VARCHAR(50) | NOT NULL | — | Extension (e.g. `pdf`) |
| `file_size` | INTEGER | NOT NULL | — | Bytes |
| `status` | VARCHAR(50) | NOT NULL | `'pending'` | Free-text: pending / processing / indexing_images / ready / error |
| `error_message` | TEXT | nullable | — | Set on pipeline failure |
| `chunk_count` | INTEGER | NOT NULL | `0` | Updated after chunking |
| `image_count` | INTEGER | NOT NULL | `0` | Updated after image processing |
| `minio_path` | VARCHAR(1000) | nullable | — | Local FS path for original file (legacy field name) |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Auto-updated by trigger |

Indexes: `idx_rag_docs_status` · `idx_rag_docs_role`

---

#### Table: `chunks`
Text chunks extracted from RAG documents, embedded and stored in ChromaDB.

| Column | Type | Null | Default | Notes |
|--------|------|:----:|---------|-------|
| `id` | UUID | NOT NULL | `gen_random_uuid()` | PK |
| `document_id` | UUID | NOT NULL | — | FK → `rag_documents.id` ON DELETE CASCADE |
| `content` | TEXT | NOT NULL | — | Chunk text (may contain `[IMG:uuid]` markers) |
| `chunk_index` | INTEGER | NOT NULL | — | 0-based position within document |
| `page_number` | INTEGER | nullable | — | |
| `chunk_type` | VARCHAR(50) | NOT NULL | `'text'` | |
| `metadata_json` | TEXT | nullable | — | JSON: filename, image_ids |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |

Index: `idx_chunks_doc` (document_id)

---

#### Table: `document_images`
Extracted images with AI-generated captions (used in the rerank pool during RAG).

| Column | Type | Null | Default | Notes |
|--------|------|:----:|---------|-------|
| `id` | UUID | NOT NULL | `gen_random_uuid()` | PK |
| `document_id` | UUID | NOT NULL | — | FK → `rag_documents.id` ON DELETE CASCADE |
| `minio_path` | VARCHAR(1000) | NOT NULL | — | Local FS path (legacy field name) |
| `page_number` | INTEGER | nullable | — | |
| `image_index` | INTEGER | NOT NULL | — | 0-based within document |
| `description` | TEXT | nullable | — | Gemma-4 Vision caption (Spanish) |
| `ocr_text` | TEXT | nullable | — | Reserved; not populated in current pipeline |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |

Indexes: `idx_doc_images_doc` · `idx_doc_images_page` (document_id, page_number)

---

#### Table: `document_figures`
Figure/caption pairs extracted by regex during ingestion.

| Column | Type | Null | Default | Notes |
|--------|------|:----:|---------|-------|
| `id` | UUID | NOT NULL | `gen_random_uuid()` | PK |
| `document_id` | UUID | NOT NULL | — | FK → `rag_documents.id` ON DELETE CASCADE |
| `figure_number` | INTEGER | NOT NULL | — | Numeric label extracted from text |
| `page_number` | INTEGER | nullable | — | |
| `caption` | TEXT | nullable | — | Caption text (≤200 chars) |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |

Index: `idx_doc_figures_doc` (document_id)

---

#### Table: `chat_sessions`
Chat conversation sessions (one per conversation thread).

| Column | Type | Null | Default | Notes |
|--------|------|:----:|---------|-------|
| `id` | UUID | NOT NULL | `gen_random_uuid()` | PK |
| `user_id` | UUID | NOT NULL | — | FK → `users.id` ON DELETE CASCADE |
| `title` | VARCHAR(200) | NOT NULL | — | Auto-set from first message (60 chars); user-renameable via `PATCH /api/conversations/{id}` |
| `collection_id` | UUID | nullable | — | FK → `collections.id` ON DELETE SET NULL |
| `document_ids` | UUID[] | NOT NULL | `'{}'` | Array of document UUIDs scoped to this session |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Auto-updated by trigger |

Index: `idx_chat_sessions_user` (user_id, updated_at DESC)

---

#### Table: `chat_messages`
Individual messages within a session.

| Column | Type | Null | Default | Notes |
|--------|------|:----:|---------|-------|
| `id` | UUID | NOT NULL | `gen_random_uuid()` | PK |
| `session_id` | UUID | NOT NULL | — | FK → `chat_sessions.id` ON DELETE CASCADE |
| `role` | VARCHAR(20) | NOT NULL | — | `'user'` or `'assistant'` |
| `content` | TEXT | NOT NULL | — | |
| `sources_json` | TEXT | nullable | — | JSON array of source metadata (assistant messages only) |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |

Index: `idx_chat_messages_session` (session_id, created_at)

---

### SQLite Caches

Two embedded SQLite databases stored under `CACHE_DIR` (default `./cache`).

#### `embeddings.db` — Query embedding cache (TTL 30 days)
Table: `embeddings`

| Column | Type | Notes |
|--------|------|-------|
| `key` | TEXT PK | MD5 hash of normalized query text |
| `vector` | BLOB | Float32 numpy array (1024 dims) |
| `created_at` | REAL | Epoch seconds |
| `last_used` | REAL | Epoch seconds |
| `hit_count` | INTEGER | Default 0 |

> Only single-query embeddings (chat path, `embed_text()`) are cached. Batch embeddings during ingestion are NOT cached.

---

#### `responses.db` — LLM response cache (TTL 24 hours)
Table: `responses`

| Column | Type | Notes |
|--------|------|-------|
| `key` | TEXT PK | MD5 of normalized query message |
| `response` | TEXT | Full LLM response text |
| `sources_json` | TEXT | JSON-encoded sources |
| `created_at` | REAL | Epoch seconds |
| `hit_count` | INTEGER | Default 0 |

Table: `response_docs` (enables cache invalidation by document)

| Column | Type | Notes |
|--------|------|-------|
| `key` | TEXT | References `responses.key` (composite PK part) |
| `doc_id` | TEXT | Document UUID string (composite PK part) |

Index: `idx_response_docs_doc` on `doc_id`.

---

### ChromaDB Collection

| Property | Value |
|----------|-------|
| Collection name | `rag_content` (configurable via `CHROMA_COLLECTION`) |
| Persistence path | `CHROMA_PATH` (default `./data/chroma`) |
| Mode | Embedded in-process (no external service) |
| Distance metric | `hnsw:space = "cosine"` |
| Vector ID format | `"{doc_id}_{chunk_index}"` |
| Similarity score | `1.0 - (cosine_distance / 2.0)` → ∈ [0, 1] |

Metadata fields stored per vector:

| Field | Type | Notes |
|-------|------|-------|
| `doc_id` | str | RAG document UUID |
| `filename` | str | Default `""` |
| `page_number` | int | `-1` sentinel when unknown (converted to `None` on read) |
| `chunk_type` | str | Default `"text"` |
| `image_id` | str | Primary image UUID (if chunk contains one image) |
| `image_ids` | str | Comma-joined UUIDs when multiple |
| `caption` | str | Gemma caption if applicable |
| `ocr_text` | str | OCR text if applicable |
| `fig_caption` | str | Figure caption from regex |

> `None` values are replaced with type-appropriate defaults before upserting (ChromaDB rejects `None` in metadata).

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Vision LLM** | Gemma-4 E4B-it Q4\_K\_M GGUF + mmproj f16 — `llama-cpp-python` 0.3+ — captioning only |
| **Chat LLM** | Llama-3.2-3B-Instruct Q4\_K\_M GGUF — `llama-cpp-python` — text generation only |
| **Reranker** | BGE-reranker-v2-m3 — `transformers` `AutoModelForSequenceClassification` |
| **Embeddings** | BGE-M3 (1024-d, multilingual, symmetric) — `sentence-transformers` |
| **Vector Store** | ChromaDB 0.5+ — embedded HNSW, cosine metric, single collection |
| **Relational DB** | PostgreSQL — auth, RBAC, document metadata, RAG chunks/images, chat history |
| **ORM / DB Driver** | SQLAlchemy 2 (async) + asyncpg |
| **API Framework** | FastAPI 0.115 + Uvicorn 0.30 (ASGI) |
| **Streaming** | Server-Sent Events via `sse-starlette` |
| **Document Parsing** | PyMuPDF · pdfplumber · python-docx · python-pptx · openpyxl · Pillow |
| **Text Chunking** | `langchain-text-splitters` — `RecursiveCharacterTextSplitter` |
| **Auth** | JWT HS256 · bcrypt · per-request JTI revocation + `tokens_valid_after` bulk revocation |
| **Caching** | SQLite — embedding cache (30d TTL) + LLM response cache (24h TTL) |
| **Frontend** | Next.js 16.2 · React 19.2 · TypeScript 5 · Tailwind CSS 4 |
| **Frontend UI libs** | Radix UI · lucide-react · react-dropzone · react-markdown + remark-gfm |
| **Frontend package manager** | pnpm |

---

## API Reference

### Auth — `/api/auth`
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/auth/login` | — | Login by **email** (or username for `is_system` admin); returns JWT + user info. Locks the account for `LOCKOUT_MINUTES` after `MAX_LOGIN_ATTEMPTS` failures (`is_system` exempt) |
| `POST` | `/api/auth/send-verification-code` | — | Send first-login password-change code after validating temporary credentials |
| `POST` | `/api/auth/verify-first-login` | — | Verify first-login code and set new password; returns 204 so the user logs in manually afterward |
| `POST` | `/api/auth/request-password-reset` | — | Send password-reset code by email without revealing account existence |
| `POST` | `/api/auth/confirm-password-reset` | — | Verify reset code and set new password; returns 204 so the user logs in manually afterward |
| `POST` | `/api/auth/logout` | Bearer | Revoke current token (inserts JTI into `revoked_tokens`) |
| `GET` | `/api/auth/me` | Bearer | Current user info |

### Users — `/api/users`
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/users` | Bearer | List users (paginated `skip`/`limit`) |
| `GET` | `/api/users/{id}` | Bearer | Get user |
| `POST` | `/api/users` | Admin | Create user with `email`, `password`, `role_id` |
| `PUT` | `/api/users/{id}` | Admin | Update user fields |
| `DELETE` | `/api/users/{id}` | Admin | Deactivate user (soft; cannot deactivate own or system account) |
| `POST` | `/api/users/{id}/activate` | Admin | Reactivate user; sets `tokens_valid_after=NOW()`; clears login lockout |
| `POST` | `/api/users/{id}/reset-password` | Admin | Admin sets a temporary password; invalidates sessions, clears lockout, and forces password change |
| `PATCH` | `/api/users/{id}/role` | Admin | Assign or remove role (guards last SUPERADMIN) |
| `PATCH` | `/api/users/{id}/email` | Admin | Change login email; re-derives `username = email.split("@")[0]`; blocked for `is_system` users |

### Roles — `/api/roles`
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/roles` | Bearer | List all roles |
| `GET` | `/api/roles/{id}` | Bearer | Get role |
| `POST` | `/api/roles` | Admin | Create role |
| `PUT` | `/api/roles/{id}` | Admin | Update role |
| `DELETE` | `/api/roles/{id}` | Admin | Delete role (users → `role_id = NULL`; blocked for `is_system` roles) |

### Collections — `/api/collections`
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/collections/accessible` | Bearer | Collections the current user can access (+ document counts) |
| `GET` | `/api/collections` | Bearer | List all collections |
| `POST` | `/api/collections` | Admin | Create collection |
| `GET` | `/api/collections/{id}` | Bearer | Get collection |
| `PUT` | `/api/collections/{id}` | Admin | Update collection |
| `DELETE` | `/api/collections/{id}?action=auto\|obsolete\|delete` | Admin | Delete collection: `auto` = 409 if docs exist; `obsolete` = mark docs OBSOLETE + unlink; `delete` = hard delete all docs |

### Documents (DMS) — `/api/pg-documents`
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/pg-documents` | Bearer | List documents (filters: `search`, `collection_id`, `status`, `uncategorized`, `sort`) |
| `POST` | `/api/collections/{id}/upload` | `can_upload` | Upload document into a collection |
| `POST` | `/api/pg-documents/upload` | `can_upload` | Upload document without a collection ("Sin asignar") |
| `GET` | `/api/pg-documents/{id}/download` | Bearer | Download file |
| `PATCH` | `/api/pg-documents/{id}` | `can_upload` | Update `title` and/or `collection_id` (`clear_collection=true` → NULL) |
| `POST` | `/api/pg-documents/{id}/reactivate` | `can_upload` | OBSOLETE → ACTIVE |
| `DELETE` | `/api/pg-documents/{id}` | `can_delete` | Soft delete (→ OBSOLETE; still downloadable) |
| `DELETE` | `/api/pg-documents/{id}/permanent` | `can_delete` | Hard delete (vectors + files + Postgres; requires OBSOLETE status) |

### Documents (RAG) — `/api/documents` & `/api/images`
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/documents` | Bearer | List RAG documents |
| `GET` | `/api/documents/{id}` | Bearer | RAG document detail |
| `DELETE` | `/api/documents/{id}` | Bearer | Delete RAG document |
| `GET` | `/api/documents/{id}/download` | Bearer | Download original file |
| `GET` | `/api/images/{id}` | Bearer | Serve extracted image |

### Ingest — `/api`
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/ingest` | Bearer | Upload file + start background indexing pipeline |
| `GET` | `/api/documents/{id}/status` | Bearer | Ingestion status (status, error, chunk_count, image_count) |

### Chat — `/api`
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/chat` | Bearer | SSE streaming RAG chat (returns token stream + `done` event with sources) |

### Conversations — `/api/conversations`
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/conversations` | Bearer | List user's chat sessions (ordered by `updated_at` DESC, limit 100) |
| `GET` | `/api/conversations/{id}` | Bearer | Session detail with full message history |
| `POST` | `/api/conversations/{id}/resume-check` | Bearer | Validate doc/collection access before resuming |
| `PATCH` | `/api/conversations/{id}` | Bearer | Rename conversation title |
| `DELETE` | `/api/conversations/{id}` | Bearer | Delete conversation (204) |

### Permissions — `/api/collections/{id}/permissions` · `/api/documents/{id}/permissions`
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET/PUT` | `.../permissions/roles/{role_id}` | Admin | Get/set role ACL entry |
| `GET/PUT/DELETE` | `.../permissions/users/{user_id}` | Admin | Get/set/remove user ACL entry |

### Admin — `/api/admin`
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/admin/roles` | Admin | Roles with eager-loaded relations |
| `GET` | `/api/admin/users` | Admin | Users with eager-loaded role |

### Health
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/health` | — | Service health (ChromaDB, local storage, HF models) |
| `GET` | `/docs` | — | OpenAPI interactive documentation |

---

## Environment Variables

All variables read from `.env` via Pydantic `Settings` (`backend/app/config.py`).

### Storage & Paths
| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://localhost/fallback` | Async PostgreSQL DSN |
| `STORAGE_PATH` | `./data/storage` | Root for document and image files |
| `CHROMA_PATH` | `./data/chroma` | ChromaDB persistence directory |
| `CACHE_DIR` | `./cache` | SQLite caches directory |
| `HF_CACHE_DIR` | `./models_cache` | HuggingFace model weights cache |

### Vision LLM — Gemma-4 (image captioning)
| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_GGUF_REPO` | `bartowski/google_gemma-4-E4B-it-GGUF` | HF repo |
| `LLM_GGUF_FILENAME` | `google_gemma-4-E4B-it-Q4_K_M.gguf` | GGUF filename |
| `LLM_MMPROJ_FILENAME` | `mmproj-google_gemma-4-E4B-it-f16.gguf` | Multimodal projector filename |
| `LLM_N_CTX` | `2048` | Vision context window (tokens); captioning needs ~860 |
| `LLM_N_THREADS` | `0` | CPU threads (0 = auto: `cpu_count - 2`) |
| `VISION_MAX_TOKENS` | `256` | Max tokens per image caption |
| `VISION_TEMPERATURE` | `0.1` | Caption sampling temperature (near-deterministic) |

### Chat LLM — Llama-3.2-3B (RAG answers)
| Variable | Default | Description |
|----------|---------|-------------|
| `CHAT_GGUF_REPO` | `bartowski/Llama-3.2-3B-Instruct-GGUF` | HF repo |
| `CHAT_GGUF_FILENAME` | `Llama-3.2-3B-Instruct-Q4_K_M.gguf` | GGUF filename |
| `CHAT_N_CTX` | `8192` | Chat context window (tokens) |
| `CHAT_MAX_TOKENS` | `1024` | Max generated tokens per response |
| `CHAT_TEMPERATURE` | `0.2` | Sampling temperature |
| `CHAT_TOP_P` | `0.9` | Nucleus sampling threshold |
| `CHAT_TOP_K` | `40` | Top-k sampling |
| `CHAT_REPEAT_PENALTY` | `1.1` | Repetition penalty |

### Embeddings & Reranker
| Variable | Default | Description |
|----------|---------|-------------|
| `EMBED_MODEL_ID` | `BAAI/bge-m3` | BGE-M3 HF model ID |
| `EMBEDDING_DIMS` | `1024` | Expected output dimensions (validated at startup) |
| `RERANKER_MODEL_ID` | `BAAI/bge-reranker-v2-m3` | Cross-encoder HF model ID |

### Retrieval Knobs
| Variable | Default | Description |
|----------|---------|-------------|
| `RETRIEVAL_TOP_K` | `12` | Candidates fetched from ChromaDB before reranking |
| `RERANK_TOP_K` | `3` | Items passed to the LLM after reranking |
| `RERANK_MAX_IMAGES` | `6` | Max image descriptions added to the rerank pool |

### Ingestion
| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_IMAGES_PER_DOC` | `50` | Cap on images extracted per document |
| `SKIP_OCR` | `false` | Skip OCR on image extraction |

### Auth & Seed
| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `change_in_production` | JWT signing secret (min 32 bytes) |
| `ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | JWT expiry (8 hours) |
| `MAX_LOGIN_ATTEMPTS` | `5` | Failed logins before temporary account lockout (`is_system` users exempt) |
| `LOCKOUT_MINUTES` | `15` | Lockout duration in minutes; auto-expires, or admin unlocks via activate/reset-password |
| `INITIAL_ADMIN_USERNAME` | `admin` | Seeded system admin username (login by username) |
| `INITIAL_ADMIN_PASSWORD` | `admin123` | Seeded system admin password |
| `SMTP_HOST` | — | Internal bank SMTP relay host; configure in `backend/.env` |
| `SMTP_PORT` | `25` | Internal relay port; plain SMTP |
| `SMTP_FROM` | — | Authorized sender address shown as email remitente; configure in `backend/.env` |
| `SMTP_TIMEOUT` | `10` | SMTP network timeout in seconds |
| `SMTP_ENABLED` | `true` | `false` logs email actions without contacting the relay |

Manual relay check from the VM:

```bash
python3 backend/tests/smtp_email_check.py --to user@example.com
python3 backend/tests/smtp_email_check.py --to user@example.com --dry-run
```

Local email template previews without SMTP:

```bash
python3 backend/tools/preview_emails.py
python3 backend/tools/preview_emails.py --output /tmp/bmsc_email_previews
```

Email deliverability checklist for production:

- Use a real authorized `SMTP_FROM` domain, not `bmsc.local` or any local-only domain.
- Publish SPF allowing the bank SMTP relay to send for that domain.
- Sign outbound mail with DKIM and align DKIM/SPF with the visible From domain.
- Publish a DMARC policy for the sender domain and monitor aggregate reports.
- Ensure the relay public IP has PTR/rDNS matching the sending hostname.
- Prefer STARTTLS on the relay path when the bank SMTP infrastructure supports it.
- Keep the visible sender as `BMSC Base de Conocimiento` for all transactional messages.

### Performance Logging
| Variable | Default | Description |
|----------|---------|-------------|
| `CHAT_PERF_LOGGING` | `false` | Emit `[chat-perf]` logs with per-stage timing |
| `INGEST_PERF_LOGGING` | `false` | Emit `[ingest-perf]` logs with per-step timing |

---

## Getting Started

### Prerequisites

- Python 3.11+ (backend virtual environment at `backend/.venv`)
- PostgreSQL with `pgcrypto` extension enabled
- Node.js 20+ and [pnpm](https://pnpm.io)
- ~8 GB free disk space for model weights

### 1. Clone the repository

```bash
git clone <repo-url>
cd BMSC_RAG_System
```

### 2. Backend — install dependencies

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Download model weights (~8 GB, one-time)

```bash
python download_models.py
```

Downloads five artifacts to `./models_cache/`:

| File | Purpose |
|------|---------|
| `google_gemma-4-E4B-it-Q4_K_M.gguf` | Vision LLM — image captioning during ingest |
| `mmproj-google_gemma-4-E4B-it-f16.gguf` | Multimodal projector for Gemma-4 |
| `BAAI/bge-m3/` | BGE-M3 embeddings (1024-d) |
| `Llama-3.2-3B-Instruct-Q4_K_M.gguf` | Chat LLM — RAG text generation |
| `BAAI/bge-reranker-v2-m3/` | Cross-encoder reranker |

### 4. Configure environment

```bash
cp .env.example .env
```

At minimum, set:

```env
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/bmsc_kb
SECRET_KEY=<random-256-bit-hex>
```

See [Environment Variables](#environment-variables) for the full reference.

### 5. Initialize the PostgreSQL schema

The application does **not** auto-create tables. Apply the schema manually:

```bash
psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
psql "$DATABASE_URL" -f sql/bd.sql
```

> On first startup the app seeds the initial admin user automatically (only if the `users` table is empty).

### 6. Start the API server

```bash
uvicorn app.main:app --reload --port 8000
```

**Startup sequence:**
1. Load all four models from local cache (Gemma-4, Llama-3.2-3B, BGE-M3, BGE-reranker)
2. Connect to PostgreSQL; seed initial admin if `users` table is empty
3. Initialize ChromaDB embedded collection (`rag_content`)
4. Ensure storage directories (`data/storage/documents/`, `data/storage/images/`)
5. Initialize SQLite caches (`embeddings.db`, `responses.db`)

API docs: `http://localhost:8000/docs`

**Initial admin credentials** (change immediately in production):
- Username: `admin` (value of `INITIAL_ADMIN_USERNAME`) — logs in by **username**
- Password: value of `INITIAL_ADMIN_PASSWORD` (default `admin123`)

All other users log in by **email + password**.

### 7. Start the frontend

```bash
cd ../frontend
pnpm install
```

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

```bash
pnpm dev
```

UI available at `http://localhost:3000`.

---

## Project Structure

```
BMSC_RAG_System/
├── backend/
│   ├── app/
│   │   ├── cache/
│   │   │   ├── embedding_cache.py     # SQLite embedding cache (TTL 30d)
│   │   │   └── response_cache.py      # SQLite LLM response cache (TTL 24h)
│   │   ├── core/
│   │   │   ├── dependencies.py        # require_permission() factory
│   │   │   └── security.py            # bcrypt, JWT create/decode
│   │   ├── db/
│   │   │   ├── base.py                # SQLAlchemy declarative base
│   │   │   ├── session.py             # Async engine + session factory
│   │   │   ├── models/                # SQLAlchemy ORM models (16 tables)
│   │   │   │   ├── user.py            # PGUser — users table
│   │   │   │   ├── role.py            # PGRole — roles table
│   │   │   │   ├── collection.py      # Collection
│   │   │   │   ├── document.py        # PGDocument — documents (DMS)
│   │   │   │   ├── document_version.py
│   │   │   │   ├── rag_document.py    # RagDocument — RAG pipeline metadata
│   │   │   │   ├── rag_chunk.py       # RagChunk — chunks
│   │   │   │   ├── rag_document_image.py
│   │   │   │   ├── rag_document_figure.py
│   │   │   │   ├── chat_session.py    # ChatSession — chat_sessions
│   │   │   │   ├── chat_message.py    # ChatMessage — chat_messages
│   │   │   │   ├── revoked_token.py
│   │   │   │   ├── collection_permission.py
│   │   │   │   ├── user_collection_permission.py
│   │   │   │   ├── role_document_permission.py
│   │   │   │   └── user_document_permission.py
│   │   │   └── schemas/               # Pydantic request/response schemas
│   │   │       ├── auth.py            # LoginRequest, UserInfo, LoginResponse
│   │   │       ├── user.py            # UserCreate (email), UserOut, EmailUpdateRequest
│   │   │       ├── role.py
│   │   │       ├── collection.py
│   │   │       └── permission.py
│   │   ├── routers/
│   │   │   ├── auth.py                # POST /login · /logout · GET /me
│   │   │   ├── users.py               # CRUD + activate/reset/email + role
│   │   │   ├── roles.py
│   │   │   ├── collections.py         # + /accessible + delete action param
│   │   │   ├── pg_documents.py        # DMS CRUD + soft/hard delete + reactivate
│   │   │   ├── documents.py           # RAG documents + images
│   │   │   ├── ingest.py              # POST /ingest + status
│   │   │   ├── chat.py                # POST /chat (SSE)
│   │   │   ├── conversations.py       # List/get/rename/delete/resume-check
│   │   │   ├── permissions.py         # Collection + document ACLs
│   │   │   └── admin.py               # /admin/roles + /admin/users
│   │   ├── services/
│   │   │   ├── rag.py                 # build_context, stream_chat
│   │   │   ├── reranker.py            # BGE cross-encoder reranker
│   │   │   ├── embedder.py            # BGE-M3 embed_text/embed_texts_batch + Gemma describe_image
│   │   │   ├── vector_store.py        # ChromaDB upsert/search
│   │   │   ├── ingest_pipeline.py     # Full ingestion orchestration
│   │   │   ├── chunker.py             # RecursiveCharacterTextSplitter wrapper
│   │   │   ├── file_storage.py        # Local filesystem upload/download/delete
│   │   │   ├── hard_delete.py         # hard_delete_document() — ChromaDB+files+Postgres
│   │   │   ├── chat_access.py         # check_doc_access, check_collection_access
│   │   │   └── parsers/
│   │   │       ├── pdf_parser.py      # PyMuPDF + pdfplumber
│   │   │       ├── docx_parser.py
│   │   │       ├── pptx_parser.py
│   │   │       ├── xlsx_parser.py
│   │   │       └── image_parser.py
│   │   ├── utils/
│   │   │   ├── model_manager.py       # Load all 4 models; get_*() getters
│   │   │   ├── inference_queue.py     # FIFO Semaphore(1) shared by Gemma + Llama
│   │   │   ├── gemma_vision_handler.py # Custom llama-cpp multimodal handler for Gemma-4
│   │   │   └── model_check.py
│   │   ├── config.py                  # Pydantic Settings (reads .env)
│   │   ├── schemas.py                 # Shared Pydantic models (chat, ingest, health)
│   │   ├── dependencies.py            # get_current_user, oauth2_scheme
│   │   ├── main.py                    # App factory, lifespan, CORS, router registration
│   │   └── seed.py                    # Seed initial SUPERADMIN on empty users table
│   ├── sql/
│   │   └── bd.sql                     # Full PostgreSQL schema (apply manually)
│   ├── download_models.py             # One-time model weight downloader
│   ├── benchmark_Q4.py                # LLM benchmark script
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── app/
│   │   ├── layout.tsx                 # Root layout + AuthProvider + metadata
│   │   ├── page.tsx                   # Redirect → /login
│   │   ├── login/page.tsx             # Login form (email + password)
│   │   ├── chat/page.tsx              # Main chat interface
│   │   ├── documents/page.tsx         # Document library
│   │   └── admin/page.tsx             # Admin panel (users, roles, collections, ACLs)
│   ├── components/
│   │   ├── NavBar.tsx
│   │   ├── chat/
│   │   │   ├── ChatWindow.tsx         # Message list + title header + rename button
│   │   │   ├── ChatHistoryPanel.tsx   # Sidebar history (resume / rename / delete)
│   │   │   ├── MessageBubble.tsx
│   │   │   ├── MessageInput.tsx
│   │   │   ├── SourcesPanel.tsx
│   │   │   ├── SourceImages.tsx
│   │   │   └── ImageLightbox.tsx
│   │   ├── documents/
│   │   │   ├── DocumentTable.tsx
│   │   │   ├── StatusBadge.tsx
│   │   │   └── UploadZone.tsx
│   │   └── ui/
│   │       ├── AlertModal.tsx
│   │       └── ConfirmModal.tsx
│   ├── lib/
│   │   ├── api.ts                     # Typed API client (all backend calls)
│   │   └── auth-context.tsx           # React auth state + token lifecycle
│   ├── types/index.ts                 # Shared TypeScript types
│   ├── public/                        # Logos, favicons
│   ├── package.json                   # pnpm · Next.js 16.2 · React 19.2
│   └── .env.local.example
└── README.md
```

---

## Key Design Decisions

**1. Dual-model LLM separation**
Gemma-4 E4B (multimodal) runs exclusively during ingestion to caption extracted images. Llama-3.2-3B (text-only) runs exclusively during chat. This ensures the chat LLM never processes image pixels, reduces prompt prefill size, and avoids multimodal overhead in the hot path.

**2. BGE cross-encoder reranking (top-12 → top-3)**
ChromaDB returns the top-12 candidates by cosine similarity (text chunks + image descriptions). BGE-reranker-v2-m3 rescores the unified pool with a cross-encoder against the original query, keeping only the 3 most relevant items for the prompt. The reranker runs outside the inference queue — it is fast and CPU-orthogonal to the LLM.

**3. Image descriptions as first-class RAG context**
During ingestion, Gemma-4 Vision generates Spanish captions for extracted figures and stores them in `document_images.description`. During RAG, captions for pages matching retrieved chunks compete in the reranker pool alongside text chunks. Winning descriptions are injected into the prompt as text blocks; the chat LLM reasons over the description, not pixels.

**4. Embedded ChromaDB (no external vector service)**
ChromaDB runs in-process. It initializes with the app, persists to `./data/chroma`, and survives restarts without a separate daemon or container.

**5. Shared FIFO inference queue (Semaphore = 1)**
A single `asyncio.Semaphore(1)` in `utils/inference_queue.py` serializes all GGUF model calls — Gemma captioning (ingest) and Llama chat share this queue. Concurrent HTTP requests queue rather than contend on CPU threads, preventing latency spikes from context switching during matrix multiplications.

**6. Dual SQLite response/embedding caches**
A 30-day embedding cache (`embeddings.db`, keyed by content hash) avoids re-embedding identical queries. A 24-hour LLM response cache (`responses.db`) short-circuits inference for repeated questions. Only single-query embeddings are cached; batch embeddings at ingest are not.

**7. BGE-M3 symmetric mode**
BGE-M3 embeds chunks and queries with identical function calls — no `query:`/`passage:` instruction prefixes required. This simplifies the pipeline and supports multilingual documents natively.

**8. Email-based login with `is_system` username exception**
Users log in with email + password. The seeded system admin (`is_system = true`) logs in with username + password, determined at runtime by the `is_system` flag — not hardcoded. This allows the first admin to access the system before any email-based user exists.

**9. SSE over WebSockets**
Server-Sent Events handle the one-directional token stream from server to client. This avoids WebSocket connection management overhead while fully satisfying the streaming requirement.

**10. All I/O async; CPU work dispatched to thread executor**
All database operations (`asyncpg`, SQLAlchemy async) and file I/O (`aiofiles`) are `async`. CPU-bound inference (embedding, LLM, reranking) is dispatched via `asyncio.get_event_loop().run_in_executor()`, keeping the event loop unblocked throughout.

**11. Nullable FKs with `ON DELETE SET NULL`**
`documents.collection_id` and `users.role_id` accept NULL. Deleting a collection or a role does not cascade-delete dependent rows — orphaned documents and users are surfaced in the admin panel for reassignment.

**12. Centralized hard delete**
`services/hard_delete.py::hard_delete_document(doc_id)` purges a document in order: ChromaDB vectors → physical files (original + images) → `rag_documents` (CASCADE cleans chunks/images/figures) → `documents` (CASCADE cleans versions/permissions). No commit — the caller manages the transaction.
