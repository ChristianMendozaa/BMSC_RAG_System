import logging
from dataclasses import dataclass, field

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
    return ParseResult(
        text_blocks=[],
        image_blocks=[ImageBlock(data=file_bytes, page_number=None, image_index=0)],
    )
