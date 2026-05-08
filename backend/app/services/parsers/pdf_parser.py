import logging
from dataclasses import dataclass, field

import fitz  # PyMuPDF
import pdfplumber

logger = logging.getLogger(__name__)

# A page is considered a vector-diagram page when it has at least this many
# drawing paths AND its text is short (labels only, not a prose page).
_MIN_DRAWINGS = 8
_MAX_TEXT_FOR_DIAGRAM = 1500  # chars; class diagrams have many label texts
_RENDER_DPI = 150


@dataclass
class TextBlock:
    text: str
    page_number: int
    block_type: str = "text"


@dataclass
class ImageBlock:
    data: bytes
    page_number: int
    image_index: int


@dataclass
class ParseResult:
    text_blocks: list[TextBlock] = field(default_factory=list)
    image_blocks: list[ImageBlock] = field(default_factory=list)


def parse(file_bytes: bytes) -> ParseResult:
    result = ParseResult()
    global_image_idx = 0

    try:
        fitz_doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        logger.error("Failed to open PDF with PyMuPDF: %s", exc)
        raise

    try:
        with pdfplumber.open(fitz.open(stream=file_bytes, filetype="pdf")) as plumber_doc:
            pass
    except Exception:
        plumber_doc = None

    for page_num in range(len(fitz_doc)):
        try:
            page = fitz_doc[page_num]
            text = page.get_text("text").strip()
            if text:
                result.text_blocks.append(TextBlock(text=text, page_number=page_num + 1))

            image_list = page.get_images(full=True)
            for img_info in image_list:
                try:
                    xref = img_info[0]
                    pixmap = fitz.Pixmap(fitz_doc, xref)
                    if pixmap.colorspace and pixmap.colorspace.n > 3:
                        pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
                    img_bytes = pixmap.tobytes("png")
                    result.image_blocks.append(
                        ImageBlock(
                            data=img_bytes,
                            page_number=page_num + 1,
                            image_index=global_image_idx,
                        )
                    )
                    global_image_idx += 1
                except Exception as exc:
                    logger.warning(
                        "Skipping image on page %d (xref=%d): %s", page_num + 1, img_info[0], exc
                    )

            # Vector-diagram detection: pages drawn with PDF path commands
            # (UML diagrams, C4 models, flowcharts) have no embedded images but
            # contain many drawing paths and little prose text.
            # Render such pages to a pixmap so BLIP can caption the full visual.
            try:
                drawings = page.get_drawings()
                is_vector_diagram = (
                    len(drawings) >= _MIN_DRAWINGS
                    and not image_list          # no raster image already captured
                    and len(text) <= _MAX_TEXT_FOR_DIAGRAM
                )
                if is_vector_diagram:
                    mat = fitz.Matrix(_RENDER_DPI / 72, _RENDER_DPI / 72)
                    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
                    result.image_blocks.append(
                        ImageBlock(
                            data=pix.tobytes("png"),
                            page_number=page_num + 1,
                            image_index=global_image_idx,
                        )
                    )
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
