import asyncio

from app.services import rag
from app.utils.inference_queue import InferenceQueue


def test_inference_queue_prioritizes_chat_over_waiting_vision():
    async def scenario():
        queue = InferenceQueue()
        events: list[str] = []

        async def hold():
            async with queue.acquire(priority=5, label="hold"):
                events.append("hold-start")
                await asyncio.sleep(0.05)
                events.append("hold-end")

        async def vision():
            await asyncio.sleep(0.01)
            async with queue.acquire(priority=10, label="vision"):
                events.append("vision-start")

        async def chat():
            await asyncio.sleep(0.02)
            async with queue.acquire(priority=0, label="chat"):
                events.append("chat-start")

        await asyncio.gather(hold(), vision(), chat())
        return events

    events = asyncio.run(scenario())

    assert events == ["hold-start", "hold-end", "chat-start", "vision-start"]


def test_build_messages_drops_history_before_context(monkeypatch):
    monkeypatch.setattr(rag.settings, "chat_prompt_token_budget", 512)
    monkeypatch.setattr(
        rag,
        "_count_prompt_tokens",
        lambda messages: len(messages[1]["content"]),
    )

    contexts = [
        {
            "content": "A" * 1200,
            "filename": "Manual.pdf",
            "page": 1,
            "doc_id": "doc-1",
            "score": 0.9,
        }
    ]
    history = [
        {"role": "user", "content": "pregunta anterior " * 80},
        {"role": "assistant", "content": "respuesta anterior " * 80},
    ]

    messages = rag._build_messages("Pregunta actual", contexts, [], history)

    assert "HISTORIAL:" not in messages[1]["content"]
    assert "CONTEXTO DE DOCUMENTOS:" in messages[1]["content"]


def test_build_context_reports_retrieval_and_rerank_status(monkeypatch):
    async def fake_embed_text(_text):
        return [0.1, 0.2]

    async def fake_search(*, query_vector, top_k, doc_ids):
        return [
            {
                "content": "Contenido relevante",
                "doc_id": "11111111-1111-1111-1111-111111111111",
                "filename": "Manual.pdf",
                "page_number": 1,
                "score": 0.8,
            }
        ]

    async def fake_fetch_images(_pairs):
        return []

    async def fake_rerank(_query, candidates, top_k):
        return candidates[:top_k]

    monkeypatch.setattr(rag.embedder, "embed_text", fake_embed_text)
    monkeypatch.setattr(rag.vector_store, "search", fake_search)
    monkeypatch.setattr(rag, "_fetch_image_descriptions", fake_fetch_images)
    monkeypatch.setattr(rag.reranker_svc, "rerank", fake_rerank)

    statuses: list[str] = []

    async def collect(stage: str, _message: str):
        statuses.append(stage)

    asyncio.run(rag.build_context("consulta", ["doc-1"], status_callback=collect))

    assert statuses == ["retrieving", "reranking"]
