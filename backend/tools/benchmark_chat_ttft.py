#!/usr/bin/env python3
"""Benchmark local de TTFT para el Llama de chat.

Ejemplos:
  PYTHONPATH=. python tools/benchmark_chat_ttft.py --prompt-tokens 500 1500 2600
  PYTHONPATH=. python tools/benchmark_chat_ttft.py --runs 2 --threads 2 4 --batches 1024 2048
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path

from huggingface_hub import hf_hub_download
from llama_cpp import Llama

from app.config import settings


def _resolve_model_path() -> str:
    return hf_hub_download(
        repo_id=settings.chat_gguf_repo,
        filename=settings.chat_gguf_filename,
        cache_dir=str(Path(settings.hf_cache_dir)),
        local_files_only=True,
    )


def _make_prompt(target_tokens: int) -> str:
    base = (
        "CONTEXTO DE DOCUMENTOS:\n"
        "[Fuente 1: Manual.pdf, página 1]\n"
        "El procedimiento operativo debe validarse con el supervisor antes de cerrar el caso. "
        "La respuesta debe citar la fuente cuando corresponda.\n\n"
    )
    text = base
    while len(text) // 4 < target_tokens:
        text += base
    return text


def _measure_once(llm: Llama, prompt_tokens: int, max_tokens: int) -> dict:
    messages = [
        {"role": "system", "content": "Responde en español, de forma breve y basada solo en el contexto."},
        {"role": "user", "content": _make_prompt(prompt_tokens) + "\nPregunta: ¿Qué debo hacer?"},
    ]
    start = time.perf_counter()
    first = 0.0
    n = 0
    for chunk in llm.create_chat_completion(
        messages=messages,
        max_tokens=max_tokens,
        stream=True,
        temperature=0.0,
    ):
        content = chunk["choices"][0]["delta"].get("content") or ""
        if not content:
            continue
        n += 1
        if first == 0.0:
            first = time.perf_counter()
    end = time.perf_counter()
    ttft = first - start if first else end - start
    gen_time = end - first if first else 0.0
    return {
        "ttft_s": ttft,
        "total_s": end - start,
        "tokens": n,
        "tok_s": n / gen_time if gen_time > 0 else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--threads", type=int, nargs="+", default=[1, 2, 4, 0])
    parser.add_argument("--batches", type=int, nargs="+", default=[512, 1024, 2048])
    parser.add_argument("--ubatches", type=int, nargs="+", default=[256, 512, 1024])
    parser.add_argument("--prompt-tokens", type=int, nargs="+", default=[500, 1500, 2600])
    parser.add_argument("--max-tokens", type=int, default=64)
    args = parser.parse_args()

    model_path = _resolve_model_path()
    total_cores = os.cpu_count() or 4
    rows = []

    for threads_arg in args.threads:
        threads = threads_arg or max(1, total_cores - 2)
        for batch in args.batches:
            for ubatch in args.ubatches:
                if ubatch > batch:
                    continue
                llm = Llama(
                    model_path=model_path,
                    n_ctx=settings.chat_n_ctx,
                    n_batch=batch,
                    n_ubatch=ubatch,
                    n_threads=threads,
                    n_threads_batch=threads,
                    n_gpu_layers=0,
                    use_mmap=False,
                    use_mlock=True,
                    verbose=False,
                )
                for prompt_tokens in args.prompt_tokens:
                    samples = [
                        _measure_once(llm, prompt_tokens, args.max_tokens)
                        for _ in range(args.runs)
                    ]
                    ttfts = [s["ttft_s"] for s in samples]
                    tok_s = [s["tok_s"] for s in samples]
                    row = {
                        "threads": threads,
                        "n_batch": batch,
                        "n_ubatch": ubatch,
                        "prompt_tokens_target": prompt_tokens,
                        "ttft_p50_s": statistics.median(ttfts),
                        "ttft_max_s": max(ttfts),
                        "tok_s_p50": statistics.median(tok_s),
                    }
                    rows.append(row)
                    print(json.dumps(row, ensure_ascii=False), flush=True)
                del llm

    print(json.dumps({"results": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
