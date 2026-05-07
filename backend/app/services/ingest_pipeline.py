import asyncio
import json
import logging
import mimetypes
import re

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Chunk as ChunkModel
from app.models import Document, DocumentFigure, DocumentImage

# Generic figure-caption regex: matches "Figura 5:", "Diagrama 3 ", "Tabla 7.", etc.
_FIG_CAPTION = re.compile(
    r'\b(Figura|Fig\.?|Diagrama|Tabla|Imagen|Esquema)\s+(\d+)[.:\s]',
    re.IGNORECASE,
)
from app.services import embedder, file_storage, ocr as ocr_service, vector_store
from app.services import chunker as chunker_service
from app.services.parsers import pdf_parser, docx_parser, pptx_parser, xlsx_parser, image_parser

logger = logging.getLogger(__name__)

# ── Cancellation registry ──────────────────────────────────────────────────
# doc_ids added here will cause their in-flight pipeline to abort gracefully.
_cancelled_docs: set[str] = set()


def cancel_pipeline(doc_id: str) -> None:
    """Signal a running pipeline to stop at its next checkpoint."""
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

# Limit concurrent image I/O to avoid saturating memory on large documents
_IMAGE_IO_SEM = asyncio.Semaphore(4)


async def _update_doc_status(
    doc_id: str, status: str, error_message: str | None = None, **kwargs
) -> None:
    async with AsyncSessionLocal() as session:
        doc = await session.get(Document, doc_id)
        if doc:
            doc.status = status
            if error_message is not None:
                doc.error_message = error_message
            for k, v in kwargs.items():
                setattr(doc, k, v)
            await session.commit()


