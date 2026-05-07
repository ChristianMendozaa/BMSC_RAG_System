import logging
from dataclasses import dataclass, field
from io import BytesIO

from docx import Document
from docx.oxml.ns import qn

logger = logging.getLogger(__name__)


@dataclass
class TextBlock:
    text: str
    page_number: int | None
    block_type: str = "text"


@dataclass
class ImageBlock:
    data: bytes
    page_number: int | None
    image_index: int


@dataclass
class ParseResult:
    text_blocks: list[TextBlock] = field(default_factory=list)
    image_blocks: list[ImageBlock] = field(default_factory=list)


def parse(file_bytes: bytes) -> ParseResult:
    result = ParseResult()
    image_idx = 0

    try:
        doc = Document(BytesIO(file_bytes))
    except Exception as exc:
        logger.error("Failed to open DOCX: %s", exc)
        raise

    text_parts: list[str] = []
    for para in doc.paragraphs:
        try:
            if not para.text.strip():
                continue
            style_name = para.style.name if para.style else ""
            if style_name.startswith("Heading"):
                if text_parts:
                    result.text_blocks.append(
                        TextBlock(text="\n".join(text_parts), page_number=None)
                    )
                    text_parts = []
                result.text_blocks.append(
                    TextBlock(text=f"## {para.text.strip()}", page_number=None)
                )
            else:
                text_parts.append(para.text.strip())
        except Exception as exc:
            logger.warning("Skipping DOCX paragraph: %s", exc)

    if text_parts:
        result.text_blocks.append(TextBlock(text="\n".join(text_parts), page_number=None))

    try:
        for rel in doc.part.rels.values():
            if "image" in rel.reltype:
                try:
                    img_data = rel.target_part.blob
                    result.image_blocks.append(
                        ImageBlock(data=img_data, page_number=None, image_index=image_idx)
                    )
                    image_idx += 1
                except Exception as exc:
                    logger.warning("Skipping DOCX inline image: %s", exc)
    except Exception as exc:
        logger.warning("Failed to extract DOCX images: %s", exc)

    return result
