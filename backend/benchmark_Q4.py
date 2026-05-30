#!/usr/bin/env python3
"""
benchmark.py — Benchmark de modelos LLM para el sistema RAG del BMSC.

Replica exactamente el entorno de inferencia del backend (model_manager.py + rag.py)
sin depender de él.  Evalúa velocidad de prefill, tokens/s de generación, TTFT
y calidad de razonamiento sobre el contenido real de prefill.txt.

Uso:
    python benchmark.py                      # Ejecutar benchmark completo
    python benchmark.py --download-only      # Solo descargar modelos
    python benchmark.py --models 0 2         # Probar solo modelos por índice
    python benchmark.py --runs 3             # 3 repeticiones por modelo
    python benchmark.py --max-tokens 512     # Limitar tokens de salida
    python benchmark.py --list               # Listar modelos disponibles
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

# ── Cargar .env si existe ────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# ── Configuración (valores idénticos al backend config.py / .env) ────────────
HF_CACHE_DIR = os.getenv("HF_CACHE_DIR", "./models_cache")
CACHE_PATH   = Path(HF_CACHE_DIR)
CACHE_PATH.mkdir(parents=True, exist_ok=True)

CONTEXT_FILE = Path(__file__).parent / "prefill.txt"

# ── Parámetros de inferencia — réplica exacta de config.py ───────────────────
# Estos son los valores por defecto del backend; se pueden sobreescribir via CLI.
DEFAULT_N_CTX           = 8192
DEFAULT_MAX_TOKENS      = 1024
DEFAULT_TEMPERATURE     = 0.0   # Greedy para benchmark determinista; el backend usa 0.7 en producción
DEFAULT_TOP_P           = 0.8
DEFAULT_TOP_K           = 20
DEFAULT_REPEAT_PENALTY  = 1.1
DEFAULT_SEED            = 42    # Semilla fija: garantiza reproducibilidad entre corridas del benchmark
STOP_TOKENS             = ["<|im_end|>", "<|endoftext|>", "Usuario:", "\nUser:"]

# ── System prompt — réplica exacta de rag.py ─────────────────────────────────
# /no_think se antepone SOLO para modelos Qwen (desactiva su thinking mode).
_SYSTEM_PROMPT_BASE = """Eres un asistente experto del banco. Tu función es ayudar a los empleados
a consultar la documentación interna del banco de manera precisa y útil.

