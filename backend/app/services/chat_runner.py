"""
Generation registry: decouples LLM generation from the HTTP request lifecycle.

A generation is started with `start()`, which creates a top-level asyncio task that
persists independently of any connected client.  Clients subscribe to a Queue to receive
SSE-ready JSON payloads; unsubscribing (or disconnecting) has no effect on the task.
"""

import asyncio
import dataclasses
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import update, select

from app.config import settings
from app.db.models.chat_message import ChatMessage
from app.db.models.chat_session import ChatSession
from app.db.session import PGAsyncSessionLocal as AsyncSessionLocal
from app.cache import response_cache
from app.services import rag

logger = logging.getLogger(__name__)


def _perf_log(msg: str, *args) -> None:
    if settings.chat_perf_logging:
        logger.info("[chat-perf] " + msg, *args)


# ── DB helpers (previously in chat.py) ────────────────────────────────────────

async def _get_history(session_id: str) -> list[dict]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == uuid.UUID(session_id))
            .order_by(ChatMessage.created_at.asc())
        )
        rows = result.scalars().all()
        return [{"role": r.role, "content": r.content} for r in rows]


async def _save_turn(
    session_id: str, role: str, content: str, sources_json: str | None = None
) -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        db.add(ChatMessage(
            session_id=uuid.UUID(session_id),
            role=role,
            content=content,
            sources_json=sources_json,
        ))
        await db.execute(
            update(ChatSession)
            .where(ChatSession.id == uuid.UUID(session_id))
            .values(updated_at=now)
        )
        await db.commit()


# ── Generation registry ────────────────────────────────────────────────────────

@dataclasses.dataclass
class ActiveGeneration:
    session_id: str
    message: str
    allowed_doc_ids: list[str]
    cancel_flag: threading.Event
    subscribers: set
    done: asyncio.Event
    text: str = ""
    sources: list[dict] = dataclasses.field(default_factory=list)
    status: str = "running"   # running | done | stopped | error
    error: str | None = None
    task: "asyncio.Task | None" = None


_active: dict[str, ActiveGeneration] = {}


def get(session_id: str) -> ActiveGeneration | None:
    return _active.get(session_id)


def is_running(session_id: str) -> bool:
    gen = _active.get(session_id)
    return gen is not None and gen.status == "running"


def request_stop(session_id: str) -> bool:
    gen = _active.get(session_id)
    if gen and gen.status == "running":
        gen.cancel_flag.set()
        return True
    return False


async def subscribe(gen: ActiveGeneration) -> asyncio.Queue:
    """Return a queue that receives SSE-ready JSON strings for this generation."""
    q: asyncio.Queue[str | None] = asyncio.Queue()

    if gen.status == "running":
        gen.subscribers.add(q)
        # Replay accumulated text so the subscriber starts in sync
        if gen.text:
            await q.put(json.dumps({"type": "token", "content": gen.text}))
    else:
        # Already finished — seed the queue with the terminal state immediately
        if gen.text:
            await q.put(json.dumps({"type": "token", "content": gen.text}))
        _put_terminal(gen, q)

    return q


def _put_terminal(gen: ActiveGeneration, q: asyncio.Queue) -> None:
    """Synchronously put the terminal event into a queue (called only from sync ctx)."""
    if gen.status == "done":
        q.put_nowait(json.dumps({
            "type": "done",
            "session_id": gen.session_id,
            "sources": gen.sources,
            "from_cache": False,
        }))
    elif gen.status == "stopped":
        q.put_nowait(json.dumps({
            "type": "stopped",
            "session_id": gen.session_id,
            "sources": gen.sources,
        }))
    elif gen.status == "error":
        q.put_nowait(json.dumps({
            "type": "error",
            "message": gen.error or "Error desconocido",
        }))


def unsubscribe(gen: ActiveGeneration, q: asyncio.Queue) -> None:
    gen.subscribers.discard(q)


async def _broadcast(gen: ActiveGeneration, payload: str) -> None:
    for q in list(gen.subscribers):
        await q.put(payload)


