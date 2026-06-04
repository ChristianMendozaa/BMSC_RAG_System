"""
Hard-delete de documentos: borra todo rastro (BD, archivos, vectores, caché).

Usar solo cuando se requiere liberar espacio o purgar definitivamente. La ruta
normal de borrado es marcar status='OBSOLETE'.
"""
import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import response_cache
from app.config import settings
from app.db.models.document import PGDocument
from app.db.models.rag_document_image import RagDocumentImage
from app.db.models.document_version import DocumentVersion
from app.db.models.rag_document import RagDocument
from app.services import file_storage, vector_store

logger = logging.getLogger(__name__)


async def hard_delete_document(db: AsyncSession, doc_id: uuid.UUID) -> None:
    """
    Borra completamente un documento:
      1. Vectores en ChromaDB.
      2. Archivos físicos (versiones y carpeta de imágenes).
      3. Filas en rag_documents (CASCADE limpia chunks, document_images, figures).
      4. Filas en documents (CASCADE limpia document_versions y permisos).

    No comitea — el caller maneja la transacción.
    """
    pg_doc = await db.scalar(select(PGDocument).where(PGDocument.id == doc_id))
    if pg_doc is None:
        return

    # 1. Caché de respuestas LLM
    n = await asyncio.to_thread(response_cache.invalidate_by_doc_id, str(doc_id))
    if n:
        logger.info("hard_delete doc=%s: invalidadas %d respuestas cacheadas", doc_id, n)

    # 2. ChromaDB
    try:
        await vector_store.delete_by_doc_id(str(doc_id))
    except Exception as exc:
        logger.warning("Vector delete falló doc=%s: %s", doc_id, exc)

    # 2. Archivos físicos: documentos
    versions_res = await db.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == doc_id)
    )
    for ver in versions_res.scalars():
        try:
            await file_storage.delete_object(settings.minio_bucket_documents, ver.file_path)
        except Exception as exc:
            logger.warning("File delete falló %s: %s", ver.file_path, exc)
    # Carpeta entera del doc en el bucket de documentos
    await file_storage.delete_objects_with_prefix(settings.minio_bucket_documents, f"{doc_id}/")

    # Imágenes asociadas
    images_res = await db.execute(
        select(RagDocumentImage).where(RagDocumentImage.document_id == doc_id)
    )
    for img in images_res.scalars():
        try:
            await file_storage.delete_object(settings.minio_bucket_images, img.minio_path)
        except Exception as exc:
            logger.warning("Image delete falló %s: %s", img.minio_path, exc)
    await file_storage.delete_objects_with_prefix(settings.minio_bucket_images, f"{doc_id}/")

    # 3-4. BD — CASCADE limpia tablas hijas
    rag_doc = await db.scalar(select(RagDocument).where(RagDocument.id == doc_id))
    if rag_doc is not None:
        await db.delete(rag_doc)
    await db.delete(pg_doc)
    await db.flush()
