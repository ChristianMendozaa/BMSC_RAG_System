import asyncio
import logging
import shutil
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def _bucket_root(bucket: str) -> Path:
    return Path(settings.storage_path) / bucket


def _object_path(bucket: str, object_name: str) -> Path:
    return _bucket_root(bucket) / object_name


def _ensure_buckets_sync() -> None:
    for bucket in (settings.minio_bucket_documents, settings.minio_bucket_images):
        _bucket_root(bucket).mkdir(parents=True, exist_ok=True)
    logger.info("Local storage buckets ready at: %s", settings.storage_path)


async def ensure_buckets() -> None:
    await asyncio.to_thread(_ensure_buckets_sync)


async def upload_bytes(
    bucket: str,
    object_name: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    def _write() -> None:
        path = _object_path(bucket, object_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    await asyncio.to_thread(_write)
    logger.debug("Stored %s/%s (%d bytes)", bucket, object_name, len(data))
    return object_name


async def get_object_bytes(bucket: str, object_name: str) -> bytes:
    path = _object_path(bucket, object_name)
    return await asyncio.to_thread(path.read_bytes)


async def delete_object(bucket: str, object_name: str) -> None:
    def _delete() -> None:
        path = _object_path(bucket, object_name)
        path.unlink(missing_ok=True)

    try:
        await asyncio.to_thread(_delete)
    except Exception as exc:
        logger.warning("Delete error for %s/%s: %s", bucket, object_name, exc)


async def delete_objects_with_prefix(bucket: str, prefix: str) -> None:
    def _delete_dir() -> None:
        # prefix is always "{doc_id}/" — delete that whole subdirectory
        target = (_bucket_root(bucket) / prefix.rstrip("/")).resolve()
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            logger.debug("Deleted storage dir: %s", target)

    try:
        await asyncio.to_thread(_delete_dir)
    except Exception as exc:
        logger.warning("Prefix delete error for %s/%s: %s", bucket, prefix, exc)


async def check_health() -> bool:
    try:
        root = Path(settings.storage_path)
        return root.exists() and root.is_dir()
    except Exception:
        return False
