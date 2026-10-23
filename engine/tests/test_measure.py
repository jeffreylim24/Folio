import importlib.util
from pathlib import Path

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