Directrices:
- Responde siempre en español, de manera clara y profesional.
- Basa tus respuestas exclusivamente en el contexto proporcionado.
- Si la información no está en el contexto, indícalo claramente.
- Cita las fuentes cuando sea relevante (nombre del documento y página).
- Para procedimientos, usa listas numeradas. Para información general, usa párrafos.
- Nunca inventes información que no esté en los documentos proporcionados.
- El contexto puede incluir fragmentos de texto y descripciones textuales de figuras, tablas o
  diagramas extraídas de los documentos. Úsalas para responder preguntas sobre contenido visual."""


def _is_qwen3_model(model_name: str) -> bool:
    """Detecta si el modelo es Qwen3 (único que soporta /no_think)."""
    return "qwen3" in model_name.lower()

# ── Preguntas de evaluación — basadas en el contenido real de prefill.txt ────
# Cada pregunta evalúa un tipo distinto de razonamiento.
TEST_QUESTIONS = [
    {
        "tag": "BÚSQUEDA FACTUAL",
        "pregunta": "¿Cuál es la dirección IP del servidor HVADIFEJREN01 y qué usuarios tiene configurados?",
        "evalua": "Capacidad de localizar datos exactos en una tabla.",
    },
    {
        "tag": "RAZONAMIENTO PROCEDIMENTAL",
        "pregunta": (
            "Si el status de UiPath Assistant está en color rojo después de reiniciar "
            "el servidor, ¿qué pasos exactos debo seguir para solucionar el problema?"
        ),
        "evalua": "Capacidad de sintetizar un procedimiento multi-paso a partir del contexto.",
    },
    {
        "tag": "EXCEPCIÓN / CASO ESPECIAL",
        "pregunta": (
            "¿Qué consideraciones especiales debo tener al realizar el mantenimiento "
            "del servidor con IP 172.24.3.51 que no aplican a los demás servidores?"
        ),
        "evalua": "Identificar excepciones y casos especiales dentro de un procedimiento general.",
    },
    {
        "tag": "COMPRENSIÓN GLOBAL",
        "pregunta": (
            "Resume los pasos principales del protocolo de mantenimiento regular "
            "de los servidores UiPath del BMSC, desde el inicio hasta la verificación final."
        ),
        "evalua": "Comprensión global del documento y capacidad de síntesis.",
    },
]

# ── Modelos candidatos a evaluar ─────────────────────────────────────────────
MODELS_TO_TEST = [
    {
        "nombre": "Qwen3-4B (Modelo Actual del Backend - Q4)",
        "repo_id": "bartowski/Qwen_Qwen3-4B-GGUF",
        "filename": "Qwen_Qwen3-4B-Q4_K_M.gguf",
    },
    {
        "nombre": "Qwen2.5-1.5B-Instruct (Q4)",
        "repo_id": "bartowski/Qwen2.5-1.5B-Instruct-GGUF",
        "filename": "Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
    },
    {
        "nombre": "Llama-3.2-1B-Instruct (Q4)",
        "repo_id": "bartowski/Llama-3.2-1B-Instruct-GGUF",
        "filename": "Llama-3.2-1B-Instruct-Q4_K_M.gguf",
    },
    {
        "nombre": "Llama-3.2-3B-Instruct (Q4)",
        "repo_id": "bartowski/Llama-3.2-3B-Instruct-GGUF",
        "filename": "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
    },
    {
        "nombre": "DeepSeek-V2-Lite-Chat (Q4)",
        "repo_id": "mradermacher/DeepSeek-V2-Lite-Chat-GGUF",
        "filename": "DeepSeek-V2-Lite-Chat.Q4_K_M.gguf",
    },
]

# ═════════════════════════════════════════════════════════════════════════════
# Utilidades
# ═════════════════════════════════════════════════════════════════════════════

def _download_file(label: str, repo_id: str, filename: str, max_attempts: int = 8) -> str:
    """Descarga un archivo GGUF con reintentos exponenciales."""
    from huggingface_hub import hf_hub_download

    print(f"\n{'─'*60}")
    print(f" Descarga: {label}")
    print(f"     repo : {repo_id}")
    print(f"     file : {filename}")
    sys.stdout.flush()

    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                cache_dir=str(CACHE_PATH),
            )
            print(f"     ✓ OK → {path}")
            return path
        except Exception as exc:
            last_exc = exc
            wait = min(2 ** (attempt - 1), 60)
            print(f"     ⚠ Intento {attempt}/{max_attempts}: {exc.__class__.__name__}: {exc}")
            if attempt < max_attempts:
                print(f"       Reintentando en {wait}s...", flush=True)
                time.sleep(wait)

    raise RuntimeError(
        f"No se pudo descargar '{filename}' tras {max_attempts} intentos."
    ) from last_exc


def _filter_think_blocks(raw_text: str) -> str:
    """Elimina bloques <think>...</think> que Qwen3 emite incluso con /no_think.
    Replica exactamente el filtrado de rag.py stream_chat()."""
    return re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()


def _build_messages(contexto_rag: str, pregunta: str, is_qwen: bool = False) -> list[dict]:
    """Construye los mensajes ChatML exactamente como _build_messages() en rag.py.
    Antepone /no_think al system prompt solo para modelos Qwen."""
    system_prompt = ("/no_think\n" if is_qwen else "") + _SYSTEM_PROMPT_BASE
    user_content = f"CONTEXTO DE DOCUMENTOS:\n{contexto_rag}\n\nPregunta: {pregunta}"
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_content},
    ]


def _load_context() -> str:
    """Carga el archivo de contexto RAG para las pruebas."""
    if not CONTEXT_FILE.exists():
        print(f"  ⚠ No se encontró '{CONTEXT_FILE}'. Creando archivo de ejemplo...")
        sample = (
            "# PROTOCOLO DE MANTENIMIENTO - SERVIDORES BMSC\n"
            "## LISTADO DE SERVIDORES\n"
            "| Nombre | IP | Usuario |\n"
            "| HVADIFEJREN01 | 172.24.3.51 | Gestor |\n"
            "## PASOS\n"
            "1. Reiniciar la máquina.\n"
            "2. Cambiar resolución a 1920x1080.\n"
            "3. Ejecutar UiPath Assistant como administrador.\n"
        ) * 10
        CONTEXT_FILE.write_text(sample, encoding="utf-8")

    text = CONTEXT_FILE.read_text(encoding="utf-8")
    print(f" Contexto cargado: {len(text):,} caracteres desde {CONTEXT_FILE.name}")
    return text


# ═════════════════════════════════════════════════════════════════════════════
# Ejecución del benchmark por modelo
# ═════════════════════════════════════════════════════════════════════════════

def _run_single_question(
    llm,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    top_p: float,
    top_k: int,
    repeat_penalty: float,
) -> dict:
    """Ejecuta una pregunta y retorna métricas + respuesta.
    Usa create_chat_completion() con streaming — réplica exacta de rag.py stream_chat()."""

    start_time = time.perf_counter()

    stream = llm.create_chat_completion(
        messages=messages,
        max_tokens=max_tokens,
        stream=True,
        stop=STOP_TOKENS,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        repeat_penalty=repeat_penalty,
    )

    ttft = None
    start_decode = None
    tokens_total = 0        # Tokens generados por el modelo (incluye <think>)
    raw_text = ""

    # ── Streaming con filtrado de <think> (réplica de rag.py) ────────────
    in_think = False
    think_buf = ""
    visible_text = ""

    for chunk in stream:
        delta = chunk["choices"][0].get("delta", {})
        content: str = delta.get("content") or ""
        if not content:
            continue

        if ttft is None:
            ttft = time.perf_counter() - start_time
            start_decode = time.perf_counter()

        tokens_total += 1
        raw_text += content

        # ── Filtrado de think blocks en streaming (réplica exacta) ───
        think_buf += content
        while True:
            if not in_think:
                idx = think_buf.find("<think>")
                if idx == -1:
                    visible_text += think_buf
                    think_buf = ""
                    break
                visible_text += think_buf[:idx]
                think_buf = think_buf[idx + len("<think>"):]
                in_think = True
            else:
                idx = think_buf.find("</think>")
                if idx == -1:
                    think_buf = ""
                    break
                think_buf = think_buf[idx + len("</think>"):].lstrip("\n")
                in_think = False

    # Flush buffer restante
    if think_buf and not in_think:
        visible_text += think_buf

    end_time = time.perf_counter()

    # ── Calcular métricas ────────────────────────────────────────────────
    total_time = end_time - start_time
    visible_text = visible_text.strip()

    if ttft is None:
        ttft = total_time

    if start_decode and tokens_total > 1:
        decode_time = end_time - start_decode
        gen_tok_s = (tokens_total - 1) / decode_time if decode_time > 0 else 0.0
    else:
        decode_time = 0.0
        gen_tok_s = 0.0

    return {
        "ttft": ttft,
        "total_time": total_time,
        "tokens_total": tokens_total,
        "gen_tok_s": gen_tok_s,
        "raw_text": raw_text,
        "visible_text": visible_text,
        "had_think_blocks": "<think>" in raw_text,
    }


def benchmark_model(
    model_info: dict,
    contexto_rag: str,
    questions: list[dict],
    args: argparse.Namespace,
) -> dict:
    """Carga un modelo, ejecuta todas las preguntas, retorna resultados."""
    from llama_cpp import Llama

    nombre = model_info["nombre"]

    # 1. Descargar si es necesario
    if not args.skip_download:
        model_path = _download_file(nombre, model_info["repo_id"], model_info["filename"])
    else:
        from huggingface_hub import hf_hub_download
        model_path = hf_hub_download(
            repo_id=model_info["repo_id"],
            filename=model_info["filename"],
            cache_dir=str(CACHE_PATH),
            local_files_only=True,
        )

    # 2. Calcular threads (réplica de model_manager.py)
    total_cores = os.cpu_count() or 4
    n_threads = max(1, total_cores - 2)

    print(f"\n{'═'*60}")
    print(f" MODELO: {nombre}")
    print(f"{'═'*60}")
    print(f"  Archivo : {Path(model_path).name}")
    print(f"  n_ctx   : {DEFAULT_N_CTX}")
    print(f"  threads : {n_threads} ({total_cores} cores, 2 reservados)")
    print(f"  mmap    : False  |  mlock: True")
    print(f"  temp    : {args.temperature}  |  top_p: {args.top_p}  |  top_k: {args.top_k}")
    print(f"  max_tok : {args.max_tokens}  |  repeat_penalty: {args.repeat_penalty}")
    sys.stdout.flush()

    # 3. Cargar modelo — parámetros IDÉNTICOS a model_manager.py _load_all_sync()
    t_load_start = time.perf_counter()
    llm = Llama(
        model_path=model_path,
        n_ctx=DEFAULT_N_CTX,
        n_batch=512,
        n_threads=n_threads,
        n_threads_batch=n_threads,
        use_mmap=False,
        use_mlock=True,
        verbose=False,
        seed=DEFAULT_SEED,
    )
    t_load = time.perf_counter() - t_load_start
    print(f"  ⏱ Modelo cargado en {t_load:.2f}s")

    # 4. Ejecutar preguntas
    question_results = []

    for q_idx, question in enumerate(questions):
        print(f"\n  {'─'*56}")
        print(f"Pregunta {q_idx + 1}/{len(questions)}: [{question['tag']}]")
        print(f"     {question['pregunta']}")
        print(f"     Evalúa: {question['evalua']}")
        print(f"  {'─'*56}")
        sys.stdout.flush()

        run_results = []
        for run in range(1, args.runs + 1):
            if args.runs > 1:
                print(f"\n     ▸ Run {run}/{args.runs}")

            # KV cache frío: cada run parte de prefill completo, como en una query RAG real
            # donde el contexto cambia en cada consulta y no hay cache de prefijo reutilizable.
            llm.reset()
            if hasattr(llm, "_ctx") and hasattr(llm._ctx, "kv_cache_clear"):
                llm._ctx.kv_cache_clear()

            messages = _build_messages(contexto_rag, question["pregunta"], is_qwen=_is_qwen3_model(nombre))
            result = _run_single_question(
                llm=llm,
                messages=messages,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
                top_p=args.top_p,
                top_k=args.top_k,
                repeat_penalty=args.repeat_penalty,
            )
            run_results.append(result)

            # Imprimir métricas del run
            print(f"     TTFT (prefill)     : {result['ttft']:.3f}s")
            print(f"     Generación         : {result['gen_tok_s']:.2f} tok/s")
            print(f"     Tokens generados   : {result['tokens_total']}")
            print(f"     Tiempo total       : {result['total_time']:.2f}s")
            if result["had_think_blocks"]:
                print(f"     ⚠ Think blocks     : Detectados y filtrados")

        # Promediar runs
        avg_ttft     = sum(r["ttft"] for r in run_results) / len(run_results)
        avg_tok_s    = sum(r["gen_tok_s"] for r in run_results) / len(run_results)
        avg_tokens   = sum(r["tokens_total"] for r in run_results) / len(run_results)
        avg_total    = sum(r["total_time"] for r in run_results) / len(run_results)

        # Imprimir respuesta completa (del último run)
        last_visible = run_results[-1]["visible_text"]
        print(f"\n     {'·'*50}")
        print(f"     RESPUESTA COMPLETA:")
        print(f"     {'·'*50}")
        for line in last_visible.split("\n"):
            print(f"     {line}")
        print(f"     {'·'*50}")

        if args.runs > 1:
            print(f"\n    PROMEDIO ({args.runs} runs):")
            print(f"        TTFT     : {avg_ttft:.3f}s")
            print(f"        tok/s    : {avg_tok_s:.2f}")
            print(f"        tokens   : {avg_tokens:.0f}")
            print(f"        total    : {avg_total:.2f}s")

        question_results.append({
            "tag": question["tag"],
            "pregunta": question["pregunta"],
            "avg_ttft": avg_ttft,
            "avg_tok_s": avg_tok_s,
            "avg_tokens": avg_tokens,
            "avg_total": avg_total,
            "respuesta": last_visible,
            "had_think": any(r["had_think_blocks"] for r in run_results),
        })

    # 5. Liberar memoria
    del llm

    return {
        "nombre": nombre,
        "load_time": t_load,
        "questions": question_results,
    }


# ═════════════════════════════════════════════════════════════════════════════
# Tabla resumen
# ═════════════════════════════════════════════════════════════════════════════

def print_summary(all_results: list[dict]) -> None:
    """Imprime tabla resumen comparativa en formato Markdown."""

    print(f"\n\n{'═'*80}")
    print(" RESUMEN COMPARATIVO DEL BENCHMARK")
    print(f"{'═'*80}\n")

    # ── Tabla 1: Métricas de velocidad por modelo (promedios globales) ───
    print("### Métricas de Velocidad (promedio global)\n")
    print("| Modelo | Carga (s) | TTFT (s) | Gen (tok/s) | Tokens | Total (s) |")
    print("| :--- | :---: | :---: | :---: | :---: | :---: |")

    for res in all_results:
        qs = res["questions"]
        avg_ttft  = sum(q["avg_ttft"] for q in qs) / len(qs)
        avg_tok_s = sum(q["avg_tok_s"] for q in qs) / len(qs)
        avg_toks  = sum(q["avg_tokens"] for q in qs) / len(qs)
        avg_total = sum(q["avg_total"] for q in qs) / len(qs)
        think_flag = " ⚠" if any(q["had_think"] for q in qs) else ""

        print(
            f"| {res['nombre']}{think_flag} "
            f"| {res['load_time']:.2f} "
            f"| {avg_ttft:.3f} "
            f"| {avg_tok_s:.2f} "
            f"| {avg_toks:.0f} "
            f"| {avg_total:.2f} |"
        )

    # ── Tabla 2: Desglose por pregunta ───────────────────────────────────
    print(f"\n### Desglose por Pregunta\n")
    for q_idx, tag in enumerate(r["tag"] for r in all_results[0]["questions"]):
        print(f"\n**[{tag}]**\n")
        print("| Modelo | TTFT (s) | tok/s | Tokens | Total (s) |")
        print("| :--- | :---: | :---: | :---: | :---: |")
        for res in all_results:
            q = res["questions"][q_idx]
            print(
                f"| {res['nombre']} "
                f"| {q['avg_ttft']:.3f} "
                f"| {q['avg_tok_s']:.2f} "
                f"| {q['avg_tokens']:.0f} "
                f"| {q['avg_total']:.2f} |"
            )

    # ── Leyenda ──────────────────────────────────────────────────────────
    print(f"\n{'─'*80}")
    print("  ⚠ = El modelo emitió bloques <think> (filtrados de la respuesta visible)")
    print("  TTFT = Time To First Token (tiempo de prefill)")
    print("  tok/s = Tokens generados por segundo (velocidad de decode)")
    print(f"{'═'*80}\n")


# ═════════════════════════════════════════════════════════════════════════════
# CLI y punto de entrada
# ═════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark de modelos LLM para el sistema RAG del BMSC.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--list", action="store_true",
        help="Listar modelos disponibles y salir.",
    )
    parser.add_argument(
        "--models", nargs="+", type=int, metavar="IDX",
        help="Índices de modelos a probar (ver --list). Por defecto: todos.",
    )
    parser.add_argument(
        "--questions", nargs="+", type=int, metavar="IDX",
        help="Índices de preguntas a ejecutar (0-3). Por defecto: todas.",
    )
    parser.add_argument(
        "--runs", type=int, default=1, metavar="N",
        help="Repeticiones por pregunta para promediar métricas (default: 1).",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=DEFAULT_MAX_TOKENS, metavar="N",
        help=f"Máximo de tokens a generar (default: {DEFAULT_MAX_TOKENS}).",
    )
    parser.add_argument(
        "--temperature", type=float, default=DEFAULT_TEMPERATURE,
        help=f"Temperatura de sampling (default: {DEFAULT_TEMPERATURE}).",
    )
    parser.add_argument(
        "--top-p", type=float, default=DEFAULT_TOP_P,
        help=f"Top-p (nucleus sampling) (default: {DEFAULT_TOP_P}).",
    )
    parser.add_argument(
        "--top-k", type=int, default=DEFAULT_TOP_K,
        help=f"Top-k sampling (default: {DEFAULT_TOP_K}).",
    )
    parser.add_argument(
        "--repeat-penalty", type=float, default=DEFAULT_REPEAT_PENALTY,
        help=f"Penalización de repetición (default: {DEFAULT_REPEAT_PENALTY}).",
    )
    parser.add_argument(
        "--download-only", action="store_true",
        help="Solo descargar modelos, no ejecutar benchmark.",
    )
    parser.add_argument(
        "--skip-download", action="store_true",
        help="Asumir que los modelos ya están descargados (falla si no existen).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # ── Listar modelos ───────────────────────────────────────────────────
    if args.list:
        print("\nModelos disponibles:\n")
        for i, m in enumerate(MODELS_TO_TEST):
            print(f"  [{i}] {m['nombre']}")
            print(f"      {m['repo_id']} / {m['filename']}")
        print(f"\nPreguntas disponibles:\n")
        for i, q in enumerate(TEST_QUESTIONS):
            print(f"  [{i}] [{q['tag']}] {q['pregunta']}")
        return

    # ── Verificar dependencias ───────────────────────────────────────────
    try:
        from llama_cpp import Llama  # noqa: F401
    except ImportError:
        print("Error: No se encontró 'llama-cpp-python'.")
        print("   Instálalo con: pip install llama-cpp-python")
        sys.exit(1)

    # ── Seleccionar modelos y preguntas ──────────────────────────────────
    if args.models is not None:
        selected_models = []
        for idx in args.models:
            if 0 <= idx < len(MODELS_TO_TEST):
                selected_models.append(MODELS_TO_TEST[idx])
            else:
                print(f"Índice de modelo inválido: {idx} (máximo: {len(MODELS_TO_TEST)-1})")
        if not selected_models:
            print("No se seleccionaron modelos válidos.")
            sys.exit(1)
    else:
        selected_models = MODELS_TO_TEST

    if args.questions is not None:
        selected_questions = []
        for idx in args.questions:
            if 0 <= idx < len(TEST_QUESTIONS):
                selected_questions.append(TEST_QUESTIONS[idx])
            else:
                print(f"Índice de pregunta inválido: {idx} (máximo: {len(TEST_QUESTIONS)-1})")
        if not selected_questions:
            print("No se seleccionaron preguntas válidas.")
            sys.exit(1)
    else:
        selected_questions = TEST_QUESTIONS

    # ── Solo descarga ────────────────────────────────────────────────────
    if args.download_only:
        print("\n📥 Modo descarga: solo descargando modelos...\n")
        for m in selected_models:
            _download_file(m["nombre"], m["repo_id"], m["filename"])
        print("\n✓ Descarga completada.")
        return

    # ── Cargar contexto ──────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print(" BENCHMARK RAG — BANCO MERCANTIL SANTA CRUZ")
    print(f"{'═'*60}")

    contexto_rag = _load_context()

    total_cores = os.cpu_count() or 4
    n_threads = max(1, total_cores - 2)

    print(f"\n  Sistema:")
    print(f"     CPU cores  : {total_cores}")
    print(f"     Threads    : {n_threads} (cpu_count - 2)")
    print(f"     Modelos    : {len(selected_models)}")
    print(f"     Preguntas  : {len(selected_questions)}")
    print(f"     Runs/preg  : {args.runs}")
    print(f"     Contexto   : {len(contexto_rag):,} chars")

    # ── Entorno de inferencia (para referencia) ──────────────────────────
    print(f"\n  Parámetros de inferencia (réplica del backend):")
    print(f"     n_ctx          : {DEFAULT_N_CTX}")
    print(f"     max_tokens     : {args.max_tokens}")
    print(f"     temperature    : {args.temperature}")
    print(f"     top_p          : {args.top_p}")
    print(f"     top_k          : {args.top_k}")
    print(f"     repeat_penalty : {args.repeat_penalty}")
    print(f"     use_mmap       : False")
    print(f"     use_mlock      : True")
    print(f"     stop           : {STOP_TOKENS}")
    print(f"     /no_think      : Sí (en system prompt)")
    print(f"     seed           : {DEFAULT_SEED} (greedy determinista; producción usa 0.7)")
    print(f"     KV cache       : reset por run (prefill completo en cada consulta)")

    # ── Ejecutar benchmark ───────────────────────────────────────────────
    all_results = []

    for model_info in selected_models:
        try:
            result = benchmark_model(model_info, contexto_rag, selected_questions, args)
            all_results.append(result)
        except Exception as exc:
            print(f"\n Error con {model_info['nombre']}: {exc}")
            continue

    # ── Resumen ──────────────────────────────────────────────────────────
    if all_results:
        print_summary(all_results)
    else:
        print("\nNo se obtuvieron resultados de ningún modelo.")


if __name__ == "__main__":
    main()