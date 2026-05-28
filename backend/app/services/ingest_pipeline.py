import asyncio
import json
import logging
import mimetypes
import re
import time
import uuid as _uuid_mod
from collections import defaultdict

from sqlalchemy import and_, select

from app.config import settings
from app.db.session import PGAsyncSessionLocal as AsyncSessionLocal
from app.db.models.rag_document import RagDocument as Document
from app.db.models.rag_chunk import RagChunk as ChunkModel
from app.db.models.rag_document_image import RagDocumentImage as DocumentImage
from app.db.models.rag_document_figure import RagDocumentFigure as DocumentFigure
from app.db.models.document_version import DocumentVersion

_FIG_CAPTION = re.compile(
    r'\b(Figura|Fig\.?|Diagrama|Tabla|Imagen|Esquema)\s+(\d+)[.:\s]',
    re.IGNORECASE,
)
_CAPTION_EXTRACT_RE = re.compile(
    r'(?:Figura|Fig\.?|Diagrama|Tabla|Imagen|Esquema)\s+\d+[.\s:][^\n]{5,200}',
    re.IGNORECASE,
)
_IMG_MARKER_RE = re.compile(r'\[IMG:([a-f0-9\-]{36})\]')


def _extract_figure_caption(text: str) -> str:
    m = _CAPTION_EXTRACT_RE.search(text)
    return m.group(0).strip()[:200] if m else ""


from app.services import embedder, file_storage, vector_store
from app.services import chunker as chunker_service
from app.services.parsers import pdf_parser, docx_parser, pptx_parser, xlsx_parser, image_parser

logger = logging.getLogger(__name__)

_cancelled_docs: set[str] = set()


def cancel_pipeline(doc_id: str) -> None:
    _cancelled_docs.add(doc_id)


def _is_cancelled(doc_id: str) -> bool:
    return doc_id in _cancelled_docs


def _clear_cancelled(doc_id: str) -> None:
    _cancelled_docs.discard(doc_id)


ACCEPTED_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md",
    ".jpg", ".jpeg", ".png", ".webp",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
TEXT_EXTENSIONS = {".txt", ".md"}

_IMAGE_IO_SEM = asyncio.Semaphore(4)


_RAG_TO_INDEX_STATUS: dict[str, str] = {
    "pending": "PENDING",
    "processing": "INDEXING",
    "indexing_images": "INDEXING",
    "ready": "READY",
    "error": "ERROR",
}


async def _update_doc_status(
    doc_id: str, status: str, error_message: str | None = None, **kwargs
) -> None:
    async with AsyncSessionLocal() as session:
        doc = await session.get(Document, _uuid_mod.UUID(doc_id))
        if doc:
            doc.status = status
            if error_message is not None:
                doc.error_message = error_message
            for k, v in kwargs.items():
                setattr(doc, k, v)

        # Keep DocumentVersion.index_status in sync (skip if no version — legacy ingest path)
        index_status = _RAG_TO_INDEX_STATUS.get(status)
        if index_status:
            ver_res = await session.execute(
                select(DocumentVersion).where(
                    and_(
                        DocumentVersion.document_id == _uuid_mod.UUID(doc_id),
                        DocumentVersion.is_current == True,  # noqa: E712
                    )
                )
            )
            ver = ver_res.scalar_one_or_none()
            if ver is not None:
                ver.index_status = index_status

        await session.commit()


async def _upload_and_store_image(
    doc_id: str,
    img_block,
) -> tuple | None:
    try:
        async with _IMAGE_IO_SEM:
            img_object_name = f"{doc_id}/images/{img_block.image_index}.png"
            await file_storage.upload_bytes(
                settings.minio_bucket_images, img_object_name, img_block.data, "image/png"
            )
        return img_object_name, img_block
    except Exception as exc:
        logger.warning("doc_id=%s: failed to upload image %d: %s", doc_id, img_block.image_index, exc)
        return None


