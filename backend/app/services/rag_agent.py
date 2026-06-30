import asyncio
import json
import logging
import re
import time
from typing import Awaitable, Callable

from app.config import settings
from app.services import rag
from app.services import reranker as reranker_svc
from app.utils.inference_queue import inference_queue
from app.utils.model_manager import get_chat_llm

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str, str], Awaitable[None]]
TraceCallback = Callable[[str, str, str | None, str], Awaitable[None]]

_MAX_FOLLOWUP_QUERIES = 2
_MAX_EVIDENCE_ITEMS_FOR_ASSESSMENT = 8
_MAX_EVIDENCE_CHARS_FOR_ASSESSMENT = 700


_ASSESSMENT_SYSTEM_PROMPT = """Eres un verificador de evidencia para un sistema RAG bancario.
Tu tarea es decidir si los fragmentos recuperados son suficientes para responder la pregunta
sin inventar información.

Responde SOLO JSON válido con esta forma:
{
  "sufficient": true | false,
  "missing": "breve descripción de lo que falta",
  "followup_queries": ["consulta adicional 1", "consulta adicional 2"]
}

Reglas:
- Marca sufficient=true solo si la evidencia contiene datos concretos para responder.
- Si falta información específica, marca sufficient=false y propone búsquedas cortas en español.
- No propongas más de 2 consultas.
- No incluyas razonamiento paso a paso ni texto fuera del JSON."""


