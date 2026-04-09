from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScanConfig:
    dpi: int = 300
    color_mode: str = "color"


def scan_from_device(output_dir: Path, config: ScanConfig) -> list[Path]:
    """
    Scan pages from a physical scanner.

    This function is intentionally implemented as an adapter point. Integrate
    your preferred backend here (WIA/TWAIN/SANE) based on deployment OS.
    """
    _ = output_dir
    _ = config
    raise NotImplementedError(
        "Physical scanner adapter is not configured. "
        "Integrate scan_from_device with your scanner backend."
    )
