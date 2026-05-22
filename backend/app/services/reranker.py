import asyncio
import logging

import torch

from app.utils.model_manager import get_reranker

logger = logging.getLogger(__name__)


def _compute_scores(query: str, candidates: list[dict]) -> list[float]:
    """Runs BGE cross-encoder inference synchronously (called via executor)."""
    tokenizer, model = get_reranker()
    pairs_a = [query] * len(candidates)
    pairs_b = [c.get("content", "") for c in candidates]
    with torch.no_grad():
        inputs = tokenizer(
            pairs_a,
            pairs_b,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        logits = model(**inputs, return_dict=True).logits.view(-1).float()
        scores = torch.sigmoid(logits).tolist()
    return scores


async def rerank(query: str, candidates: list[dict], top_k: int) -> list[dict]:
    """
    Reordena candidates por relevancia semántica respecto a query usando BGE-reranker-v2-m3.
    Corre en executor — NO usa inference_queue (el cross-encoder es ligero y CPU-orthogonal).

    Cada candidate debe tener al menos la clave "content".
    Devuelve los top_k items con un campo "rerank_score" añadido, ordenados por score desc.
    """
    if not candidates:
        return []

    if len(candidates) <= top_k:
        for c in candidates:
            c.setdefault("rerank_score", 1.0)
        return candidates

    try:
        scores = await asyncio.to_thread(_compute_scores, query, candidates)
    except Exception as exc:
        logger.error("Error en reranker, devolviendo orden original: %s", exc)
        for c in candidates:
            c.setdefault("rerank_score", 0.0)
        return candidates[:top_k]

    for candidate, score in zip(candidates, scores):
        candidate["rerank_score"] = float(score)

    ranked = sorted(candidates, key=lambda x: x.get("rerank_score", 0.0), reverse=True)
    return ranked[:top_k]
