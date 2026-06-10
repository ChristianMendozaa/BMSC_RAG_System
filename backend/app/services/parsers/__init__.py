from app.services.parsers import docx_parser, image_parser, pdf_parser, pptx_parser, xlsx_parser
from app.services.parsers.image_parser import ParseResult, TextBlock

ACCEPTED_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md",
    ".jpg", ".jpeg", ".png", ".webp",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
TEXT_EXTENSIONS = {".txt", ".md"}


def parse_file(ext: str, file_bytes: bytes) -> ParseResult:
    """Dispatch al parser según extensión. Lanza ValueError si no está soportada."""
    if ext in IMAGE_EXTENSIONS:
        return image_parser.parse(file_bytes)
    if ext == ".pdf":
        return pdf_parser.parse(file_bytes)
    if ext == ".docx":
        return docx_parser.parse(file_bytes)
    if ext == ".pptx":
        return pptx_parser.parse(file_bytes)
    if ext == ".xlsx":
        return xlsx_parser.parse(file_bytes)
    if ext in TEXT_EXTENSIONS:
        # utf-8-sig: igual que utf-8 pero descarta el BOM que mete Notepad/Windows
        text = file_bytes.decode("utf-8-sig", errors="replace")
        return ParseResult(
            text_blocks=[TextBlock(text=text, page_number=None)],
            image_blocks=[],
        )
    raise ValueError(f"Unsupported file extension: {ext}")
