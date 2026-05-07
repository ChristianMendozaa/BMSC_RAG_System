"""RapidOCR wrapper — extracts literal text from image bytes (es + en).

Pure Python: models are ONNX files downloaded automatically on first use (~10 MB).
No system-level installation required.
"""

import asyncio
import io
import logging
from typing import Any

import numpy as np
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

_engine: Any = None


def _get_engine() -> Any:
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
        logger.info("RapidOCR engine initialized")
    return _engine


def _extract_text_sync(image_bytes: bytes) -> str:
    if settings.skip_ocr:
        return ""
    try:
        engine = _get_engine()
    except Exception as exc:
        logger.warning("RapidOCR init failed: %s", exc)
        return ""

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = np.array(image)

    try:
        result, _ = engine(arr)
    except Exception as exc:
        logger.warning("RapidOCR inference failed: %s", exc)
        return ""

    if not result:
        return ""

    pieces: list[str] = []
    for item in result:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        text = item[1]
        confidence = item[2] if len(item) > 2 else 1.0
        if not isinstance(text, str) or not text.strip():
            continue
        if isinstance(confidence, (int, float)) and confidence < 0.30:
            continue
        pieces.append(text.strip())
    return " | ".join(pieces)


async def extract_text(image_bytes: bytes) -> str:
    try:
        return await asyncio.to_thread(_extract_text_sync, image_bytes)
    except Exception as exc:
        logger.warning("OCR failed: %s", exc)
        return ""