def _truncate(text: str, max_chars: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def _evidence_label(item: dict) -> str:
    prefix = "Figura" if item.get("type") == "image" else "Texto"
    filename = item.get("filename") or "Documento"
    page = item.get("page")
    page_text = f", pagina {page}" if page else ""
    return f"{prefix}: {filename}{page_text}"


def _build_evidence_summary(text_contexts: list[dict], image_sources: list[dict]) -> str:
    items = (text_contexts + image_sources)[:_MAX_EVIDENCE_ITEMS_FOR_ASSESSMENT]
    if not items:
        return "Sin evidencia recuperada."

    parts: list[str] = []
    for idx, item in enumerate(items, start=1):
        parts.append(
            f"[{idx}] {_evidence_label(item)}\n"
            f"{_truncate(item.get('content', ''), _MAX_EVIDENCE_CHARS_FOR_ASSESSMENT)}"
        )
    return "\n\n".join(parts)


def _extract_json_object(text: str) -> dict | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _normalize_assessment(raw: dict | None) -> dict:
    if not raw:
        return {"sufficient": True, "missing": "", "followup_queries": []}

    followups = raw.get("followup_queries", [])
    if not isinstance(followups, list):
        followups = []
    followups = [
        str(q).strip()
        for q in followups
        if isinstance(q, str) and str(q).strip()
    ][:_MAX_FOLLOWUP_QUERIES]

    sufficient_raw = raw.get("sufficient", True)
    if isinstance(sufficient_raw, bool):
        sufficient = sufficient_raw
    elif isinstance(sufficient_raw, str):
        sufficient = sufficient_raw.strip().lower() not in {"false", "no", "0"}
    else:
        sufficient = bool(sufficient_raw)

    return {
        "sufficient": sufficient,
        "missing": str(raw.get("missing", "") or "").strip(),
        "followup_queries": followups,
    }


async def _assess_evidence(
    message: str,
    text_contexts: list[dict],
    image_sources: list[dict],
) -> dict:
    user_content = (
        f"Pregunta original:\n{message}\n\n"
        f"Evidencia recuperada:\n{_build_evidence_summary(text_contexts, image_sources)}"
    )
    messages = [
        {"role": "system", "content": _ASSESSMENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    def _run_llm() -> str:
        llm = get_chat_llm()
        result = llm.create_chat_completion(
            messages=messages,
            max_tokens=320,
            temperature=0.0,
            top_p=0.9,
            stop=["<|eot_id|>", "<|end_of_text|>"],
        )
        return result["choices"][0]["message"].get("content") or ""

    try:
        async with inference_queue.acquire(priority=0, label="agent-assess"):
            raw_text = await asyncio.to_thread(_run_llm)
    except Exception as exc:
        logger.warning("Agentic evidence assessment failed; using current evidence: %s", exc)
        return {"sufficient": True, "missing": "", "followup_queries": []}

    return _normalize_assessment(_extract_json_object(raw_text))


def _dedupe_key(item: dict) -> tuple:
    if item.get("type") == "image":
        return ("image", item.get("image_id") or "", item.get("doc_id") or "", item.get("page"))
    return (
        "text",
        item.get("doc_id") or "",
        item.get("page"),
        (item.get("content") or "")[:160],
    )


def _merge_unique(existing: list[dict], incoming: list[dict]) -> list[dict]:
    seen = {_dedupe_key(item) for item in existing}
    merged = list(existing)
    for item in incoming:
        key = _dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


async def _final_rerank(
    message: str,
    items: list[dict],
    document_ids: list[str] | None,
) -> list[dict]:
    if not items:
        return []

    num_docs = len(document_ids) if document_ids else 0
    multi = num_docs > 1
    effective_top_k = settings.rerank_top_k
    if multi:
        effective_top_k = min(
            settings.rerank_top_k + (num_docs - 1),
            settings.rerank_top_k_max,
        )
    effective_top_k = min(max(effective_top_k, settings.rerank_top_k), len(items))

    reranked = await reranker_svc.rerank(message, items, top_k=len(items))
    return rag._select_diverse(reranked, effective_top_k, multi)


async def build_agentic_context(
    message: str,
    document_ids: list[str] | None,
    history: list[dict] | None = None,
    status_callback: StatusCallback | None = None,
    trace_callback: TraceCallback | None = None,
) -> tuple[list[dict], list[dict]]:
    t0 = time.perf_counter()

    if status_callback:
        await status_callback("agent_searching", "Buscando evidencia inicial")
    if trace_callback:
        await trace_callback("agent_searching", "Buscando evidencia inicial", None, "running")

    text_contexts, image_sources = await rag.build_context(
        message,
        document_ids,
        history=history,
        status_callback=status_callback,
    )

    if trace_callback:
        total = len(text_contexts) + len(image_sources)
        await trace_callback(
            "agent_searching",
            "Evidencia inicial encontrada",
            f"{total} fragmentos candidatos",
            "completed",
        )

    if status_callback:
        await status_callback("agent_assessing", "Verificando cobertura de la evidencia")
    if trace_callback:
        await trace_callback(
            "agent_assessing",
            "Verificando si la evidencia alcanza",
            None,
            "running",
        )

    assessment = await _assess_evidence(message, text_contexts, image_sources)
    followup_queries = assessment["followup_queries"]

    if assessment["sufficient"] or not followup_queries:
        if trace_callback:
            detail = "La evidencia recuperada es suficiente"
            if not assessment["sufficient"] and not followup_queries:
                detail = "No se encontraron búsquedas adicionales fiables"
            await trace_callback("agent_assessing", "Cobertura verificada", detail, "completed")
        logger.info("agentic retrieval: %.3fs (single round)", time.perf_counter() - t0)
        return text_contexts, image_sources

    if trace_callback:
        await trace_callback(
            "agent_expanding",
            "Ampliando búsqueda documental",
            "; ".join(followup_queries),
            "running",
        )
    if status_callback:
        await status_callback("agent_expanding", "Ampliando búsqueda documental")

    merged_items = text_contexts + image_sources
    for query in followup_queries[:_MAX_FOLLOWUP_QUERIES]:
        more_text, more_images = await rag.build_context(
            query,
            document_ids,
            history=history,
            status_callback=status_callback,
        )
        merged_items = _merge_unique(merged_items, more_text + more_images)

    final_items = await _final_rerank(message, merged_items, document_ids)
    final_text = [item for item in final_items if item.get("type") == "text"]
    final_images = [item for item in final_items if item.get("type") == "image"]

    if trace_callback:
        await trace_callback(
            "agent_expanding",
            "Búsqueda ampliada completada",
            f"{len(final_items)} evidencias seleccionadas",
            "completed",
        )
    if status_callback:
        await status_callback("agent_finalizing", "Preparando respuesta con evidencia verificada")

    logger.info("agentic retrieval: %.3fs (expanded)", time.perf_counter() - t0)
    return final_text, final_images
