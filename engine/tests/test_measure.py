import importlib.util
import json
from pathlib import Path

import httpx

from folio_engine.ollama.client import PullProgress

_PATH = Path(__file__).parent.parent / "scripts" / "measure_models.py"
_spec = importlib.util.spec_from_file_location("measure_models", _PATH)
measure = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(measure)


def test_row_from():
    row = measure.row_from(
        "m:1b",
        {"size": 9_000_000_000, "size_vram": 4_500_000_000},
        {"prompt_eval_count": 9800, "eval_count": 50, "eval_duration": 2_000_000_000},
    )
    assert row == {
        "tag": "m:1b",
        "loaded_gb": 8.4,
        "gpu_percent": 50,
        "prompt_tokens": 9800,
        "tokens_per_s": 25.0,
    }


def test_row_from_handles_zero_size_and_duration():
    row = measure.row_from("m", {"size": 0, "size_vram": 0}, {})
    assert row["gpu_percent"] == 0
    assert row["tokens_per_s"] == 0.0


def test_build_prompt_is_about_35k_chars():
    prompt = measure.build_prompt()
    assert 35_000 <= len(prompt) <= 36_000
    assert prompt.rstrip().endswith("List the job titles as JSON.")


def _fake_client(monkeypatch):
    class Fake:
        def pull(self, tag):
            return iter(())

    monkeypatch.setattr(measure, "_pull", lambda c, t: None)
    return Fake()


def _http(handler):
    return httpx.Client(base_url="http://x", transport=httpx.MockTransport(handler))


def test_measure_payload_and_latest_alias(monkeypatch):
    thinking = next(m for m in measure.MODEL_CATALOG if m.thinking)
    plain = next(m for m in measure.MODEL_CATALOG if not m.thinking)
    sent = {}

    def handler(req):
        if req.url.path == "/api/chat":
            body = json.loads(req.content)
            sent[body["model"]] = body
            return httpx.Response(
                200,
                json={
                    "prompt_eval_count": 10,
                    "eval_count": 10,
                    "eval_duration": 10**9,
                },
            )
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": f"{t}:latest", "size": 2**30, "size_vram": 2**30}
                    for t in ("nolatest",)
                ]
                + [
                    {"name": plain.tag, "size": 2**30, "size_vram": 2**30},
                    {"name": thinking.tag, "size": 2**30, "size_vram": 2**30},
                ]
            },
        )

    c = _fake_client(monkeypatch)
    with _http(handler) as http:
        r1 = measure.measure(c, http, thinking.tag, False)
        r2 = measure.measure(c, http, plain.tag, False)
    assert r1["loaded_gb"] == 1.0 and r2["tokens_per_s"] == 10.0
    t = sent[thinking.tag]
    assert t["stream"] is False and t["think"] is False
    assert t["options"] == {
        "num_ctx": thinking.context_tokens,
        "temperature": 0.2,
        "presence_penalty": 0,
    }
    assert "think" not in sent[plain.tag]
    assert sent[plain.tag]["options"]["num_ctx"] == plain.context_tokens


def test_same_model_latest_alias():
    assert measure._same_model("x", "x:latest")
    assert measure._same_model("x:latest", "x")
    assert not measure._same_model("x:1b", "x")


def test_failure_gives_error_row_and_next_model_continues(monkeypatch):
    a, b = measure.MODEL_CATALOG[0], measure.MODEL_CATALOG[1]

    def handler(req):
        if req.url.path == "/api/chat":
            if json.loads(req.content)["model"] == a.tag:
                return httpx.Response(500, json={"error": "out of memory"})
            return httpx.Response(200, json={"eval_count": 1, "eval_duration": 10**9})
        return httpx.Response(
            200, json={"models": [{"name": b.tag, "size": 2**30, "size_vram": 0}]}
        )

    c = _fake_client(monkeypatch)
    with _http(handler) as http:
        rows = [measure.measure(c, http, t, False) for t in (a.tag, b.tag)]
    assert rows[0]["tag"] == a.tag and "error" in rows[0]
    assert "error" not in rows[1] and rows[1]["loaded_gb"] == 1.0
    assert "ERROR" in measure.format_table(rows)


def test_ps_miss_lists_names(monkeypatch):
    a = measure.MODEL_CATALOG[0]

    def handler(req):
        if req.url.path == "/api/chat":
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"models": [{"name": "other:1"}]})

    with _http(handler) as http:
        row = measure.measure(_fake_client(monkeypatch), http, a.tag, False)
    assert "other:1" in row["error"]


class _PullOnly:
    def __init__(self, events):
        self._events = events

    def pull(self, tag):
        yield from self._events


def test_pull_progress_adds_up_all_layers(capsys):
    events = [
        PullProgress("pulling big", "big", 1000, 0),
        PullProgress("pulling tiny", "tiny", 10, 10),  # a tiny layer finishes first
        PullProgress("pulling big", "big", 1000, 500),
        PullProgress("pulling big", "big", 1000, 1000),
    ]
    measure._pull(_PullOnly(events), "m")
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "  pulling m: 0%"
    assert "  pulling m: 50%" in lines
    assert lines[-1] == "  pulling m: 100%"
    assert lines.count("  pulling m: 100%") == 1
