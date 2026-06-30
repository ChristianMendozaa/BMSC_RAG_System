"""
Cola priorizada para serializar inferencia LLM (chat + captioning de ingesta).
Solo una inferencia corre a la vez; chat debe adelantar nuevos trabajos de ingesta.
"""

import asyncio
import heapq
import itertools
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class InferenceQueue:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active = False
        self._queue: list[tuple[int, int, asyncio.Future[None]]] = []
        self._seq = itertools.count()
        self._waiting: int = 0

    @asynccontextmanager
    async def acquire(self, priority: int = 5, label: str = "llm"):
        fut = await self._enqueue(priority, label)
        try:
            await fut
            logger.info(
                "[cola-llm] Inferencia iniciada (%s) — en espera: %d",
                label,
                self._waiting,
            )
            yield
        finally:
            if not fut.cancelled():
                await self._release(label)

    async def _enqueue(self, priority: int, label: str) -> asyncio.Future[None]:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[None] = loop.create_future()
        async with self._lock:
            self._waiting += 1
            heapq.heappush(self._queue, (priority, next(self._seq), fut))
            logger.info(
                "[cola-llm] Solicitud en cola (%s, prioridad=%d) — en espera: %d",
                label,
                priority,
                self._waiting,
            )
            self._wake_next_locked()
        return fut

    async def _release(self, label: str) -> None:
        async with self._lock:
            if self._active:
                self._active = False
                logger.debug("[cola-llm] Inferencia finalizada (%s)", label)
            self._wake_next_locked()

    def _wake_next_locked(self) -> None:
        if self._active:
            return
        while self._queue:
            _priority, _seq, fut = heapq.heappop(self._queue)
            if fut.cancelled():
                self._waiting = max(0, self._waiting - 1)
                continue
            self._active = True
            self._waiting = max(0, self._waiting - 1)
            fut.set_result(None)
            return

    @property
    def waiting(self) -> int:
        return self._waiting


inference_queue = InferenceQueue()
