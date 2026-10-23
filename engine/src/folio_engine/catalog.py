import math
from dataclasses import dataclass
from typing import Literal

from .hardware import HardwareInfo, has_usable_gpu, usable_memory_gb

CONTEXT_TOKENS = 16384  # one context size for every model, everywhere
HEADROOM = 0.20  # recommended memory = needed memory x 1.20
DISK_HEADROOM_GB = 2.0
DOWNLOAD_MB_PER_S = 10
# Minimum specs from the README. Below them every model is at best a tight
# fit, so Folio recommends nothing and warns before a download.
MIN_RAM_GB = 16
MIN_VRAM_GB = 8

Tier = Literal["small", "balanced", "best"]
Fit = Literal["ok", "tight", "no"]


@dataclass(frozen=True)
class CatalogModel:
    tag: str  # Ollama tag
    name: str  # short name shown to the user
    maker: str
    download_gb: float
    needed_gb: float  # memory needed to run at CONTEXT_TOKENS
    thinking: bool
    blurb: str
    tier: Tier | None = None
    max_context: int = 131072

    @property
    def recommended_gb(self) -> float:
        return round(self.needed_gb * (1 + HEADROOM), 1)

    @property
    def context_tokens(self) -> int:
        return min(CONTEXT_TOKENS, self.max_context)


def _m(
    tag: str,
    name: str,
    maker: str,
    download_gb: float,
    needed_gb: float,
    thinking: bool,
    blurb: str,
    tier: Tier | None = None,
    max_context: int = 262144,
) -> CatalogModel:
    return CatalogModel(
        tag, name, maker, download_gb, needed_gb, thinking, blurb, tier, max_context
    )


# The three tier models were measured with scripts/measure_models.py (Apple M5,
# 24 GB, 2026-10-23). The rest are calculated and err high, which is the safe
# direction; see docs/superpowers/specs/2026-10-22-model-research.md.
MODEL_CATALOG: list[CatalogModel] = [
    _m("qwen3.5:4b-q4_K_M", "qwen3.5:4b", "Alibaba", 3.3, 3.4, True,
       "Small and quick. Fine for simple edits on modest computers.", "small"),
    _m("qwen3:4b-instruct-2507-q4_K_M", "qwen3:4b-instruct", "Alibaba", 2.5, 5.9, False,
       "Small and fast. Answers directly without a long thinking step."),
    _m("gemma4:e4b-it-q4_K_M", "gemma4:e4b", "Google", 6.6, 8.4, True,
       "Google's compact model. A good fit for everyday resume edits.", None, 131072),
    _m("qwen3.5:9b-q4_K_M", "qwen3.5:9b", "Alibaba", 6.6, 5.0, True,
       "A strong all-rounder. Good bullets without needing a powerful computer.", "balanced"),
    _m("gemma4:12b-it-q4_K_M", "gemma4:12b", "Google", 8.0, 10.3, True,
       "Google's mid-size model. May write more natural-sounding bullets."),
    _m("ministral-3:14b-instruct-2512-q4_K_M", "ministral-3:14b", "Mistral", 9.1, 12.8, False,
       "Mistral's mid-size model. Clear, direct writing."),
    _m("mistral-small3.2:24b-instruct-2506-q4_K_M", "mistral-small3.2:24b", "Mistral", 15, 18.7, False,
       "A large Mistral model. Polished writing; needs a powerful computer.", None, 131072),
    _m("qwen3.5:27b-q4_K_M", "qwen3.5:27b", "Alibaba", 17, 19.7, True,
       "A large model with careful reasoning. Needs plenty of memory."),
    _m("gemma4:26b-a4b-it-q4_K_M", "gemma4:26b-a4b", "Google", 18, 20.2, True,
       "A large Google model that stays fairly quick. Needs plenty of memory."),
    _m("qwen3.8:27b-q4_K_M", "qwen3.8:27b", "Alibaba", 18, 17.2, True,
       "Our top pick for quality. Needs a powerful computer.", "best"),
    _m("gemma4:31b-it-q4_K_M", "gemma4:31b", "Google", 20, 24.1, True,
       "Google's largest model here. Very capable; needs lots of memory."),
    _m("qwen3.6:35b-a3b-q4_K_M", "qwen3.6:35b-a3b", "Alibaba", 24, 25.9, True,
       "The biggest model on the list. Only for computers with lots of memory."),
]  # fmt: skip


def find_model(tag: str) -> CatalogModel | None:
    return next((m for m in MODEL_CATALOG if m.tag == tag), None)


def below_minimum(hw: HardwareInfo) -> bool:
    if not hw.apple_silicon and (hw.gpu_vram_gb or 0) >= MIN_VRAM_GB:
        return False
    # Computers sold as 16 GB can report a little less.
    return hw.total_ram_gb < MIN_RAM_GB * 0.9


def fit(model: CatalogModel, usable_gb: float) -> Fit:
    if usable_gb >= model.recommended_gb:
        return "ok"
    if usable_gb >= model.needed_gb:
        return "tight"
    return "no"


