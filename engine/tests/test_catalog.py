from folio_engine.catalog import ModelTier, recommend
from folio_engine.hardware import HardwareInfo

A = ModelTier("a", 5, 7, "Small")
B = ModelTier("b", 9, 12, "Medium")
C = ModelTier("c", 20, 24, "Large")
CATALOG = [A, B, C]


def hw(budget_gb: float, disk: float) -> HardwareInfo:
    # Non-Apple, no GPU: budget = 0.5 * RAM
    return HardwareInfo("windows", "AMD64", budget_gb * 2, False, None, disk)


def test_picks_largest_fitting():
    r = recommend(hw(16.8, 500), CATALOG)
    assert r.model == B and r.reason == "ok"


def test_memory_too_small():
    r = recommend(hw(2, 500), CATALOG)
    assert r.model is None and r.reason == "memory"
    assert "API key" in r.message


def test_disk_too_small():
    r = recommend(hw(16.8, 8), CATALOG)
    assert r.model is None and r.reason == "disk"
    assert r.free_disk_needed_gb == 3.0


def test_est_minutes():
    assert recommend(hw(16.8, 500), CATALOG).est_minutes == 16
