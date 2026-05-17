import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings

logger = logging.getLogger(__name__)

_client: Optional[Any] = None
_collection: Optional[Any] = None


def _get_collection() -> Any:
    global _client, _collection
    if _collection is None:
        db_path = Path(settings.chroma_path)
        db_path.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(db_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        _collection = _client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "ChromaDB colección '%s' lista en: %s",
            settings.chroma_collection, db_path,
        )
    return _collection


async def ensure_collections() -> None:
    """Inicializa la colección ChromaDB al arrancar el servidor."""
    await asyncio.to_thread(_get_collection)


async def upsert_chunks_batch(doc_id: str, chunks_data: list[dict]) -> None:
    """Inserta o actualiza chunks en ChromaDB.

    Cada item en chunks_data debe tener:
      chunk_index (int), vector (list[float]), payload (dict).

    El payload debe contener: content, filename, page_number, chunk_type
    y opcionalmente: image_id, caption, ocr_text, fig_caption.

    ChromaDB requiere IDs string y metadata sin valores None.
    """
    if not chunks_data:
        return

    def _upsert() -> None:
        col = _get_collection()
        ids = []
        embeddings = []
        documents = []
        metadatas = []

        for item in chunks_data:
            chunk_id = f"{doc_id}_{item['chunk_index']}"
            ids.append(chunk_id)
            embeddings.append(item["vector"])
            payload = item["payload"]
            documents.append(payload.get("content", ""))

            # ChromaDB rechaza None en metadata — usar valores por defecto seguros
            page_num = payload.get("page_number")
            metadatas.append({
                "doc_id": doc_id,
                "filename": payload.get("filename") or "",
                "page_number": page_num if page_num is not None else -1,
                "chunk_type": payload.get("chunk_type") or "text",
                "image_id": payload.get("image_id") or "",
                "image_ids": payload.get("image_ids") or "",
                "caption": payload.get("caption") or "",
                "ocr_text": payload.get("ocr_text") or "",
                "fig_caption": payload.get("fig_caption") or "",
            })

        col.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    await asyncio.to_thread(_upsert)


async def search(
    query_vector: list[float],
    top_k: int,
    doc_ids: list[str] | None = None,
) -> list[dict]:
    """Busca los top_k chunks más similares.

    Retorna lista de dicts con keys:
      score, content, doc_id, filename, page_number,
      chunk_type, image_id, caption, ocr_text, fig_caption.

    score = similitud coseno en [0, 1] (1 = idéntico).
    """
    def _search() -> list[dict]:
        col = _get_collection()

        # Guardia: ChromaDB lanza error si n_results > total de items
        total = col.count()
        if total == 0:
            return []
        actual_k = min(top_k, total)

        where = None
        if doc_ids:
            if len(doc_ids) == 1:
                where = {"doc_id": doc_ids[0]}
            else:
                where = {"doc_id": {"$in": doc_ids}}

        results = col.query(
            query_embeddings=[query_vector],
            n_results=actual_k,
            where=where,
            include=["metadatas", "documents", "distances"],
        )

        hits = []
        ids_list = results["ids"][0]
        distances = results["distances"][0]
        metas = results["metadatas"][0]
        docs = results["documents"][0]

        for i, _chroma_id in enumerate(ids_list):
            meta = metas[i]
            # Distancia coseno ChromaDB ∈ [0,2]: 0=idéntico, 2=opuesto
            score = 1.0 - (distances[i] / 2.0)
            page_num = meta.get("page_number", -1)
            hits.append({
                "score": score,
                "content": docs[i],
                "doc_id": meta.get("doc_id", ""),
                "filename": meta.get("filename", ""),
                "page_number": page_num if page_num != -1 else None,
                "chunk_type": meta.get("chunk_type", "text"),
                "image_id": meta.get("image_id") or None,
                "image_ids": meta.get("image_ids") or "",
                "caption": meta.get("caption") or "",
                "ocr_text": meta.get("ocr_text") or "",
                "fig_caption": meta.get("fig_caption") or "",
            })
        return hits

    return await asyncio.to_thread(_search)


async def delete_by_doc_id(doc_id: str) -> None:
    def _delete() -> None:
        col = _get_collection()
        try:
            col.delete(where={"doc_id": doc_id})
            logger.info("ChromaDB: eliminados vectores para doc_id=%s", doc_id)
        except Exception as exc:
            logger.warning("ChromaDB delete falló para doc_id=%s: %s", doc_id, exc)

    await asyncio.to_thread(_delete)


async def check_health() -> bool:
    def _check() -> bool:
        try:
            _get_collection().count()
            return True
        except Exception:
            return False

    return await asyncio.to_thread(_check)