@dataclass
class Device:
    total_ram_gb: float
    usable_gb: float
    free_disk_gb: float
    chip_label: str
    chip_note: str


@dataclass
class ModelOption:
    tag: str
    name: str
    maker: str
    blurb: str
    tier: Tier | None
    download_gb: float
    needed_gb: float
    recommended_gb: float
    est_minutes: int
    fit: Fit
    note: str
    disk_short_gb: float | None


@dataclass
class Advice:
    device: Device
    recommended: str | None
    reason: Literal["ok", "memory", "disk"]
    message: str
    tiers: list[ModelOption]
    models: list[ModelOption]


def _device(hw: HardwareInfo, usable: float) -> Device:
    if hw.apple_silicon:
        label = hw.chip or "Apple Silicon"
        note = "Shares memory with the graphics chip"
    elif has_usable_gpu(hw):
        label = hw.gpu_name or "NVIDIA graphics card"
        note = f"{hw.gpu_vram_gb:g} GB of graphics memory"
    else:
        label = "No dedicated graphics card"
        note = "AI runs on your processor, which is slower"
    return Device(hw.total_ram_gb, usable, hw.free_disk_gb, label, note)


def _note(
    m: CatalogModel, f: Fit, usable: float, rec: CatalogModel | None, cpu_only: bool
) -> str:
    if rec is not None and m.tag == rec.tag:
        return (
            f"Why: it needs about {m.needed_gb:g} GB and your device has "
            f"{usable:g} GB usable, so it runs smoothly with room to spare."
        )
    if f == "ok":
        if rec is not None and m.needed_gb < rec.needed_gb:
            return (
                "Faster, but writes noticeably weaker bullets. "
                "Your device can do better."
            )
        if cpu_only and rec is not None:
            return (
                f"Fits in your {usable:g} GB, but replies will be slow "
                "without a graphics card."
            )
        return f"Runs smoothly: needs about {m.needed_gb:g} GB of your {usable:g} GB."
    if f == "tight":
        return (
            f"Fits in your {usable:g} GB, but with little room to spare. "
            "Expect slow replies with other apps open."
        )
    return (
        f"Needs about {m.needed_gb:g} GB, more than your {usable:g} GB. "
        "It would be very slow or fail to load."
    )


def _disk_short(m: CatalogModel, free_disk_gb: float) -> float | None:
    short = round(m.download_gb + DISK_HEADROOM_GB - free_disk_gb, 1)
    return short if short > 0 else None


def advise(hw: HardwareInfo, catalog: list[CatalogModel] = MODEL_CATALOG) -> Advice:
    usable = usable_memory_gb(hw)
    tier_order: list[Tier] = ["small", "balanced", "best"]
    tier_models = [next(m for m in catalog if m.tier == t) for t in tier_order]
    low_spec = below_minimum(hw)
    # Without a graphics card a bigger model fits in memory but is too slow
    # on a long resume prompt, so only Small is ever recommended.
    cpu_only = not hw.apple_silicon and not has_usable_gpu(hw)

    def fit_on_device(m: CatalogModel) -> Fit:
        f = fit(m, usable)
        return "tight" if low_spec and f == "ok" else f

    candidates = tier_models[:1] if cpu_only else tier_models
    ok_tiers = [m for m in candidates if fit_on_device(m) == "ok"]
    rec = max(ok_tiers, key=lambda m: m.needed_gb) if ok_tiers else None

    def option(m: CatalogModel) -> ModelOption:
        f = fit_on_device(m)
        return ModelOption(
            tag=m.tag,
            name=m.name,
            maker=m.maker,
            blurb=m.blurb,
            tier=m.tier,
            download_gb=m.download_gb,
            needed_gb=m.needed_gb,
            recommended_gb=m.recommended_gb,
            est_minutes=math.ceil(m.download_gb * 1024 / DOWNLOAD_MB_PER_S / 60),
            fit=f,
            note=_note(m, f, usable, rec, cpu_only),
            disk_short_gb=_disk_short(m, hw.free_disk_gb),
        )

    if rec is None:
        reason: Literal["ok", "memory", "disk"] = "memory"
        message = (
            "None of Folio's models will run smoothly on this device. "
            "You can use your own API key instead, or pick a model below anyway."
        )
    else:
        short = _disk_short(rec, hw.free_disk_gb)
        if short is None:
            reason = "ok"
            message = f"We recommend {rec.name} for your device."
        else:
            reason = "disk"
            need = rec.download_gb + DISK_HEADROOM_GB
            message = (
                f"The recommended model needs about {need:g} GB of free disk "
                f"space. Free up {short:g} GB, or pick a smaller model."
            )
    return Advice(
        device=_device(hw, usable),
        recommended=rec.tag if rec else None,
        reason=reason,
        message=message,
        tiers=[option(m) for m in tier_models],
        models=[option(m) for m in sorted(catalog, key=lambda m: m.needed_gb)],
    )
