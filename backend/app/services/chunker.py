import logging
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=150,
    length_function=len,
)


@dataclass
class Chunk:
    content: str
    chunk_index: int
    page_number: int | None
    chunk_type: str = "text"


def chunk_text_blocks(
    blocks: list[dict],
) -> list[Chunk]:
    """
    blocks: list of {"text": str, "page_number": int | None, "block_type": str}
    Returns flat list of Chunk objects.
    """
    chunks: list[Chunk] = []
    chunk_index = 0

    for block in blocks:
        text = block.get("text", "").strip()
        page = block.get("page_number")
        block_type = block.get("block_type", "text")

        if not text:
            continue

        try:
            pieces = _splitter.split_text(text)
        except Exception as exc:
            logger.warning("Chunker failed on block (page=%s): %s", page, exc)
            continue

        for piece in pieces:
            if piece.strip():
                chunks.append(
                    Chunk(
                        content=piece.strip(),
                        chunk_index=chunk_index,
                        page_number=page,
                        chunk_type=block_type,
                    )
                )
                chunk_index += 1

    return chunks