def _cleanup(session_id: str) -> None:
    _active.pop(session_id, None)


def start(
    session_id: str,
    message: str,
    allowed_doc_ids: list[str],
) -> ActiveGeneration:
    gen = ActiveGeneration(
        session_id=session_id,
        message=message,
        allowed_doc_ids=allowed_doc_ids,
        cancel_flag=threading.Event(),
        subscribers=set(),
        done=asyncio.Event(),
    )
    _active[session_id] = gen
    gen.task = asyncio.create_task(_run(gen))
    return gen


async def _run(gen: ActiveGeneration) -> None:
    session_id = gen.session_id
    try:
        t_total = time.perf_counter()

        t0 = time.perf_counter()
        history = await _get_history(session_id)
        _perf_log("history(db): %.3fs", time.perf_counter() - t0)

        t0 = time.perf_counter()
        await _save_turn(session_id, "user", gen.message)
        _perf_log("save-user(db): %.3fs", time.perf_counter() - t0)

        is_first_turn = not history

        t0 = time.perf_counter()
        cached = (
            await asyncio.to_thread(response_cache.get, gen.message, gen.allowed_doc_ids)
            if is_first_turn else None
        )
        _perf_log(
            "cache lookup: %.3fs (%s)",
            time.perf_counter() - t0,
            "HIT" if cached is not None else ("MISS" if is_first_turn else "SKIP(follow-up)"),
        )

        if cached is not None:
            cached_text, cached_sources = cached
            await _save_turn(session_id, "assistant", cached_text, json.dumps(cached_sources))
            gen.text = cached_text
            gen.sources = cached_sources
            gen.status = "done"
            _perf_log("TOTAL chat (cache hit): %.3fs", time.perf_counter() - t_total)
            payload = json.dumps({
                "type": "done",
                "session_id": session_id,
                "sources": cached_sources,
                "from_cache": True,
            })
            await _broadcast(gen, payload)
            return

        text_contexts, image_sources = await rag.build_context(
            gen.message,
            gen.allowed_doc_ids,
            history=history,
        )

        final_sources = None
        async for token, sources in rag.stream_chat(
            message=gen.message,
            text_contexts=text_contexts,
            image_sources=image_sources,
            history=history,
            cancel_flag=gen.cancel_flag,
        ):
            if sources is not None:
                final_sources = sources
            elif token:
                gen.text += token
                await _broadcast(gen, json.dumps({"type": "token", "content": token}))

        sources_data = (
            [s.model_dump() for s in final_sources] if final_sources else []
        )
        gen.sources = sources_data

        t0 = time.perf_counter()
        await _save_turn(session_id, "assistant", gen.text, json.dumps(sources_data))
        _perf_log("save-assistant(db): %.3fs", time.perf_counter() - t0)

        if gen.cancel_flag.is_set():
            gen.status = "stopped"
            _perf_log("TOTAL chat (stopped): %.3fs", time.perf_counter() - t_total)
            payload = json.dumps({
                "type": "stopped",
                "session_id": session_id,
                "sources": sources_data,
            })
        else:
            gen.status = "done"
            if is_first_turn and gen.text and sources_data:
                await asyncio.to_thread(
                    response_cache.set,
                    gen.message, gen.allowed_doc_ids, gen.text, sources_data,
                )
            _perf_log("TOTAL chat: %.3fs", time.perf_counter() - t_total)
            payload = json.dumps({
                "type": "done",
                "session_id": session_id,
                "sources": sources_data,
                "from_cache": False,
            })

        await _broadcast(gen, payload)

    except Exception as exc:
        logger.error("Chat runner error [%s]: %s", session_id, exc)
        gen.status = "error"
        gen.error = str(exc)
        await _broadcast(gen, json.dumps({"type": "error", "message": str(exc)}))

    finally:
        gen.done.set()
        loop = asyncio.get_running_loop()
        loop.call_later(10.0, _cleanup, session_id)
