import hashlib
import logging
from dataclasses import dataclass, field

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

_MIN_DRAWINGS = 8
_MAX_TEXT_FOR_DIAGRAM = 1500
_RENDER_DPI = 150

_HEADER_ZONE = 0.10   # top 10% of page height → header zone (logo, banner)
_FOOTER_ZONE = 0.05   # bottom 5% of page height → footer zone
_MIN_WIDTH = 80       # minimum natural image width in pixels
_MIN_HEIGHT = 80      # minimum natural image height in pixels
_MERGE_MARGIN = 20    # point tolerance for grouping overlapping/nearby rects


@dataclass
class TextBlock:
    text: str
    page_number: int
    block_type: str = "text"
    y_position: float = 0.0


@dataclass
class ImageBlock:
    data: bytes
    page_number: int
    image_index: int
    y_position: float = 0.0


@dataclass
class ParseResult:
    text_blocks: list[TextBlock] = field(default_factory=list)
    image_blocks: list[ImageBlock] = field(default_factory=list)


def _group_by_proximity(rects: list, margin: float) -> list[list[int]]:
    """Return connected components of rect indices whose expanded boxes intersect."""
    n = len(rects)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        expanded = fitz.Rect(
            rects[i].x0 - margin, rects[i].y0 - margin,
            rects[i].x1 + margin, rects[i].y1 + margin,
        )
        for j in range(i + 1, n):
            if expanded.intersects(rects[j]):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def parse(file_bytes: bytes) -> ParseResult:
    result = ParseResult()
    global_image_idx = 0
    seen_hashes: set[str] = set()  # document-level deduplication

    try:
        fitz_doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        logger.error("Failed to open PDF with PyMuPDF: %s", exc)
        raise

    for page_num in range(len(fitz_doc)):
        try:
            page = fitz_doc[page_num]
            page_height = page.rect.height

            # Extract text blocks with per-block y positions for reading-order interleaving
            raw_blocks = page.get_text("blocks")
            # Each block: (x0, y0, x1, y1, text, block_no, block_type)
            # block_type 0=text, 1=image placeholder (no useful content)
            for blk in raw_blocks:
                if blk[6] != 0:
                    continue
                blk_text = blk[4].strip()
                if not blk_text:
                    continue
                result.text_blocks.append(TextBlock(
                    text=blk_text,
                    page_number=page_num + 1,
                    block_type="text",
                    y_position=blk[1],
                ))

            image_list = page.get_images(full=True)

            # Step A: collect candidates that pass header/footer zone and minimum size filters
            # candidate: (xref, page_rect, pixmap)
            candidates: list[tuple[int, fitz.Rect, fitz.Pixmap]] = []
            for img_info in image_list:
                xref = img_info[0]
                try:
                    rects = page.get_image_rects(xref)
                    if not rects:
                        continue
                    rect = rects[0]

                    # Filter 1: skip images entirely inside header or footer zone
                    if rect.y1 < page_height * _HEADER_ZONE:
                        continue
                    if rect.y0 > page_height * (1 - _FOOTER_ZONE):
                        continue

                    # Filter 2: skip images below minimum pixel dimensions
                    pixmap = fitz.Pixmap(fitz_doc, xref)
                    if pixmap.colorspace and pixmap.colorspace.n > 3:
                        pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
                    if pixmap.width < _MIN_WIDTH or pixmap.height < _MIN_HEIGHT:
                        continue

                    candidates.append((xref, rect, pixmap))
                except Exception as exc:
                    logger.warning(
                        "Skipping image on page %d (xref=%d): %s", page_num + 1, xref, exc
                    )

            # Step B: group candidates by bounding-box proximity (union-find)
            if candidates:
                rects_only = [r for _, r, _ in candidates]
                groups = _group_by_proximity(rects_only, _MERGE_MARGIN)

                mat = fitz.Matrix(_RENDER_DPI / 72, _RENDER_DPI / 72)

                for group_indices in groups:
                    try:
                        if len(group_indices) == 1:
                            # Single image: extract embedded bytes directly
                            idx = group_indices[0]
                            _, rect, pixmap = candidates[idx]
                            img_bytes = pixmap.tobytes("png")
                            y_pos = rect.y0
                        else:
                            # Multiple nearby images (e.g. screenshot + annotation circle):
                            # render their union bounding box from the page as a composite crop
                            union_rect = candidates[group_indices[0]][1]
                            for idx in group_indices[1:]:
                                union_rect = union_rect | candidates[idx][1]
                            clip_pix = page.get_pixmap(
                                clip=union_rect, matrix=mat, colorspace=fitz.csRGB
                            )
                            img_bytes = clip_pix.tobytes("png")
                            y_pos = union_rect.y0

                        # Filter 4: document-level deduplication by content hash
                        h = hashlib.md5(img_bytes).hexdigest()
                        if h in seen_hashes:
                            continue
                        seen_hashes.add(h)

                        result.image_blocks.append(ImageBlock(
                            data=img_bytes,
                            page_number=page_num + 1,
                            image_index=global_image_idx,
                            y_position=y_pos,
                        ))
                        global_image_idx += 1
                    except Exception as exc:
                        logger.warning(
                            "Skipping image group on page %d: %s", page_num + 1, exc
                        )

            # Vector-diagram detection: pages with many drawing paths and little text
            try:
                drawings = page.get_drawings()
                page_text_len = sum(
                    len(blk[4]) for blk in raw_blocks if blk[6] == 0
                )
                is_vector_diagram = (
                    len(drawings) >= _MIN_DRAWINGS
                    and not image_list
                    and page_text_len <= _MAX_TEXT_FOR_DIAGRAM
                )
                if is_vector_diagram:
                    mat = fitz.Matrix(_RENDER_DPI / 72, _RENDER_DPI / 72)
                    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
                    img_bytes = pix.tobytes("png")
                    h = hashlib.md5(img_bytes).hexdigest()
                    if h not in seen_hashes:
                        seen_hashes.add(h)
                        result.image_blocks.append(ImageBlock(
                            data=img_bytes,
                            page_number=page_num + 1,
                            image_index=global_image_idx,
                            y_position=0.0,
                        ))
                        global_image_idx += 1
                        logger.debug(
                            "Rendered vector-diagram page %d (%d paths)",
                            page_num + 1, len(drawings),
                        )
            except Exception as exc:
                logger.warning("Vector-diagram render failed on page %d: %s", page_num + 1, exc)
        except Exception as exc:
            logger.warning("Skipping PDF page %d: %s", page_num + 1, exc)

    fitz_doc.close()
    return result
