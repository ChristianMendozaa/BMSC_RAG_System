-- ============================================================
--  MERCANTIL DOCBANK — Schema inicial
--  PostgreSQL 15+
-- ============================================================

-- Tipos enumerados
CREATE TYPE document_status AS ENUM ('ACTIVE', 'OBSOLETE');
CREATE TYPE index_status    AS ENUM ('PENDING', 'INDEXING', 'READY', 'ERROR');


-- ------------------------------------------------------------
--  ROLES
--  Los permisos globales (gestionar usuarios, subir docs, etc.)
--  viven aquí. Los permisos sobre colecciones específicas van
--  en collection_permissions.
--  is_system = true → no se puede eliminar, solo editar.
-- ------------------------------------------------------------
CREATE TABLE roles (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    VARCHAR(100) NOT NULL UNIQUE,
    description             TEXT,
    is_system               BOOLEAN     NOT NULL DEFAULT false,
    can_manage_users        BOOLEAN     NOT NULL DEFAULT false,
    can_manage_collections  BOOLEAN     NOT NULL DEFAULT false,
    can_upload_documents    BOOLEAN     NOT NULL DEFAULT false,
    can_delete_documents    BOOLEAN     NOT NULL DEFAULT false,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ------------------------------------------------------------
--  USERS
--  created_by es nullable para el primer superadmin (no tiene
--  quién lo haya creado).
-- ------------------------------------------------------------
-- role_id es nullable: cuando se elimina un rol custom, los usuarios que lo
-- tenían quedan huérfanos (role_id = NULL). Un admin debe asignarles otro rol
-- antes de que puedan loguearse de nuevo (el login bloquea usuarios sin rol).
--
-- tokens_valid_after: marca temporal que invalida todos los JWT emitidos antes
-- de ese instante. Se actualiza cuando un admin resetea la contraseña o
-- reactiva al usuario, forzando re-login sin necesidad de tracking de JTIs.
CREATE TABLE users (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    username            VARCHAR(100) NOT NULL UNIQUE,
    hashed_password     VARCHAR(255) NOT NULL,
    role_id             UUID         REFERENCES roles(id) ON DELETE SET NULL,
    is_active           BOOLEAN      NOT NULL DEFAULT true,
    tokens_valid_after  TIMESTAMPTZ,
    created_by          UUID         REFERENCES users(id),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);


-- ------------------------------------------------------------
--  COLLECTIONS
-- ------------------------------------------------------------
CREATE TABLE collections (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(200) NOT NULL UNIQUE,
    description TEXT,
    is_active   BOOLEAN      NOT NULL DEFAULT true,
    created_by  UUID         REFERENCES users(id),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);


-- ------------------------------------------------------------
--  COLLECTION_PERMISSIONS  (acceso por rol a una colección)
--  Una fila por cada combinación rol+colección.
--  Cuando se crea una colección se insertan filas para todos
--  los roles existentes con todo en false por defecto.
-- ------------------------------------------------------------
CREATE TABLE collection_permissions (
    id            UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id       UUID    NOT NULL REFERENCES roles(id)       ON DELETE CASCADE,
    collection_id UUID    NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    can_view      BOOLEAN NOT NULL DEFAULT false,
    can_download  BOOLEAN NOT NULL DEFAULT false,
    can_chat      BOOLEAN NOT NULL DEFAULT false,
    CONSTRAINT uq_role_collection UNIQUE (role_id, collection_id)
);


-- ------------------------------------------------------------
--  USER_COLLECTION_PERMISSIONS  (excepción individual por colección)
--  Sobreescribe lo que define collection_permissions para ese
--  usuario en particular. Puede ampliar o restringir su rol.
-- ------------------------------------------------------------
CREATE TABLE user_collection_permissions (
    id            UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID    NOT NULL REFERENCES users(id)       ON DELETE CASCADE,
    collection_id UUID    NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    can_view      BOOLEAN NOT NULL DEFAULT false,
    can_download  BOOLEAN NOT NULL DEFAULT false,
    can_chat      BOOLEAN NOT NULL DEFAULT false,
    CONSTRAINT uq_user_collection UNIQUE (user_id, collection_id)
);


-- ------------------------------------------------------------
--  DOCUMENTS  (registro lógico — no guarda el archivo)
--  collection_id es nullable: documentos sin colección quedan en la
--  categoría "Sin colección" (puede pasar al subir sin asignar, o cuando
--  se elimina la colección y se opta por marcar los docs como obsoletos).
--  ON DELETE SET NULL: al borrar una colección con documentos en modo
--  "obsoletizar", los documentos sobreviven sin colección.
-- ------------------------------------------------------------
CREATE TABLE documents (
    id            UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    title         VARCHAR(500)    NOT NULL,
    collection_id UUID            REFERENCES collections(id) ON DELETE SET NULL,
    status        document_status NOT NULL DEFAULT 'ACTIVE',
    created_by    UUID            REFERENCES users(id),
    created_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);


-- ------------------------------------------------------------
--  ROLE_DOCUMENT_PERMISSIONS  (acceso por rol a un documento específico)
--  Permite que un rol tenga acceso a documentos individuales
--  independientemente de su acceso a la colección.
--
--  Orden de resolución de permisos para acceso a documento:
--  1. user_document_permissions  (override de usuario)
--  2. role_document_permissions  (permiso de rol en doc)
--  3. user_collection_permissions (override de usuario en colección)
--  4. collection_permissions      (permiso de rol en colección)
--  5. Sin acceso por defecto
-- ------------------------------------------------------------
CREATE TABLE role_document_permissions (
    id           UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id      UUID    NOT NULL REFERENCES roles(id)     ON DELETE CASCADE,
    document_id  UUID    NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    can_view     BOOLEAN NOT NULL DEFAULT false,
    can_download BOOLEAN NOT NULL DEFAULT false,
    can_chat     BOOLEAN NOT NULL DEFAULT false,
    CONSTRAINT uq_role_document UNIQUE (role_id, document_id)
);


-- ------------------------------------------------------------
--  USER_DOCUMENT_PERMISSIONS  (override individual por documento)
--  Prioridad más alta en el orden de resolución. Permite
--  conceder o restringir acceso a un documento específico
--  sin afectar el acceso a la colección completa.
-- ------------------------------------------------------------
CREATE TABLE user_document_permissions (
    id           UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID    NOT NULL REFERENCES users(id)     ON DELETE CASCADE,
    document_id  UUID    NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    can_view     BOOLEAN NOT NULL DEFAULT false,
    can_download BOOLEAN NOT NULL DEFAULT false,
    can_chat     BOOLEAN NOT NULL DEFAULT false,
    CONSTRAINT uq_user_document UNIQUE (user_id, document_id)
);


-- ------------------------------------------------------------
--  DOCUMENT_VERSIONS  (aquí vive el archivo real en disco)
--  file_path: ruta relativa desde STORAGE_PATH
--    ej: "documents/{doc_id}/v1/manual.pdf"
--  mime_type: necesario para servir el archivo correctamente
--    ej: "application/pdf", "application/vnd.openxmlformats..."
-- ------------------------------------------------------------
CREATE TABLE document_versions (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id       UUID         NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version_number    INTEGER      NOT NULL,
    original_filename VARCHAR(500) NOT NULL,
    file_path         VARCHAR(1000) NOT NULL,
    file_size_bytes   INTEGER      NOT NULL,
    mime_type         VARCHAR(100) NOT NULL,
    is_current        BOOLEAN      NOT NULL DEFAULT false,
    index_status      index_status NOT NULL DEFAULT 'PENDING',
    change_notes      TEXT,
    created_by        UUID         REFERENCES users(id),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_document_version UNIQUE (document_id, version_number)
);


-- ------------------------------------------------------------
--  REVOKED_TOKENS  (reemplaza Redis para JWT blacklist)
--  Limpiar periódicamente con:
--    DELETE FROM revoked_tokens WHERE expires_at < NOW();
-- ------------------------------------------------------------
CREATE TABLE revoked_tokens (
    jti        UUID        PRIMARY KEY,
    user_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL
);


-- ============================================================
--  RAG METADATA TABLES  (migradas desde SQLite)
-- ============================================================

-- rag_documents: equivalente al SQLite `documents`.
-- Nombrado rag_documents para evitar colisión con `documents` (DMS).
-- id se provee explícitamente desde la app (UUID4); puede coincidir
-- con documents.id cuando la subida viene por la ruta pg-documents.
CREATE TABLE rag_documents (
    id                  UUID         PRIMARY KEY,
    role_id             UUID         REFERENCES roles(id) ON DELETE SET NULL,
    filename            VARCHAR(500) NOT NULL,
    original_filename   VARCHAR(500) NOT NULL,
    file_type           VARCHAR(50)  NOT NULL,
    file_size           INTEGER      NOT NULL,
    status              VARCHAR(50)  NOT NULL DEFAULT 'pending',
    error_message       TEXT,
    chunk_count         INTEGER      NOT NULL DEFAULT 0,
    image_count         INTEGER      NOT NULL DEFAULT 0,
    minio_path          VARCHAR(1000),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE chunks (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID        NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
    content       TEXT        NOT NULL,
    chunk_index   INTEGER     NOT NULL,
    page_number   INTEGER,
    chunk_type    VARCHAR(50) NOT NULL DEFAULT 'text',
    metadata_json TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE document_images (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID         NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
    minio_path    VARCHAR(1000) NOT NULL,
    page_number   INTEGER,
    image_index   INTEGER      NOT NULL,
    description   TEXT,
    ocr_text      TEXT,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE document_figures (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID        NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
    figure_number INTEGER     NOT NULL,
    page_number   INTEGER,
    caption       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE chat_sessions (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           VARCHAR(200) NOT NULL,
    collection_id   UUID         REFERENCES collections(id) ON DELETE SET NULL,
    document_ids    UUID[]       NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE chat_messages (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   UUID        NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role         VARCHAR(20) NOT NULL,
    content      TEXT        NOT NULL,
    sources_json TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ============================================================
--  ÍNDICES
-- ============================================================

CREATE INDEX idx_users_role_id    ON users(role_id);
CREATE INDEX idx_users_is_active  ON users(is_active);
-- Listar rápido usuarios huérfanos (sin rol asignado) en el panel admin.
CREATE INDEX idx_users_no_role    ON users(id) WHERE role_id IS NULL;

CREATE INDEX idx_col_perms_role       ON collection_permissions(role_id);
CREATE INDEX idx_col_perms_collection ON collection_permissions(collection_id);

CREATE INDEX idx_user_col_perms_user  ON user_collection_permissions(user_id);
CREATE INDEX idx_user_col_perms_col   ON user_collection_permissions(collection_id);

CREATE INDEX idx_documents_collection     ON documents(collection_id);
CREATE INDEX idx_documents_status         ON documents(status);
-- Filtro "solo sin colección" en el panel admin.
CREATE INDEX idx_documents_uncategorized  ON documents(id) WHERE collection_id IS NULL;

-- Permisos de documento por rol y por usuario
CREATE INDEX idx_role_doc_perms_role ON role_document_permissions(role_id);
CREATE INDEX idx_role_doc_perms_doc  ON role_document_permissions(document_id);
CREATE INDEX idx_user_doc_perms_user ON user_document_permissions(user_id);
CREATE INDEX idx_user_doc_perms_doc  ON user_document_permissions(document_id);

-- Este índice es el más consultado: "dame la versión actual de este documento"
CREATE INDEX idx_versions_current ON document_versions(document_id, is_current);
CREATE INDEX idx_versions_status  ON document_versions(index_status);

CREATE INDEX idx_revoked_expires ON revoked_tokens(expires_at);

CREATE INDEX idx_rag_docs_status    ON rag_documents(status);
CREATE INDEX idx_rag_docs_role      ON rag_documents(role_id);
CREATE INDEX idx_chunks_doc         ON chunks(document_id);
CREATE INDEX idx_doc_images_doc     ON document_images(document_id);
CREATE INDEX idx_doc_images_page    ON document_images(document_id, page_number);
CREATE INDEX idx_doc_figures_doc    ON document_figures(document_id);
CREATE INDEX idx_chat_sessions_user ON chat_sessions(user_id, updated_at DESC);
CREATE INDEX idx_chat_messages_session ON chat_messages(session_id, created_at);


-- ============================================================
--  TRIGGER para updated_at automático
--  Se aplica a todas las tablas que tienen esa columna.
-- ============================================================
CREATE OR REPLACE FUNCTION fn_update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

CREATE TRIGGER trg_collections_updated_at
    BEFORE UPDATE ON collections
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

CREATE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

CREATE TRIGGER trg_rag_documents_updated_at
    BEFORE UPDATE ON rag_documents
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

CREATE TRIGGER trg_chat_sessions_updated_at
    BEFORE UPDATE ON chat_sessions
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();


-- ============================================================
--  DATOS INICIALES
--  Roles del sistema que siempre deben existir.
--  El primer usuario SUPERADMIN se crea desde backend/app/seed.py
--
--  VISITANTE: rol de solo consulta. Sin permisos globales.
--  El acceso a colecciones y documentos se asigna manualmente
--  desde el panel de administración mediante collection_permissions
--  y las tablas de permisos por documento.
-- ============================================================
INSERT INTO roles (name, description, is_system, can_manage_users, can_manage_collections, can_upload_documents, can_delete_documents)
VALUES
    ('SUPERADMIN', 'Control total del sistema',                                              true,  true,  true,  true,  true),
    ('ADMIN',      'Gestión de documentos y colecciones',                                    true,  false, true,  true,  true),
    ('VISITANTE',  'Acceso de solo consulta a colecciones y documentos asignados por admin', true,  false, false, false, false);