async def run_pipeline(doc_id: str, file_bytes: bytes, filename: str) -> None:
    t_start = time.monotonic()
    logger.info("doc_id=%s: ─── Iniciando ingesta: %r ───", doc_id, filename)

    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    # ── Step 1: Upload original file ──────────────────────────────────────
    logger.info("doc_id=%s: [1/5] Subiendo archivo original...", doc_id)
    try:
        minio_path = f"{doc_id}/{filename}"
        await file_storage.upload_bytes(
            settings.minio_bucket_documents, minio_path, file_bytes, mime_type
        )
        async with AsyncSessionLocal() as session:
            doc = await session.get(Document, _uuid_mod.UUID(doc_id))
            if doc:
                doc.minio_path = minio_path
                await session.commit()
    except Exception as exc:
        logger.error("doc_id=%s: storage upload failed: %s", doc_id, exc)
        await _update_doc_status(doc_id, "error", str(exc))
        return

    await _update_doc_status(doc_id, "processing")

    # ── Step 2: Parse document ─────────────────────────────────────────────
    logger.info("doc_id=%s: [2/5] Parseando documento (%s)...", doc_id, ext)
    try:
        if ext in IMAGE_EXTENSIONS:
            parse_result = image_parser.parse(file_bytes)
        elif ext == ".pdf":
            parse_result = pdf_parser.parse(file_bytes)
        elif ext == ".docx":
            parse_result = docx_parser.parse(file_bytes)
        elif ext == ".pptx":
            parse_result = pptx_parser.parse(file_bytes)
        elif ext == ".xlsx":
            parse_result = xlsx_parser.parse(file_bytes)
        elif ext in TEXT_EXTENSIONS:
            from app.services.parsers.image_parser import ParseResult, TextBlock
            text = file_bytes.decode("utf-8", errors="replace")
            parse_result = ParseResult(
                text_blocks=[TextBlock(text=text, page_number=None)],
                image_blocks=[],
            )
        else:
            raise ValueError(f"Unsupported file extension: {ext}")
    except Exception as exc:
        logger.error("doc_id=%s: parser failed: %s", doc_id, exc)
        await _update_doc_status(doc_id, "error", f"Parser error: {exc}")
        return

    n_text = len(parse_result.text_blocks)
    n_imgs = len(parse_result.image_blocks)
    logger.info(
        "doc_id=%s: parse OK — %d bloques de texto, %d imágenes detectadas",
        doc_id, n_text, n_imgs,
    )

    # ── Step 2b: Index figure-caption references ───────────────────────────
    figure_records: list[DocumentFigure] = []
    seen_fig_keys: set[tuple[str, int]] = set()
    for block in parse_result.text_blocks:
        for m in _FIG_CAPTION.finditer(block.text):
            label = m.group(1).lower().rstrip(".")
            fig_num = int(m.group(2))
            key = (label, fig_num)
            if key not in seen_fig_keys:
                seen_fig_keys.add(key)
                figure_records.append(DocumentFigure(
                    document_id=_uuid_mod.UUID(doc_id),
                    figure_number=fig_num,
                    page_number=block.page_number,
                    caption=m.group(0)[:200],
                ))
    if figure_records:
        async with AsyncSessionLocal() as session:
            for rec in figure_records:
                session.add(rec)
            await session.commit()
        logger.info("doc_id=%s: indexadas %d referencias de figuras", doc_id, len(figure_records))

    # ── Step 3: Upload images to MinIO in parallel ─────────────────────────
    image_blocks = parse_result.image_blocks[:settings.max_images_per_doc]
    total_images = len(image_blocks)

    if total_images > 0:
        logger.info("doc_id=%s: [3/5] Subiendo %d imágenes al almacenamiento...", doc_id, total_images)
        upload_results = await asyncio.gather(
            *[_upload_and_store_image(doc_id, img) for img in image_blocks],
            return_exceptions=True,
        )
    else:
        upload_results = []
        logger.info("doc_id=%s: [3/5] Sin imágenes que procesar", doc_id)

    # ── Step 4: Describe images with Gemma VLM (sequential — not thread-safe) ─
    if _is_cancelled(doc_id):
        logger.info("doc_id=%s: pipeline cancelado antes de describir imágenes", doc_id)
        _clear_cancelled(doc_id)
        return

    await _update_doc_status(doc_id, "indexing_images")

    image_descriptions: dict[int, str] = {}

    if total_images > 0:
        logger.info("doc_id=%s: [4/5] Describiendo imágenes con Gemma (0/%d)...", doc_id, total_images)

    for i, (result_item, img_block) in enumerate(zip(upload_results, image_blocks)):
        if _is_cancelled(doc_id):
            logger.info("doc_id=%s: pipeline cancelado durante descripción de imágenes", doc_id)
            _clear_cancelled(doc_id)
            return

        if isinstance(result_item, Exception) or result_item is None:
            logger.warning("doc_id=%s: [Image %d/%d] upload falló, omitiendo", doc_id, i + 1, total_images)
            continue

        logger.info(
            "doc_id=%s: [Image %d/%d] describiendo imagen en página %s...",
            doc_id, i + 1, total_images, img_block.page_number,
        )
        try:
            description = await embedder.describe_image(img_block.data)
            image_descriptions[img_block.image_index] = description
            logger.info(
                "doc_id=%s: [Image %d/%d] OK — %d caracteres de descripción",
                doc_id, i + 1, total_images, len(description),
            )
        except Exception as exc:
            logger.warning(
                "doc_id=%s: [Image %d/%d] VLM falló: %s",
                doc_id, i + 1, total_images, exc,
            )
            image_descriptions[img_block.image_index] = ""

    # ── Step 5: Save image records to DB → get UUIDs ──────────────────────
    doc_uuid = _uuid_mod.UUID(doc_id)

    # Collect successfully uploaded images
    valid_images: list[tuple[str, object]] = []
    for result_item, img_block in zip(upload_results, image_blocks):
        if isinstance(result_item, Exception) or result_item is None:
            continue
        img_object_name, _ = result_item
        valid_images.append((img_object_name, img_block))

    db_image_records: list[DocumentImage] = []
    if valid_images:
        logger.info("doc_id=%s: guardando %d registros de imágenes en BD", doc_id, len(valid_images))
        async with AsyncSessionLocal() as session:
            for img_object_name, img_block in valid_images:
                rec = DocumentImage(
                    document_id=doc_uuid,
                    minio_path=img_object_name,
                    page_number=img_block.page_number,
                    image_index=img_block.image_index,
                    description=image_descriptions.get(img_block.image_index, ""),
                    ocr_text=None,
                )
                session.add(rec)
                db_image_records.append(rec)
            await session.commit()
            for rec in db_image_records:
                await session.refresh(rec)

    image_index_to_uuid: dict[int, str] = {
        rec.image_index: str(rec.id) for rec in db_image_records
    }

    # ── Step 6: Build merged per-page content with inline [IMG:uuid] markers ─
    logger.info("doc_id=%s: [4/5] Construyendo contenido fusionado con imágenes inline...", doc_id)

    page_text_map: dict = defaultdict(list)
    for tb in parse_result.text_blocks:
        page_text_map[tb.page_number].append(tb)

    page_image_map: dict = defaultdict(list)
    for img_object_name, img_block in valid_images:
        img_uuid = image_index_to_uuid.get(img_block.image_index)
        if img_uuid:
            page_image_map[img_block.page_number].append((img_block, img_uuid))

    all_pages = sorted(
        set(page_text_map.keys()) | set(page_image_map.keys()),
        key=lambda p: (p is None, p or 0),
    )

    merged_blocks: list[dict] = []
    for page in all_pages:
        items: list[tuple[float, str, object]] = []

        for tb in page_text_map.get(page, []):
            items.append((getattr(tb, "y_position", 0.0), "text", tb))

        for img_block, img_uuid in page_image_map.get(page, []):
            items.append((getattr(img_block, "y_position", 0.0), "image", (img_block, img_uuid)))

        items.sort(key=lambda x: x[0])

        parts: list[str] = []
        for _, kind, payload in items:
            if kind == "text":
                parts.append(payload.text.strip())
            else:
                img_block, img_uuid = payload
                desc = image_descriptions.get(img_block.image_index, "").strip()
                parts.append(f"\n[IMG:{img_uuid}]\n{desc}\n")

        if parts:
            merged_blocks.append({
                "text": "\n\n".join(parts),
                "page_number": page,
                "block_type": "text",
            })

    logger.info("doc_id=%s: %d páginas fusionadas", doc_id, len(merged_blocks))

    # ── Step 7: Chunk + embed + upsert (single pass) ──────────────────────
    logger.info("doc_id=%s: [5/5] Chunking + embedding del contenido fusionado...", doc_id)
    chunks = chunker_service.chunk_text_blocks(merged_blocks)
    logger.info("doc_id=%s: %d chunks generados", doc_id, len(chunks))

    if not chunks:
        logger.info("doc_id=%s: sin chunks, finalizando", doc_id)
        _clear_cancelled(doc_id)
        await _update_doc_status(
            doc_id, "ready", None,
            chunk_count=0, image_count=len(db_image_records),
        )
        return

    texts = [c.content for c in chunks]
    try:
        vectors = await embedder.embed_texts_batch(texts)
    except Exception as exc:
        logger.error("doc_id=%s: batch embedding falló: %s", doc_id, exc)
        await _update_doc_status(doc_id, "error", f"Embedding error: {exc}")
        return

    logger.info("doc_id=%s: embeddings listos, subiendo %d chunks a ChromaDB...", doc_id, len(chunks))

    chroma_items = []
    for i, chunk in enumerate(chunks):
        if i >= len(vectors):
            break
        found_ids = _IMG_MARKER_RE.findall(chunk.content)
        # Strip [IMG:uuid] markers from content stored in ChromaDB / sent to LLM
        clean_content = _IMG_MARKER_RE.sub("[Figura]", chunk.content)
        chroma_items.append({
            "chunk_index": i,
            "vector": vectors[i],
            "payload": {
                "content": clean_content,
                "filename": filename,
                "page_number": chunk.page_number,
                "chunk_type": "text",
                "image_ids": ",".join(found_ids),
                "image_id": "",
            },
        })

    try:
        await vector_store.upsert_chunks_batch(doc_id, chroma_items)
    except Exception as exc:
        logger.error("doc_id=%s: ChromaDB upsert falló: %s", doc_id, exc)
        await _update_doc_status(doc_id, "error", f"ChromaDB error: {exc}")
        return

    logger.info("doc_id=%s: guardando %d chunks en PostgreSQL...", doc_id, len(chunks))
    async with AsyncSessionLocal() as session:
        for i, chunk in enumerate(chunks):
            found_ids = _IMG_MARKER_RE.findall(chunk.content)
            session.add(ChunkModel(
                document_id=doc_uuid,
                content=chunk.content,
                chunk_index=i,
                page_number=chunk.page_number,
                chunk_type="text",
                metadata_json=json.dumps({
                    "filename": filename,
                    "image_ids": ",".join(found_ids),
                }),
            ))
        await session.commit()

    elapsed = time.monotonic() - t_start
    _clear_cancelled(doc_id)
    await _update_doc_status(
        doc_id, "ready", None,
        chunk_count=len(chunks),
        image_count=len(db_image_records),
    )
    logger.info(
        "doc_id=%s: ✓ Ingesta completa — %d chunks, %d imágenes en %.1fs",
        doc_id, len(chunks), len(db_image_records), elapsed,
    )
