import math
from dataclasses import dataclass
from typing import Literal

from .hardware import HardwareInfo, memory_budget_gb

DISK_HEADROOM_GB = 2.0
DOWNLOAD_MB_PER_S = 10


@dataclass(frozen=True)
class ModelTier:
    name: str  # Ollama tag
    size_gb: float  # download size
    min_budget_gb: float
    label: str  # plain-English name shown to user


# PROVISIONAL tiers. To be replaced after quality testing on the owner's
# resumes (spec section 6, "REVISIT LATER").
MODEL_CATALOG: list[ModelTier] = [
    ModelTier("qwen3:8b", 5.2, 7, "Standard"),
    ModelTier("qwen3:14b", 9.3, 12, "Enhanced"),
    ModelTier("qwen3:32b", 20, 24, "Maximum"),
]


@dataclass
class Recommendation:
    model: ModelTier | None
    reason: Literal["ok", "memory", "disk"]
    message: str  # plain English, shown verbatim in UI
    est_minutes: int | None
    free_disk_needed_gb: float | None


def recommend(
    hw: HardwareInfo, catalog: list[ModelTier] = MODEL_CATALOG
) -> Recommendation:
    budget = memory_budget_gb(hw)
    fitting = [m for m in catalog if m.min_budget_gb <= budget]
    if not fitting:
        return Recommendation(
            model=None,
            reason="memory",
            message=(
                "This computer doesn't have enough memory to run an AI model "
                "privately. You can use your own API key instead."
            ),
            est_minutes=None,
            free_disk_needed_gb=None,
        )
    best = max(fitting, key=lambda m: m.min_budget_gb)
    needed = best.size_gb + DISK_HEADROOM_GB
    if hw.free_disk_gb < needed:
        short = round(needed - hw.free_disk_gb, 1)
        return Recommendation(
            model=None,
            reason="disk",
            message=(
                f"The best model for this computer needs about {needed:g} GB "
                f"of free disk space. Free up {short:g} GB and try again."
            ),
            est_minutes=None,
            free_disk_needed_gb=short,
        )
    minutes = math.ceil(best.size_gb * 1024 / DOWNLOAD_MB_PER_S / 60)
    return Recommendation(
        model=best,
        reason="ok",
        message=(
            f"We recommend the {best.label} model ({best.size_gb:g} GB). "
            f"Download takes about {minutes} minutes."
        ),
        est_minutes=minutes,
        free_disk_needed_gb=None,
    )
