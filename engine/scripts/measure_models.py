"""Measure how much memory each catalog model really uses in Ollama.

Developer tool, not shipped in the app. For each model it pulls the weights,
sends one ~10k-token resume-style prompt at Folio's context size, then reads
how much memory Ollama holds for it and how fast it generated.

Run (Ollama must be running; pulls are multi-GB downloads):

    cd engine
    uv run python scripts/measure_models.py                  # the three tier models
    uv run python scripts/measure_models.py qwen3:8b --delete  # chosen tags, then remove them

Options: --delete removes each model after measuring (saves disk);
--out FILE sets the JSON output path (default measure-results.json).

What to send back: the Markdown table printed at the end, or the JSON file.
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

from folio_engine.catalog import MODEL_CATALOG, find_model
from folio_engine.ollama.client import OllamaClient

_RESUME_BLOCK = (
    "Jane Doe, Senior Software Engineer at Acme Corp (2019-2024). Led a team of "
    "six building payment APIs in Python and Go; cut p95 latency by 40% and "
    "mentored four junior engineers. Skills: Python, Go, SQL, Kubernetes, AWS. "
    "Education: BSc Computer Science, State University, 2015-2019.\n"
)
_QUESTION = "List the job titles as JSON."
_PROMPT_CHARS = 35_000
_GB = 1024**3


def build_prompt() -> str:
    """About 35 000 characters (~10k tokens) of resume-like text plus the question."""
    reps = _PROMPT_CHARS // len(_RESUME_BLOCK) + 1
    return _RESUME_BLOCK * reps + "\n" + _QUESTION


def row_from(tag: str, ps_entry: dict, chat_body: dict) -> dict:
    size = ps_entry.get("size", 0)
    vram = ps_entry.get("size_vram", 0)
    eval_ns = chat_body.get("eval_duration", 0)
    tokens = chat_body.get("eval_count", 0)
    return {
        "tag": tag,
        "loaded_gb": round(size / _GB, 1),
        "gpu_percent": round(100 * vram / size) if size else 0,
        "prompt_tokens": chat_body.get("prompt_eval_count", 0),
        "tokens_per_s": round(tokens / (eval_ns / 1e9), 1) if eval_ns else 0.0,
    }


def format_table(rows: list[dict]) -> str:
    lines = [
        "| Model | Loaded GB | GPU % | Prompt tokens | Tokens/s |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['tag']} | {r['loaded_gb']} | {r['gpu_percent']} "
            f"| {r['prompt_tokens']} | {r['tokens_per_s']} |"
        )
    return "\n".join(lines)


def _pull(client: OllamaClient, tag: str) -> None:
    last = -5
    for p in client.pull(tag):
        if p.total and p.completed is not None:
            pct = int(100 * p.completed / p.total)
            if pct >= last + 5:
                last = pct
                print(f"  pulling {tag}: {pct}%", flush=True)


def measure(client: OllamaClient, http: httpx.Client, tag: str, delete: bool) -> dict:
    model = find_model(tag)
    if model is None:
        sys.exit(f"{tag} is not in the catalog")
    _pull(client, tag)
    payload = {
        "model": tag,
        "messages": [{"role": "user", "content": build_prompt()}],
        "stream": False,
        "options": {
            "num_ctx": model.context_tokens,
            "temperature": 0.2,
            "presence_penalty": 0,
        },
    }
    if model.thinking:
        payload["think"] = False
    print(f"  running {tag}...", flush=True)
    r = http.post("/api/chat", json=payload, timeout=None)
    r.raise_for_status()
    body = r.json()
    ps = http.get("/api/ps").json().get("models", [])
    entry = next((m for m in ps if tag in (m.get("name"), m.get("model"))), None)
    if entry is None:
        sys.exit(f"{tag} is not listed in /api/ps after the chat")
    row = row_from(tag, entry, body)
    if delete:
        http.request("DELETE", "/api/delete", json={"model": tag}).raise_for_status()
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tags", nargs="*", help="model tags (default: the tier models)")
    ap.add_argument("--delete", action="store_true", help="delete each model after")
    ap.add_argument("--out", default="measure-results.json")
    args = ap.parse_args()

    tags = args.tags or [m.tag for m in MODEL_CATALOG if m.tier]
    client = OllamaClient()
    if client.version() is None:
        sys.exit("Ollama is not running. Start it (or set OLLAMA_HOST) and retry.")
    rows = []
    with httpx.Client(base_url=client._base_url) as http:
        for tag in tags:
            print(tag, flush=True)
            rows.append(measure(client, http, tag, args.delete))
    Path(args.out).write_text(json.dumps(rows, indent=2))
    print("\n" + format_table(rows))
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
