import asyncio
import logging
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.config import settings

logger = logging.getLogger(__name__)

_client: QdrantClient | None = None


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        db_path = Path(settings.qdrant_path)
        db_path.mkdir(parents=True, exist_ok=True)
        _client = QdrantClient(path=str(db_path))
        logger.info("Qdrant embedded mode at: %s", db_path)
    return _client


def _point_id(doc_id: str, index: int) -> str:
    base = uuid.UUID(doc_id).int
    return str(uuid.UUID(int=(base + index) % (2**128)))


def _image_point_id(image_id: str) -> str:
    """Stable point ID for the visual collection — derived from image_id (a UUID)."""
    return image_id  # image_id is already a UUID string


def _get_stored_dims(client: QdrantClient, collection_name: str) -> int | None:
    try:
        info = client.get_collection(collection_name)
        vectors = info.config.params.vectors
        if vectors is None:
            return None
        if hasattr(vectors, "size"):
            return int(vectors.size)
        if isinstance(vectors, dict) and vectors:
            first = next(iter(vectors.values()))
            return int(first.size)
    except Exception as exc:
        logger.warning("Could not read collection dims: %s", exc)
    return None


def _ensure_collection(client: QdrantClient, name: str, dims: int) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if name in existing:
        stored = _get_stored_dims(client, name)
        if stored is None:
            logger.warning("Cannot read dims for '%s' — recreating.", name)
            client.delete_collection(name)
        elif stored != dims:
            logger.warning(
                "Collection '%s' has %d dims but config expects %d — recreating.",
                name, stored, dims,
            )
            client.delete_collection(name)
        else:
            logger.info("Qdrant collection '%s' OK (%d dims).", name, stored)
            return

    client.create_collection(
        collection_name=name,
        vectors_config=qmodels.VectorParams(size=dims, distance=qmodels.Distance.COSINE),
    )
    try:
        client.create_payload_index(
            collection_name=name,
            field_name="doc_id",
            field_schema=qmodels.PayloadSchemaType.KEYWORD,
        )
    except Exception as exc:
        logger.warning("Could not create payload index for '%s': %s", name, exc)
    logger.info("Created Qdrant collection: %s (%d dims)", name, dims)


def _ensure_collections_sync() -> None:
    client = get_client()
    _ensure_collection(client, settings.qdrant_collection_text, settings.embedding_dims)
    _ensure_collection(client, settings.qdrant_collection_image_visual, settings.clip_dims)


async def ensure_collections() -> None:
    await asyncio.to_thread(_ensure_collections_sync)


# ── Text collection (texto + descripciones de imagen, MiniLM 384 dims) ─────
async def upsert_chunk(
    doc_id: str,
    chunk_index: int,
    vector: list[float],
    payload: dict,
) -> None:
    if len(vector) != settings.embedding_dims:
        raise ValueError(
            f"Vector dim mismatch: got {len(vector)}, collection expects "
            f"{settings.embedding_dims}. Delete backend/data/qdrant and restart."
        )

    def _upsert() -> None:
        client = get_client()
        point = qmodels.PointStruct(
            id=_point_id(doc_id, chunk_index),
            vector=vector,
            payload={"doc_id": doc_id, **payload},
        )
        client.upsert(
            collection_name=settings.qdrant_collection_text,
            points=[point],
        )

    await asyncio.to_thread(_upsert)


async def upsert_chunks_batch(
    doc_id: str,
    chunks_data: list[dict],
) -> None:
    """Upsert all chunks in a single Qdrant call — faster than N individual upserts.

    Each item in chunks_data must have keys: chunk_index (int), vector (list[float]), payload (dict).
    """
    if not chunks_data:
        return

    def _upsert() -> None:
        client = get_client()
        points = []
        for item in chunks_data:
            vector = item["vector"]
            if len(vector) != settings.embedding_dims:
                raise ValueError(
                    f"Vector dim mismatch: got {len(vector)}, collection expects "
                    f"{settings.embedding_dims}."
                )
            points.append(qmodels.PointStruct(
                id=_point_id(doc_id, item["chunk_index"]),
                vector=vector,
                payload={"doc_id": doc_id, **item["payload"]},
            ))
        client.upsert(
            collection_name=settings.qdrant_collection_text,
            points=points,
        )

    await asyncio.to_thread(_upsert)


async def search(
    query_vector: list[float],
    top_k: int,
    doc_ids: list[str] | None = None,
) -> list[qmodels.ScoredPoint]:
    def _search() -> list[qmodels.ScoredPoint]:
        client = get_client()
        query_filter = None
        if doc_ids:
            query_filter = qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="doc_id",
                        match=qmodels.MatchAny(any=doc_ids),
                    )
                ]
            )
        result = client.query_points(
            collection_name=settings.qdrant_collection_text,
            query=query_vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        return result.points

    return await asyncio.to_thread(_search)


# ── Visual collection (imágenes embebidas con CLIP, 512 dims) ──────────────
async def upsert_image_visual(
    doc_id: str,
    image_id: str,
    vector: list[float],
    payload: dict,
) -> None:
    if len(vector) != settings.clip_dims:
        raise ValueError(
            f"Visual vector dim mismatch: got {len(vector)}, collection expects "
            f"{settings.clip_dims}."
        )

    def _upsert() -> None:
        client = get_client()
        point = qmodels.PointStruct(
            id=_image_point_id(image_id),
            vector=vector,
            payload={"doc_id": doc_id, "image_id": image_id, **payload},
        )
        client.upsert(
            collection_name=settings.qdrant_collection_image_visual,
            points=[point],
        )

    await asyncio.to_thread(_upsert)


async def search_image_visual(
    query_vector: list[float],
    top_k: int,
    doc_ids: list[str] | None = None,
) -> list[qmodels.ScoredPoint]:
    def _search() -> list[qmodels.ScoredPoint]:
        client = get_client()
        query_filter = None
        if doc_ids:
            query_filter = qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="doc_id",
                        match=qmodels.MatchAny(any=doc_ids),
                    )
                ]
            )
        try:
            result = client.query_points(
                collection_name=settings.qdrant_collection_image_visual,
                query=query_vector,
                limit=top_k,
                query_filter=query_filter,
                with_payload=True,
            )
            return result.points
        except Exception as exc:
            # Empty collection or not yet created — degrade gracefully
            logger.debug("Visual search returned no points: %s", exc)
            return []

    return await asyncio.to_thread(_search)


async def delete_by_doc_id(doc_id: str) -> None:
    def _delete() -> None:
        client = get_client()
        doc_filter = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="doc_id",
                    match=qmodels.MatchValue(value=doc_id),
                )
            ]
        )
        for collection in (
            settings.qdrant_collection_text,
            settings.qdrant_collection_image_visual,
        ):
            try:
                client.delete(
                    collection_name=collection,
                    points_selector=qmodels.FilterSelector(filter=doc_filter),
                )
            except Exception as exc:
                logger.warning("Failed to delete points from '%s': %s", collection, exc)
        logger.info("Deleted Qdrant points for doc_id=%s", doc_id)

    await asyncio.to_thread(_delete)


async def check_health() -> bool:
    def _check() -> bool:
        try:
            get_client().get_collections()
            return True
        except Exception:
            return False

    return await asyncio.to_thread(_check)
