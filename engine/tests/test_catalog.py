from folio_engine.catalog import (
    CONTEXT_TOKENS,
    MODEL_CATALOG,
    CatalogModel,
    advise,
    find_model,
    fit,
)
from folio_engine.hardware import HardwareInfo

S = CatalogModel("s:q", "s", "M", 3.0, 5.0, True, "b", "small")
B = CatalogModel("b:q", "b", "M", 6.0, 8.0, True, "b", "balanced")
X = CatalogModel("x:q", "x", "M", 18.0, 20.0, True, "b", "best")
T = CatalogModel("t:q", "t", "M", 9.0, 12.0, False, "b")


def mac(ram, disk):
    return HardwareInfo("macos", "arm64", ram, True, None, disk, chip="Apple M5")


def test_fit_bands():
    assert fit(B, 9.6) == "ok"  # 8.0 * 1.2 = 9.6
    assert fit(B, 9.5) == "tight"
    assert fit(B, 8.0) == "tight"
    assert fit(B, 7.9) == "no"


def test_recommended_and_context_properties():
    assert B.recommended_gb == 9.6
    assert B.context_tokens == CONTEXT_TOKENS
    small_ctx = CatalogModel("c:q", "c", "M", 1, 2, False, "b", max_context=8192)
    assert small_ctx.context_tokens == 8192


def test_advise_recommends_largest_tier_that_runs_well():
    a = advise(mac(24, 500), [S, B, X, T])  # usable 16.1
    assert a.recommended == "b:q" and a.reason == "ok"
    assert a.message == "We recommend b for your device."
    assert [o.tag for o in a.tiers] == ["s:q", "b:q", "x:q"]
    assert [o.tag for o in a.models] == ["s:q", "b:q", "t:q", "x:q"]
    rec = a.tiers[1]
    assert rec.note == (
        "Why: it needs about 8 GB and your device has 16.1 GB usable, "
        "so it runs smoothly with room to spare."
    )
    assert (
        a.tiers[0].note
        == "Faster, but writes noticeably weaker bullets. Your device can do better."
    )
    assert a.tiers[2].fit == "no"
    assert a.tiers[2].note == (
        "Needs about 20 GB, more than your 16.1 GB. "
        "It would be very slow or fail to load."
    )


def test_larger_model_that_fits_gets_runs_smoothly_note():
    big_ok = CatalogModel("o:q", "o", "M", 4.0, 9.0, False, "b")  # rec 10.8 <= 16.1
    a = advise(mac(24, 500), [S, B, X, big_ok])
    o = next(m for m in a.models if m.tag == "o:q")
    assert o.fit == "ok"
    assert o.note == "Runs smoothly: needs about 9 GB of your 16.1 GB."


def test_tight_note():
    o = next(m for m in advise(mac(16, 500), [S, B, X, T]).models if m.tag == "t:q")
    assert o.fit == "no"  # 12.0 > 10.7
    o = next(m for m in advise(mac(19, 500), [S, B, X, T]).models if m.tag == "t:q")
    assert o.fit == "tight"
    assert o.note == (
        "Fits in your 12.7 GB, but with little room to spare. "
        "Expect slow replies with other apps open."
    )


def test_advise_nothing_runs_well():
    a = advise(mac(8, 500), [S, B, X])  # usable 5.4; S needs 5.0 -> tight
    assert a.recommended is None and a.reason == "memory"
    assert len(a.tiers) == 3 and a.tiers[0].fit == "tight"
    assert "API key" in a.message


def test_advise_disk_short():
    a = advise(mac(24, 7.0), [S, B, X])  # B needs 6 + 2 headroom = 8
    assert a.recommended == "b:q" and a.reason == "disk"
    assert a.tiers[1].disk_short_gb == 1.0
    assert a.tiers[0].disk_short_gb is None
    assert "Free up 1 GB" in a.message


def test_device_labels_apple():
    d = advise(mac(24, 212), [S, B, X]).device
    assert (d.total_ram_gb, d.usable_gb, d.free_disk_gb) == (24, 16.1, 212)
    assert d.chip_label == "Apple M5"
    assert d.chip_note == "Shares memory with the graphics chip"


def test_device_labels_apple_unknown_chip():
    hw = HardwareInfo("macos", "arm64", 24, True, None, 100)
    assert advise(hw, [S, B, X]).device.chip_label == "Apple Silicon"


def test_device_labels_nvidia():
    hw = HardwareInfo("windows", "AMD64", 32, False, 12, 100, gpu_name="RTX 4070")
    d = advise(hw, [S, B, X]).device
    assert d.usable_gb == 16.0
    assert (d.chip_label, d.chip_note) == ("RTX 4070", "12 GB of graphics memory")
    hw = HardwareInfo("windows", "AMD64", 32, False, 12, 100)
    assert advise(hw, [S, B, X]).device.chip_label == "NVIDIA graphics card"


def test_device_labels_no_gpu():
    hw = HardwareInfo("windows", "AMD64", 16, False, None, 100)
    d = advise(hw, [S, B, X]).device
    assert d.chip_label == "No dedicated graphics card"
    assert d.chip_note == "AI runs on your processor, which is slower"


def test_est_minutes():
    # ceil(6*1024/10/60)
    assert advise(mac(24, 500), [S, B, X]).tiers[1].est_minutes == 11


def test_real_catalog_shape():
    tiers = {m.tier: m.name for m in MODEL_CATALOG if m.tier}
    assert tiers == {
        "small": "qwen3.5:4b",
        "balanced": "qwen3.5:9b",
        "best": "qwen3.8:27b",
    }
    assert all(m.tag.endswith("q4_K_M") for m in MODEL_CATALOG)
    assert all(m.max_context >= 2 * CONTEXT_TOKENS for m in MODEL_CATALOG)
    assert all(m.context_tokens == CONTEXT_TOKENS for m in MODEL_CATALOG)
    assert all(len(m.blurb) <= 90 for m in MODEL_CATALOG)
    assert find_model("qwen3:14b") is None
    assert find_model("qwen3.5:9b-q4_K_M").name == "qwen3.5:9b"
    assert advise(mac(24, 500)).recommended == "qwen3.5:9b-q4_K_M"
