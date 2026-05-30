# DocuMind RAG

> Self-hosted Retrieval Augmented Generation for enterprise documentation — query PDFs, spreadsheets, presentations, and documents through a conversational interface powered by local AI inference.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16.2-000000?logo=next.js&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white)
![ChromaDB](https://img.shields.io/badge/ChromaDB-0.5-FF6B35)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Overview

DocuMind RAG is a self-hosted document intelligence platform that ingests organizational documents and makes them queryable through natural language. The system combines dense vector retrieval, cross-encoder reranking, and a quantized language model to answer questions grounded strictly in the uploaded knowledge base — including visual content extracted from figures and diagrams as text descriptions.

The stack runs entirely on-premise with no external API dependencies. The inference layer uses a **dual-model architecture**: **Gemma-4 E4B Q4\_K\_M** (multimodal, via `llama-cpp-python`) handles image captioning during document ingestion; **Llama-3.2-3B-Instruct Q4\_K\_M** (text-only) generates all chat responses. **BGE-reranker-v2-m3** reranks the retrieval pool before it reaches the LLM. Embeddings are produced by **BGE-M3** via `sentence-transformers`, and vectors are persisted in an embedded **ChromaDB** instance. A hybrid RBAC + per-document ACL model controls which users and roles can view or chat over specific documents and collections.

---

## System Architecture

```mermaid
graph TD
    subgraph Client
        U[User Browser]
    end

    subgraph Frontend["Frontend — Next.js 16"]
        FE_CHAT[Chat Interface]
        FE_ADMIN[Admin Panel]
        FE_DOCS[Document Library]
    end

    subgraph API["API Server — FastAPI 0.115"]
        AUTH[Auth Router<br/>JWT + bcrypt]
        CHAT_R[Chat Router<br/>SSE Streaming]
        INGEST_R[Ingest Router]
        DOC_R[Documents Router]
        PERM_R[Permissions Router]
        HEALTH[Health Check]
    end

    subgraph Inference["Local Inference — CPU only"]
        QUEUE[FIFO Inference Queue<br/>semaphore = 1]
        GEMMA[Gemma-4 E4B Q4_K_M<br/>image captioning · ingest only]
        QWEN[Llama-3.2-3B Q4_K_M<br/>chat text generation]
        EMBED[BGE-M3 1024-d<br/>sentence-transformers]
        RERANK[BGE-reranker-v2-m3<br/>cross-encoder · outside queue]
    end

    subgraph Storage["Persistence"]
        PG[(PostgreSQL 18<br/>Users · RBAC · Metadata)]
        CHROMA[(ChromaDB<br/>HNSW · cosine)]
        FS[File Storage<br/>documents/ · images/]
        CACHE[(SQLite Cache<br/>embeddings · responses)]
    end

    U --> FE_CHAT & FE_ADMIN & FE_DOCS
    FE_CHAT --> CHAT_R
    FE_DOCS --> INGEST_R & DOC_R
    FE_ADMIN --> AUTH & PERM_R

    INGEST_R --> QUEUE --> GEMMA
    CHAT_R --> QUEUE --> QWEN
    CHAT_R --> RERANK
    INGEST_R --> EMBED
    CHAT_R --> EMBED
    EMBED --> CACHE

    CHAT_R --> CHROMA
    INGEST_R --> CHROMA
    INGEST_R --> FS

    AUTH --> PG
    CHAT_R --> PG
    INGEST_R --> PG
    DOC_R --> PG
    PERM_R --> PG
```

---

## Document Ingestion Pipeline

```mermaid
flowchart LR
    A([File Upload\n≤ 200 MB]) --> B[Store Original\n./data/storage/documents]
    B --> C{Format Parser}
    C -->|PDF| D[PyMuPDF\npdfplumber]
    C -->|DOCX/PPTX| E[python-docx\npython-pptx]
    C -->|XLSX| F[openpyxl]
    C -->|Image| G[Pillow]
    D & E & F & G --> H[Extract Text Blocks\n+ Image Blocks]
    H --> I[Store Images\n./data/storage/images]
    I --> J[Caption Images\nGemma-4 Vision\nstored in PostgreSQL]
    J --> K[Chunk Text\nRecursive 800 / 150 overlap]
    K --> L[Embed Chunks\nBGE-M3 → 1024-d]
    L --> M[(ChromaDB\nupsert HNSW)]
    L --> N[(PostgreSQL\nchunks + image descriptions)]
    M & N --> O([Status: ready])
```

**Supported formats:** `.pdf` · `.docx` · `.pptx` · `.xlsx` · `.txt` · `.md` · `.jpg` · `.jpeg` · `.png` · `.webp`

---

## RAG Query Flow

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend
    participant API as FastAPI
    participant PG as PostgreSQL
    participant EMB as BGE-M3
    participant VDB as ChromaDB
    participant RR as BGE-reranker-v2-m3
    participant Q as Inference Queue
    participant LLM as Llama-3.2-3B

    User->>FE: Send message
    FE->>API: POST /api/chat
    API->>PG: Resolve user permissions
    API->>PG: Load conversation history (last 4 turns)
    API->>EMB: Embed query + history context
    EMB-->>API: 1024-d vector
    API->>VDB: Cosine search top-10 chunks
    VDB-->>API: Chunks + scores
    API->>PG: Fetch image descriptions for retrieved pages
    PG-->>API: document_images.description rows
    API->>RR: Rerank pool (chunks + image descriptions)
    RR-->>API: Top-3 items by relevance
    API->>Q: Enqueue inference request (FIFO)
    Q->>LLM: Prompt: system + text context + history + query
    loop Token stream
        LLM-->>API: Token
        API-->>FE: SSE: data token
    end
    API-->>FE: SSE: sources JSON
    FE-->>User: Rendered response + source panel
    API->>PG: Persist conversation turn
    API->>PG: Cache response (query hash)
```

> **Note:** The chat LLM (Llama-3.2-3B) is a text-only model. It receives only text as context — image descriptions are injected as `[Figura N: ...]` text blocks in the prompt. The model does not process or receive image pixels at any point during chat.

---

## Database Schema

```mermaid
erDiagram
    users {
        uuid id PK
        string username
        string hashed_password
        uuid role_id FK
        bool is_active
    }
    roles {
        uuid id PK
        string name
        bool can_manage_users
        bool can_manage_collections
        bool can_upload_documents
        bool can_delete_documents
    }
    rag_documents {
        uuid id PK
        uuid role_id FK
        string filename
        string file_type
        string status
        int chunk_count
        int image_count
    }
    chunks {
        uuid id PK
        uuid document_id FK
        text content
        int chunk_index
        int page_number
    }
    document_images {
        uuid id PK
        uuid document_id FK
        string minio_path
        int page_number
        text description
    }
    collections {
        uuid id PK
        string name
        bool is_active
    }
    user_document_permissions {
        uuid user_id FK
        uuid document_id FK
        bool can_view
        bool can_chat
        bool can_delete
    }
    role_document_permissions {
        uuid role_id FK
        uuid document_id FK
        bool can_view
        bool can_chat
    }
    collection_permissions {
        uuid role_id FK
        uuid collection_id FK
        bool can_view
        bool can_chat
        bool can_manage
    }
    revoked_tokens {
        string jti PK
        uuid user_id FK
        datetime expires_at
    }
    conversations {
        uuid id PK
        string conversation_id
        string role
        text content
        json sources_json
    }

    users }o--|| roles : "belongs to"
    users ||--o{ user_document_permissions : "has"
    roles ||--o{ role_document_permissions : "has"
    roles ||--o{ collection_permissions : "has"
    rag_documents ||--o{ chunks : "contains"
    rag_documents ||--o{ document_images : "contains"
    rag_documents ||--o{ user_document_permissions : "grants"
    rag_documents ||--o{ role_document_permissions : "grants"
    collections ||--o{ collection_permissions : "grants"
    users ||--o{ revoked_tokens : "revokes"
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Chat LLM | Llama-3.2-3B-Instruct Q4\_K\_M GGUF — `llama-cpp-python` 0.3.23 (text-only) |
| Vision Captioning | Gemma-4 E4B Q4\_K\_M + mmproj — `llama-cpp-python` (ingest only) |
| Reranker | BGE-reranker-v2-m3 — `transformers` + `AutoModelForSequenceClassification` |
| Embeddings | BGE-M3 (1024-d, multilingual) — `sentence-transformers` |
| Vector Store | ChromaDB 0.5 — embedded HNSW, cosine metric |
| Relational DB | PostgreSQL 18 — users, RBAC, metadata, conversations |
| API Framework | FastAPI 0.115 + Uvicorn 0.30 (async, ASGI) |
| Streaming | Server-Sent Events via `sse-starlette` |
| Document Parsing | PyMuPDF · pdfplumber · python-docx · python-pptx · openpyxl · Pillow |
| Text Chunking | `langchain-text-splitters` — RecursiveCharacterTextSplitter |
| Auth | JWT (HS256) · bcrypt · per-request JTI revocation check |
| Caching | SQLite — embedding cache + LLM response cache |
| Frontend | Next.js 16 · React 19 · Tailwind CSS 4 · Radix UI |

---

## Key Design Decisions

**1. Dual-model inference architecture**
Gemma-4 E4B (multimodal) runs exclusively during document ingestion to generate text captions for extracted images. Llama-3.2-3B (text-only) runs exclusively during chat to generate responses. This separation means the chat LLM never receives image pixels — it receives pre-generated text descriptions — which reduces prompt size, eliminates multimodal inference overhead in the hot path, and avoids any implication that the chat model has visual capability.

**2. BGE cross-encoder reranking (top-10 → top-3)**
ChromaDB returns the top-10 chunks by cosine similarity. BGE-reranker-v2-m3 then re-scores the full pool (text chunks + image descriptions) against the original query using a cross-encoder, keeping only the 3 most relevant items for the prompt. This two-stage retrieval improves answer quality and reduces LLM prefill time. The reranker runs outside the inference queue since it is fast and CPU-orthogonal to the LLM.

**3. Image descriptions as first-class RAG context**
During ingestion, Gemma-4 Vision generates a Spanish description of each extracted figure and stores it in `document_images.description` (PostgreSQL). During RAG, these descriptions are fetched for the pages matching the retrieved chunks and compete in the reranker pool alongside text chunks. The winning descriptions are injected into the prompt as `[Figura N: filename, página P]` text blocks — the LLM reasons over the description text, not pixels.

**4. Embedded ChromaDB**
ChromaDB runs in-process with a persistent HNSW index on disk (`./data/chroma`). This removes an external service dependency entirely — the vector store initializes with the application and survives restarts without a separate process.

**5. BGE-M3 with symmetric retrieval**
BGE-M3 produces 1024-dimensional embeddings that perform well in symmetric retrieval mode (no `query:`/`passage:` instruction prefixes required). This simplifies the embedding pipeline and supports multilingual documents out of the box.

**6. Shared FIFO Inference Queue (semaphore = 1)**
A single `asyncio.Semaphore` serializes all LLM calls — both Gemma-4 (image captioning during ingest) and Llama-3.2-3B (chat generation) share the same queue. Concurrent HTTP requests queue rather than contend on CPU threads, preventing latency spikes from context switching during matrix operations.

**7. RBAC + per-document ACL**
Roles define coarse-grained defaults (`can_upload_documents`, `can_manage_collections`). Individual documents and collections carry separate permission rows per user and per role with `can_view`, `can_chat`, `can_edit`, `can_share`, `can_delete` flags. The resolution order is: explicit user permission → role permission → collection membership → deny.

**8. SSE over WebSockets**
Server-Sent Events deliver token-by-token streaming over a standard HTTP connection. This avoids WebSocket connection management complexity while satisfying the one-directional server→client stream requirement of LLM output.

**10. Fully async I/O with thread executor offload**
All database access and file I/O use `asyncio`-native drivers (`asyncpg`, `aiofiles`). CPU-bound operations (embedding, inference, reranking) are dispatched to a thread executor via `asyncio.get_event_loop().run_in_executor()`, keeping the event loop unblocked.

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+ and [pnpm](https://pnpm.io)
- PostgreSQL 18
- ~11 GB free disk space for model weights

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd documentation_chat/backend
pip install -r requirements.txt
```

### 2. Download model weights

```bash
python download_models.py
```

This downloads five artifacts to `./models_cache/` (~11 GB total):

| File | Size | Purpose |
|------|------|---------|
| `google_gemma-4-E4B-it-Q4_K_M.gguf` | ~5.4 GB | Vision LLM — image captioning during ingest |
| `mmproj-google_gemma-4-E4B-it-f16.gguf` | ~1.0 GB | Multimodal projection for Gemma-4 |
| `BAAI/bge-m3/` | ~1.1 GB | Embeddings — semantic vector encoding |
| `Llama-3.2-3B-Instruct-Q4_K_M.gguf` | ~2.0 GB | Chat LLM — text generation in RAG chat |
| `BAAI/bge-reranker-v2-m3/` | ~1.1 GB | Cross-encoder reranker |

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```env
DATABASE_URL=postgresql+asyncpg://user:password@ipaddress:5432/docmind
SECRET_KEY=<random-256-bit-hex>
```

See [Environment Variables](#environment-variables) for the full reference.

### 4. Start the API server

```bash
uvicorn app.main:app --reload --port 8000
```

On startup the application:
1. Loads all four models from the model cache (Gemma-4, Llama-3.2-3B, BGE-M3, BGE-reranker)
2. Connects to PostgreSQL and seeds the initial admin user
3. Initializes the ChromaDB collection
4. Creates storage directories and SQLite caches

Interactive API docs are available at `http://localhost:8000/docs`.

### 5. Start the frontend

```bash
cd ../frontend
pnpm install
pnpm dev
```

The UI is available at `http://localhost:3000`.

---

## API Reference

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/auth/login` | — | Obtain JWT access token |
| `POST` | `/api/auth/logout` | Bearer | Revoke current token (JTI blacklist) |
| `GET` | `/api/auth/me` | Bearer | Current user info |
| `POST` | `/api/chat` | Bearer | SSE streaming chat with RAG context |
| `GET` | `/api/chat/history/{id}` | Bearer | Conversation history |
| `POST` | `/api/ingest` | Bearer | Upload and index a document |
| `GET` | `/api/documents/{id}/status` | Bearer | Ingestion pipeline status |
| `GET` | `/api/documents` | Bearer | Paginated document list |
| `DELETE` | `/api/documents/{id}` | Bearer | Delete document, vectors, and files |
| `GET` | `/api/collections/accessible` | Bearer | Collections visible to current user |
| `GET/PUT` | `/api/permissions/documents/{id}/users` | Admin | Document-level user ACL |
| `GET/PUT` | `/api/permissions/documents/{id}/roles` | Admin | Document-level role ACL |
| `GET` | `/api/health` | — | Service health (DB, ChromaDB, models) |
| `GET` | `/docs` | — | OpenAPI interactive documentation |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | — | PostgreSQL async DSN (`postgresql+asyncpg://...`) |
| `SECRET_KEY` | — | JWT signing secret (min 32 bytes, random) |
| `STORAGE_PATH` | `./data/storage` | Root path for document and image files |
| `CHROMA_PATH` | `./data/chroma` | ChromaDB persistence directory |
| `HF_CACHE_DIR` | `./models_cache` | Model weights cache directory |
| `LLM_GGUF_REPO` | `bartowski/google_gemma-4-E4B-it-GGUF` | HF repo for Gemma-4 (vision/captioning) |
| `LLM_GGUF_FILENAME` | `google_gemma-4-E4B-it-Q4_K_M.gguf` | Gemma-4 GGUF filename |
| `LLM_MMPROJ_FILENAME` | `mmproj-google_gemma-4-E4B-it-f16.gguf` | Gemma-4 vision projection filename |
| `LLM_N_CTX` | `4096` | Gemma-4 context window (tokens) |
| `LLM_N_THREADS` | `0` | CPU threads for inference (`0` = auto-detect) |
| `CHAT_GGUF_REPO` | `bartowski/Llama-3.2-3B-Instruct-GGUF` | HF repo for Llama-3.2-3B (chat) |
| `CHAT_GGUF_FILENAME` | `Llama-3.2-3B-Instruct-Q4_K_M.gguf` | Llama-3.2-3B GGUF filename |
| `CHAT_N_CTX` | `8192` | Llama-3.2-3B context window (tokens) |
| `CHAT_MAX_TOKENS` | `1024` | Max tokens per chat response |
| `CHAT_TEMPERATURE` | `0.7` | Chat sampling temperature |
| `CHAT_TOP_P` | `0.9` | Chat nucleus sampling threshold |
| `CHAT_TOP_K` | `40` | Chat top-k sampling |
| `RERANKER_MODEL_ID` | `BAAI/bge-reranker-v2-m3` | Cross-encoder reranker HF model ID |
| `RETRIEVAL_TOP_K` | `10` | Chunks fetched from ChromaDB before reranking |
| `RERANK_TOP_K` | `3` | Items passed to the LLM after reranking |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | JWT expiry (8 hours) |
| `INITIAL_ADMIN_USERNAME` | `admin` | Seeded superadmin username |
| `INITIAL_ADMIN_PASSWORD` | — | Seeded superadmin password |

---

## Project Structure

```
documentation_chat/
├── backend/
│   ├── app/
│   │   ├── core/              # DB base models, security helpers
│   │   ├── db/                # SQLAlchemy session, engine setup
│   │   ├── routers/           # FastAPI route handlers
│   │   │   ├── auth.py        # Login / logout / me
│   │   │   ├── chat.py        # SSE streaming RAG chat
│   │   │   ├── ingest.py      # Document upload & indexing
│   │   │   ├── documents.py   # Document CRUD
│   │   │   ├── collections.py # Collection management
│   │   │   ├── permissions.py # ACL management
│   │   │   ├── users.py       # User management
│   │   │   └── roles.py       # Role management
│   │   ├── services/
│   │   │   ├── rag.py              # RAG orchestration: retrieval, reranking, streaming
│   │   │   ├── reranker.py         # BGE cross-encoder reranker (transformers)
│   │   │   ├── embedder.py         # BGE-M3 + Gemma-4 image captioning
│   │   │   ├── vector_store.py     # ChromaDB operations
│   │   │   ├── ingest_pipeline.py  # Async ingestion pipeline
│   │   │   ├── file_storage.py     # Local file I/O
│   │   │   └── parsers/
│   │   │       ├── pdf_parser.py   # PyMuPDF + pdfplumber
│   │   │       ├── docx_parser.py
│   │   │       ├── pptx_parser.py
│   │   │       ├── xlsx_parser.py
│   │   │       └── image_parser.py
│   │   ├── utils/
│   │   │   ├── model_manager.py    # Loads all 4 models; get_vision_llm / get_chat_llm / get_reranker / get_embedder
│   │   │   └── inference_queue.py  # FIFO semaphore shared by Gemma-4 + Llama-3.2
│   │   ├── config.py          # Pydantic settings from .env
│   │   ├── schemas.py         # Pydantic request/response models
│   │   ├── dependencies.py    # FastAPI dependency injection
│   │   ├── main.py            # App factory, lifespan, middleware
│   │   └── seed.py            # Initial admin user seeding
│   ├── sql/                   # Raw SQL migration scripts
│   ├── download_models.py     # One-time model weight downloader (5 artifacts)
│   ├── .env.example           # Environment variable template
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── chat/page.tsx      # Main chat interface
│   │   ├── admin/page.tsx     # Admin panel (users, roles, permissions)
│   │   └── login/page.tsx
│   ├── components/
│   │   ├── chat/              # ChatWindow, MessageBubble, SourcesPanel
│   │   └── ui/                # Shared UI primitives
│   ├── lib/
│   │   ├── api.ts             # Typed API client
│   │   └── auth-context.tsx   # Auth state + token management
│   └── types/index.ts         # Shared TypeScript types
└── README.md
```
