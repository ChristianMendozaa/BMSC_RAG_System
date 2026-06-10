import logging
from dataclasses import dataclass, field
from io import BytesIO

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

_EXIF_ORIENTATION_TAG = 0x0112


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


def _normalize_orientation(file_bytes: bytes) -> bytes:
    """Aplica la rotación EXIF (fotos de celular) re-encodando solo si hace falta."""
    try:
        img = Image.open(BytesIO(file_bytes))
        if img.getexif().get(_EXIF_ORIENTATION_TAG, 1) == 1:
            return file_bytes
        img = ImageOps.exif_transpose(img)
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:
        logger.warning("Could not normalize image orientation: %s", exc)
        return file_bytes


def parse(file_bytes: bytes) -> ParseResult:
    return ParseResult(
        text_blocks=[],
        image_blocks=[
            ImageBlock(data=_normalize_orientation(file_bytes), page_number=None, image_index=0)
        ],
    )
