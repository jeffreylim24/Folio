import subprocess

from folio_engine import hardware
from folio_engine.hardware import HardwareInfo, usable_memory_gb


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


def test_usable_apple_silicon():
    assert usable_memory_gb(HardwareInfo("macos", "arm64", 24, True, None, 500)) == 16.1


def test_usable_nvidia_prefers_ram_when_larger():
    h = HardwareInfo("windows", "AMD64", 32, False, 12, 500)
    assert usable_memory_gb(h) == 16.0


def test_usable_nvidia_big_gpu_uses_vram():
    h = HardwareInfo("windows", "AMD64", 32, False, 24, 500)
    assert usable_memory_gb(h) == 21.6


def test_usable_nvidia_small_ram_uses_vram():
    h = HardwareInfo("windows", "AMD64", 16, False, 12, 500)
    assert usable_memory_gb(h) == 10.8


def test_usable_small_nvidia_falls_back_to_ram():
    h = HardwareInfo("windows", "AMD64", 32, False, 4, 500)
    assert usable_memory_gb(h) == 16.0


def test_usable_plain_ram():
    h = hw(os="windows", apple_silicon=False, total_ram_gb=32)
    assert usable_memory_gb(h) == 16.0


def _capture_run(monkeypatch, stdout="NVIDIA GeForce RTX 4060, 8192\n"):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout)

    monkeypatch.setattr(hardware.subprocess, "run", fake_run)
    return seen


def test_nvidia_smi_runs_without_console_window_on_windows(monkeypatch):
    seen = _capture_run(monkeypatch)
    monkeypatch.setattr(hardware.sys, "platform", "win32")
    assert hardware._nvidia_gpu() == ("NVIDIA GeForce RTX 4060", 8)
    assert seen["creationflags"] == hardware.CREATE_NO_WINDOW == 0x08000000
    assert "--query-gpu=name,memory.total" in seen["cmd"]


def test_nvidia_smi_has_no_creationflags_elsewhere(monkeypatch):
    seen = _capture_run(monkeypatch)
    monkeypatch.setattr(hardware.sys, "platform", "darwin")
    assert hardware._nvidia_gpu() == ("NVIDIA GeForce RTX 4060", 8)
    assert seen.get("creationflags", 0) == 0


def test_nvidia_smi_largest_gpu_wins(monkeypatch):
    _capture_run(monkeypatch, "Small GPU, 4096\nBig GPU, 24576\n")
    assert hardware._nvidia_gpu() == ("Big GPU", 24)


def test_nvidia_smi_missing_returns_none(monkeypatch):
    def boom(cmd, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(hardware.subprocess, "run", boom)
    assert hardware._nvidia_gpu() is None


def test_mac_chip(monkeypatch):
    _capture_run(monkeypatch, "Apple M5\n")
    assert hardware._mac_chip() == "Apple M5"


def test_mac_chip_failure_is_none(monkeypatch):
    def boom(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(hardware.subprocess, "run", boom)
    assert hardware._mac_chip() is None


def test_nvidia_vram_is_rounded_for_display(monkeypatch):
    _capture_run(monkeypatch, "NVIDIA GeForce RTX 4070, 12282\n")
    assert hardware._nvidia_gpu() == ("NVIDIA GeForce RTX 4070", 12.0)
