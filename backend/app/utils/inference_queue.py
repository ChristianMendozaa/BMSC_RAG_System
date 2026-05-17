"""
Cola FIFO para serializar toda inferencia LLM (chat + captioning de ingesta).
Solo una inferencia corre a la vez; el resto espera en orden de llegada.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class InferenceQueue:
    def __init__(self) -> None:
        self._sem = asyncio.Semaphore(1)
        self._waiting: int = 0

    @asynccontextmanager
    async def acquire(self):
        self._waiting += 1
        logger.info("[cola-llm] Solicitud en cola — en espera: %d", self._waiting)
        async with self._sem:
            self._waiting -= 1
            logger.info("[cola-llm] Inferencia iniciada — en espera: %d", self._waiting)
            try:
                yield
            finally:
                logger.debug("[cola-llm] Inferencia finalizada")

    @property
    def waiting(self) -> int:
        return self._waiting


inference_queue = InferenceQueue()