async def _upload_and_store_image(
    doc_id: str,
    img_block,
) -> tuple | None:
    """Upload one image to storage and return (object_name, img_block) or None on failure."""
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
    logger.info("Starting ingestion for doc_id=%s filename=%s", doc_id, filename)

    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    # ── Step 1: Upload original file to local storage ──────────────────────
    try:
        minio_path = f"{doc_id}/{filename}"
        await file_storage.upload_bytes(
            settings.minio_bucket_documents, minio_path, file_bytes, mime_type
        )
        async with AsyncSessionLocal() as session:
            doc = await session.get(Document, doc_id)
            if doc:
                doc.minio_path = minio_path
                await session.commit()
    except Exception as exc:
        logger.error("doc_id=%s: storage upload failed: %s", doc_id, exc)
        await _update_doc_status(doc_id, "error", str(exc))
        return

    await _update_doc_status(doc_id, "processing")

    # ── Step 2: Parse file ─────────────────────────────────────────────────
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

    # ── Step 2b: Extract figure-to-page index ─────────────────────────────
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
                    document_id=doc_id,
                    figure_number=fig_num,
                    page_number=block.page_number,
                    caption=m.group(0)[:200],
                ))
    if figure_records:
        async with AsyncSessionLocal() as session:
            for rec in figure_records:
                session.add(rec)
            await session.commit()
        logger.info("doc_id=%s: indexed %d figure references", doc_id, len(figure_records))

    # ── Step 3: Build raw text blocks ─────────────────────────────────────
    raw_blocks = [
        {
            "text": b.text,
            "page_number": b.page_number,
            "block_type": getattr(b, "block_type", "text"),
        }
        for b in parse_result.text_blocks
    ]

    # ── Step 4: Chunk + batch-embed + batch-upsert text (PHASE 1) ─────────
    chunks = chunker_service.chunk_text_blocks(raw_blocks)

    chunk_count = 0
    if chunks:
        texts = [c.content for c in chunks]
        try:
            vectors = await embedder.embed_texts_batch(texts)
        except Exception as exc:
            logger.error("doc_id=%s: batch embedding failed: %s", doc_id, exc)
            await _update_doc_status(doc_id, "error", f"Embedding error: {exc}")
            return

        # Batch upsert to Qdrant
        qdrant_items = [
            {
                "chunk_index": i,
                "vector": vectors[i],
                "payload": {
                    "content": chunks[i].content,
                    "filename": filename,
                    "page_number": chunks[i].page_number,
                    "chunk_type": chunks[i].chunk_type,
                    "image_id": None,
                },
            }
            for i in range(len(chunks))
            if i < len(vectors)
        ]
        try:
            await vector_store.upsert_chunks_batch(doc_id, qdrant_items)
        except Exception as exc:
            logger.error("doc_id=%s: Qdrant batch upsert failed: %s", doc_id, exc)
            await _update_doc_status(doc_id, "error", f"Vector store error: {exc}")
            return

        # Bulk insert chunk records to SQLite
        async with AsyncSessionLocal() as session:
            for i, chunk in enumerate(chunks):
                session.add(ChunkModel(
                    document_id=doc_id,
                    content=chunk.content,
                    chunk_index=i,
                    page_number=chunk.page_number,
                    chunk_type=chunk.chunk_type,
                    metadata_json=json.dumps({"filename": filename}),
                ))
            await session.commit()

        chunk_count = len(chunks)
        logger.info("doc_id=%s: text phase done — %d chunks embedded", doc_id, chunk_count)

    # ── Mark as indexing_images — text is searchable, images still pending ─
    await _update_doc_status(doc_id, "indexing_images", None, chunk_count=chunk_count, image_count=0)
    logger.info("doc_id=%s: status → indexing_images; starting image phase", doc_id)

    # ── Step 5: Image phase — upload, caption, OCR (sequential VLM is safe) ─
    if _is_cancelled(doc_id):
        logger.info("doc_id=%s: pipeline cancelled before image phase", doc_id)
        _clear_cancelled(doc_id)
        return

    image_blocks = parse_result.image_blocks[:settings.max_images_per_doc]
    if not image_blocks:
        logger.info("doc_id=%s: no images to process", doc_id)
        return

    # Upload all images to storage in parallel
    upload_results = await asyncio.gather(
        *[_upload_and_store_image(doc_id, img) for img in image_blocks],
        return_exceptions=True,
    )

    # Build page-text map for context augmentation
    page_text_map: dict[int | None, str] = {}
    for block in raw_blocks:
        pn = block["page_number"]
        page_text_map[pn] = (page_text_map.get(pn, "") + " " + block["text"]).strip()

    def _surrounding_page_text(page_number: int | None) -> str:
        if page_number is None:
            return page_text_map.get(None, "")
        parts: list[str] = []
        for p in (page_number - 1, page_number, page_number + 1):
            chunk = page_text_map.get(p, "").strip()
            if chunk:
                parts.append(chunk)
        return "\n".join(parts)

    # VLM caption + OCR — VLM is not thread-safe, run sequentially
    db_image_records: list[tuple[DocumentImage, bytes]] = []

    for result, img_block in zip(upload_results, image_blocks):
        if _is_cancelled(doc_id):
            logger.info("doc_id=%s: pipeline cancelled during image processing", doc_id)
            _clear_cancelled(doc_id)
            return

        if isinstance(result, Exception) or result is None:
            continue
        img_object_name, _ = result

        description = ""
        ocr_text = ""
        try:
            description = await embedder.describe_image(img_block.data)
        except Exception as exc:
            logger.warning(
                "doc_id=%s: VLM caption failed for image %d: %s",
                doc_id, img_block.image_index, exc,
            )
        try:
            ocr_text = await ocr_service.extract_text(img_block.data)
        except Exception as exc:
            logger.warning(
                "doc_id=%s: OCR failed for image %d: %s",
                doc_id, img_block.image_index, exc,
            )

        db_image_records.append((
            DocumentImage(
                document_id=doc_id,
                minio_path=img_object_name,
                page_number=img_block.page_number,
                image_index=img_block.image_index,
                description=description,
                ocr_text=ocr_text,
            ),
            img_block.data,
        ))

    if not db_image_records:
        logger.info("doc_id=%s: image phase produced no records", doc_id)
        return

    # Save image records to DB and get their generated IDs
    async with AsyncSessionLocal() as session:
        for rec, _ in db_image_records:
            session.add(rec)
        await session.commit()
        for rec, _ in db_image_records:
            await session.refresh(rec)

    # ── Step 6: Build image description chunks + batch embed + upsert ─────
    image_desc_blocks = []
    for rec, _ in db_image_records:
        page_text = _surrounding_page_text(rec.page_number)
        parts = []
        if rec.description:
            parts.append(rec.description.strip())
        if rec.ocr_text:
            parts.append(f"Texto en la imagen: {rec.ocr_text.strip()}")
        if page_text:
            parts.append(f"Contexto de la página: {page_text}")
        if not parts:
            continue
        augmented = "\n".join(parts)
        image_desc_blocks.append({
            "text": augmented,
            "caption": rec.description or "",
            "ocr_text": rec.ocr_text or "",
            "page_context": page_text,
            "page_number": rec.page_number,
            "image_id": rec.id,
            "image_index": rec.image_index,
        })

    img_chunk_count = 0
    if image_desc_blocks:
        img_texts = [b["text"] for b in image_desc_blocks]
        try:
            img_vectors = await embedder.embed_texts_batch(img_texts)
        except Exception as exc:
            logger.warning("doc_id=%s: image description embedding failed: %s", doc_id, exc)
            img_vectors = []

        start_idx = chunk_count
        qdrant_img_items = [
            {
                "chunk_index": start_idx + i,
                "vector": img_vectors[i],
                "payload": {
                    "content": image_desc_blocks[i]["text"],
                    "caption": image_desc_blocks[i]["caption"],
                    "ocr_text": image_desc_blocks[i]["ocr_text"],
                    "page_context_used": image_desc_blocks[i]["page_context"][:1000],
                    "filename": filename,
                    "page_number": image_desc_blocks[i]["page_number"],
                    "chunk_type": "image_description",
                    "image_id": image_desc_blocks[i]["image_id"],
                },
            }
            for i in range(len(image_desc_blocks))
            if i < len(img_vectors)
        ]
        try:
            await vector_store.upsert_chunks_batch(doc_id, qdrant_img_items)
        except Exception as exc:
            logger.warning("doc_id=%s: image description Qdrant upsert failed: %s", doc_id, exc)

        async with AsyncSessionLocal() as session:
            for i, desc_block in enumerate(image_desc_blocks):
                session.add(ChunkModel(
                    document_id=doc_id,
                    content=desc_block["text"],
                    chunk_index=start_idx + i,
                    page_number=desc_block["page_number"],
                    chunk_type="image_description",
                    metadata_json=json.dumps({
                        "filename": filename,
                        "image_id": desc_block["image_id"],
                    }),
                ))
            await session.commit()

        img_chunk_count = len(qdrant_img_items)

    # ── Step 7: Batch CLIP visual embeddings ──────────────────────────────
    for rec, img_bytes in db_image_records:
        try:
            visual_vector = await embedder.embed_image(img_bytes)
            await vector_store.upsert_image_visual(
                doc_id=doc_id,
                image_id=rec.id,
                vector=visual_vector,
                payload={
                    "filename": filename,
                    "page_number": rec.page_number,
                    "caption": rec.description or "",
                    "ocr_text": rec.ocr_text or "",
                },
            )
        except Exception as exc:
            logger.warning(
                "doc_id=%s: failed to embed visual vector for image_id=%s: %s",
                doc_id, rec.id, exc,
            )

    total_chunks = chunk_count + img_chunk_count
    _clear_cancelled(doc_id)
    await _update_doc_status(
        doc_id, "ready", None,
        chunk_count=total_chunks,
        image_count=len(db_image_records),
    )
    logger.info(
        "doc_id=%s: image phase done — %d images, %d total chunks",
        doc_id, len(db_image_records), total_chunks,
    )
