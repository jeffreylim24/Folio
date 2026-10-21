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
