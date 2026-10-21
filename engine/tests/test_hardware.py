import subprocess

from folio_engine import hardware
from folio_engine.hardware import HardwareInfo, memory_budget_gb


def hw(**kw):
    base = {
        "os": "macos",
        "arch": "arm64",
        "total_ram_gb": 24,
        "apple_silicon": True,
        "gpu_vram_gb": None,
        "free_disk_gb": 500,
    }
    base.update(kw)
    return HardwareInfo(**base)


def test_budget_apple_silicon():
    assert memory_budget_gb(hw()) == 16.8


def test_budget_nvidia():
    h = hw(os="windows", arch="AMD64", apple_silicon=False, gpu_vram_gb=12)
    assert memory_budget_gb(h) == 10.8


def test_budget_nvidia_too_small_falls_back_to_ram():
    h = hw(os="windows", apple_silicon=False, gpu_vram_gb=4, total_ram_gb=32)
    assert memory_budget_gb(h) == 16.0


def test_budget_plain_ram():
    h = hw(os="windows", apple_silicon=False, total_ram_gb=32)
    assert memory_budget_gb(h) == 16.0


def _capture_run(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, stdout="8192\n")

    monkeypatch.setattr(hardware.subprocess, "run", fake_run)
    return seen


def test_nvidia_smi_runs_without_console_window_on_windows(monkeypatch):
    seen = _capture_run(monkeypatch)
    monkeypatch.setattr(hardware.sys, "platform", "win32")
    assert hardware._nvidia_vram_gb() == 8
    assert seen["creationflags"] == hardware.CREATE_NO_WINDOW == 0x08000000


def test_nvidia_smi_has_no_creationflags_elsewhere(monkeypatch):
    seen = _capture_run(monkeypatch)
    monkeypatch.setattr(hardware.sys, "platform", "darwin")
    assert hardware._nvidia_vram_gb() == 8
    assert seen.get("creationflags", 0) == 0
