"""Nivel 2: caché persistente de respuestas LLM (SQLite, TTL 24 horas)."""

import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path

_TTL = 24 * 3600  # 24 horas en segundos
_DB_PATH: str = ""


def init_db(cache_dir: str) -> None:
    global _DB_PATH
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    _DB_PATH = str(Path(cache_dir) / "responses.db")
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS responses (
                key          TEXT PRIMARY KEY,
                response     TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                created_at   REAL NOT NULL,
                hit_count    INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS response_docs (
                key    TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                PRIMARY KEY (key, doc_id)
            );
            CREATE INDEX IF NOT EXISTS idx_response_docs_doc ON response_docs(doc_id);
        """)
        conn.commit()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def _key(text: str) -> str:
    return hashlib.md5(_normalize(text).encode()).hexdigest()


def get(message: str) -> tuple[str, list[dict]] | None:
    """Retorna (response_text, sources) o None si no existe / expiró."""
    if not _DB_PATH:
        return None
    k = _key(message)
    now = time.time()
    with _connect() as conn:
        row = conn.execute(
            "SELECT response, sources_json, created_at FROM responses WHERE key = ?", (k,)
        ).fetchone()
        if row is None:
            return None
        response, sources_json, created_at = row
        if now - created_at > _TTL:
            conn.execute("DELETE FROM responses WHERE key = ?", (k,))
            conn.execute("DELETE FROM response_docs WHERE key = ?", (k,))
            conn.commit()
            return None
        conn.execute(
            "UPDATE responses SET hit_count = hit_count + 1 WHERE key = ?", (k,)
        )
        conn.commit()
    return response, json.loads(sources_json)


def set(message: str, response: str, sources: list[dict]) -> None:
    """Guarda respuesta e indexa los doc_ids usados como fuente."""
    if not _DB_PATH:
        return
    k = _key(message)
    now = time.time()
    doc_ids = list({s["doc_id"] for s in sources if s.get("doc_id")})
    with _connect() as conn:
        conn.execute(
            """INSERT INTO responses(key, response, sources_json, created_at, hit_count)
               VALUES (?, ?, ?, ?, 0)
               ON CONFLICT(key) DO UPDATE SET
                 response     = excluded.response,
                 sources_json = excluded.sources_json,
                 created_at   = excluded.created_at""",
            (k, response, json.dumps(sources), now),
        )
        conn.execute("DELETE FROM response_docs WHERE key = ?", (k,))
        conn.executemany(
            "INSERT OR IGNORE INTO response_docs(key, doc_id) VALUES (?, ?)",
            [(k, d) for d in doc_ids],
        )
        conn.commit()


def invalidate_by_doc_id(doc_id: str) -> int:
    """Elimina todas las respuestas que usaron doc_id como fuente. Retorna N eliminadas."""
    if not _DB_PATH:
        return 0
    with _connect() as conn:
        keys = [
            r[0]
            for r in conn.execute(
                "SELECT key FROM response_docs WHERE doc_id = ?", (doc_id,)
            ).fetchall()
        ]
        if not keys:
            return 0
        placeholders = ",".join("?" * len(keys))
        conn.execute(f"DELETE FROM responses WHERE key IN ({placeholders})", keys)
        conn.execute(f"DELETE FROM response_docs WHERE key IN ({placeholders})", keys)
        conn.commit()
    return len(keys)
