import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import psutil

GB = 1024**3
MIN_NVIDIA_VRAM_GB = 6
# subprocess.CREATE_NO_WINDOW only exists on Windows builds of Python.
CREATE_NO_WINDOW = 0x08000000


@dataclass
class HardwareInfo:
    os: Literal["macos", "windows", "other"]
    arch: str
    total_ram_gb: float
    apple_silicon: bool
    gpu_vram_gb: float | None  # NVIDIA only, via nvidia-smi; None otherwise
    free_disk_gb: float  # on the volume holding the Ollama models dir


def ollama_models_dir() -> Path:
    env = os.environ.get("OLLAMA_MODELS")
    return Path(env) if env else Path.home() / ".ollama" / "models"


def _nvidia_vram_gb() -> float | None:
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
            # The engine runs windowless; don't flash a console on Windows.
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        ).stdout
        # One line per GPU, in MiB; use the largest.
        return max(float(line) for line in out.split() if line) / 1024
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def free_disk_gb(models_dir: Path) -> float:
    """Free space on the volume that holds (or will hold) the models dir."""
    disk_path = models_dir if models_dir.exists() else Path.home()
    return round(shutil.disk_usage(disk_path).free / GB, 1)


def detect_hardware(models_dir: Path) -> HardwareInfo:
    system = platform.system()
    os_name = {"Darwin": "macos", "Windows": "windows"}.get(system, "other")
    arch = platform.machine()
    return HardwareInfo(
        os=os_name,
        arch=arch,
        total_ram_gb=round(psutil.virtual_memory().total / GB, 1),
        apple_silicon=os_name == "macos" and arch == "arm64",
        gpu_vram_gb=_nvidia_vram_gb(),
        free_disk_gb=free_disk_gb(models_dir),
    )


def memory_budget_gb(hw: HardwareInfo) -> float:
    """Memory available for model weights, by platform rule."""
    if hw.apple_silicon:
        return round(0.70 * hw.total_ram_gb, 2)
    if hw.gpu_vram_gb is not None and hw.gpu_vram_gb >= MIN_NVIDIA_VRAM_GB:
        return round(0.9 * hw.gpu_vram_gb, 2)
    return round(0.5 * hw.total_ram_gb, 2)
