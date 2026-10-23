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
    chip: str | None = None  # macOS CPU brand string, e.g. "Apple M5"
    gpu_name: str | None = None  # NVIDIA only


def ollama_models_dir() -> Path:
    env = os.environ.get("OLLAMA_MODELS")
    return Path(env) if env else Path.home() / ".ollama" / "models"


def _no_window_flags() -> int:
    # The engine runs windowless; don't flash a console on Windows.
    return CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _nvidia_gpu() -> tuple[str, float] | None:
    """(name, VRAM in GB) of the largest NVIDIA GPU, via nvidia-smi."""
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
            creationflags=_no_window_flags(),
        ).stdout
        # One line per GPU: "<name>, <MiB>"; use the largest.
        gpus = []
        for line in out.splitlines():
            if line.strip():
                name, _, mib = line.rpartition(",")
                gpus.append((name.strip(), float(mib) / 1024))
        return max(gpus, key=lambda g: g[1])
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _mac_chip() -> str | None:
    try:
        out = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        ).stdout.strip()
        return out or None
    except (OSError, subprocess.SubprocessError):
        return None


def free_disk_gb(models_dir: Path) -> float:
    """Free space on the volume that holds (or will hold) the models dir."""
    disk_path = models_dir if models_dir.exists() else Path.home()
    return round(shutil.disk_usage(disk_path).free / GB, 1)


def detect_hardware(models_dir: Path) -> HardwareInfo:
    system = platform.system()
    os_name = {"Darwin": "macos", "Windows": "windows"}.get(system, "other")
    arch = platform.machine()
    gpu = _nvidia_gpu()
    return HardwareInfo(
        os=os_name,
        arch=arch,
        total_ram_gb=round(psutil.virtual_memory().total / GB, 1),
        apple_silicon=os_name == "macos" and arch == "arm64",
        gpu_vram_gb=gpu[1] if gpu else None,
        free_disk_gb=free_disk_gb(models_dir),
        chip=_mac_chip() if os_name == "macos" else None,
        gpu_name=gpu[0] if gpu else None,
    )


def has_usable_gpu(hw: HardwareInfo) -> bool:
    return hw.gpu_vram_gb is not None and hw.gpu_vram_gb >= MIN_NVIDIA_VRAM_GB


def usable_memory_gb(hw: HardwareInfo) -> float:
    """Memory a model can use on this device, by platform rule."""
    if hw.apple_silicon:
        return round(0.67 * hw.total_ram_gb, 1)
    if has_usable_gpu(hw):
        return round(0.9 * (hw.gpu_vram_gb or 0), 1)
    return round(0.5 * hw.total_ram_gb, 1)
