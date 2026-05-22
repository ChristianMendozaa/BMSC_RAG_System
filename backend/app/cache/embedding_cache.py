"""Nivel 1: caché persistente de embeddings de consultas (SQLite, TTL 30 días)."""

import hashlib
import re
import sqlite3
import time
from pathlib import Path

import numpy as np

_TTL = 30 * 24 * 3600  # 30 días en segundos
_DB_PATH: str = ""


def init_db(cache_dir: str) -> None:
    global _DB_PATH
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    _DB_PATH = str(Path(cache_dir) / "embeddings.db")
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                key        TEXT PRIMARY KEY,
                vector     BLOB NOT NULL,
                created_at REAL NOT NULL,
                last_used  REAL NOT NULL,
                hit_count  INTEGER DEFAULT 0
            )
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


def get(text: str) -> list[float] | None:
    """Retorna vector cacheado o None si no existe / expiró."""
    if not _DB_PATH:
        return None
    k = _key(text)
    now = time.time()
    with _connect() as conn:
        row = conn.execute(
            "SELECT vector, created_at FROM embeddings WHERE key = ?", (k,)
        ).fetchone()
        if row is None:
            return None
        vector_bytes, created_at = row
        if now - created_at > _TTL:
            conn.execute("DELETE FROM embeddings WHERE key = ?", (k,))
            conn.commit()
            return None
        conn.execute(
            "UPDATE embeddings SET hit_count = hit_count + 1, last_used = ? WHERE key = ?",
            (now, k),
        )
        conn.commit()
    return np.frombuffer(vector_bytes, dtype=np.float32).tolist()


def set(text: str, vector: list[float]) -> None:
    if not _DB_PATH:
        return
    k = _key(text)
    now = time.time()
    blob = np.array(vector, dtype=np.float32).tobytes()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO embeddings(key, vector, created_at, last_used, hit_count)
               VALUES (?, ?, ?, ?, 0)
               ON CONFLICT(key) DO UPDATE SET
                 vector     = excluded.vector,
                 created_at = excluded.created_at,
                 last_used  = excluded.last_used""",
            (k, blob, now, now),
        )
        conn.commit()
