"""Dump the desktop app's own output for a FLIR image, as Phase-0 ground truth.

Drives the real `core.thermal_engine.ThermalEngine` (ExifTool + numpy path),
so the comparison is against the shipping implementation, not a reimplementation.

    python3 warmish-web/tests/python_reference.py <image.jpg> <out.json>
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
os.chdir(REPO)

import numpy as np  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

import desktop_engine_shim  # noqa: E402, F401  (swaps in a working exiftool)
from core.thermal_engine import ThermalEngine  # noqa: E402


def main() -> None:
    src, dst = sys.argv[1], sys.argv[2]
    _app = QGuiApplication.instance() or QGuiApplication([])

    engine = ThermalEngine()
    if not engine.load_thermal_image(src):
        raise SystemExit(f"desktop engine failed to load {src}")

    params = engine.get_thermal_parameters_from_metadata()
    if not engine.calculate_temperatures(params):
        raise SystemExit("desktop engine failed to compute temperatures")

    temps = engine.temperature_data.astype(np.float64)
    raw = np.asarray(engine.thermal_data, dtype=np.uint16)

    # Colorized pixels straight from create_colored_pixmap's own math, so the
    # precomputed LUTs and the index arithmetic are validated too.
    from constants import PALETTE_MAP

    span = (engine.temp_max - engine.temp_min) or 1
    norm = np.nan_to_num((temps - engine.temp_min) / span)
    colors = {}
    idx = list(range(0, temps.size, max(1, temps.size // 40)))
    for pal in ("Iron", "Rainbow", "Viridis", "Grayscale", "Turbo"):
        rgb = (PALETTE_MAP[pal](norm.flat[idx])[:, :3] * 255).astype(np.uint8)
        colors[pal] = rgb.tolist()

    Path(dst).write_bytes(
        json.dumps(
            {
                "colorIndices": idx,
                "colors": colors,
                "parameters": {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in params.items()},
                # Overlay alignment the desktop derives from Real2IR / OffsetX / OffsetY.
                "overlay": {k: float(v) for k, v in engine.get_overlay_parameters_from_metadata().items()},
                "width": int(raw.shape[1]),
                "height": int(raw.shape[0]),
                "rawChecksum": int(raw.astype(np.uint64).sum()),
                "tempMin": float(np.nanmin(temps)),
                "tempMax": float(np.nanmax(temps)),
                "tempMean": float(np.nanmean(temps)),
                # A deterministic scatter of pixels, for element-wise comparison.
                "samples": [
                    {"i": int(i), "t": (None if np.isnan(temps.flat[i]) else float(temps.flat[i]))}
                    for i in range(0, temps.size, max(1, temps.size // 500))
                ],
            }
        ).encode()
    )
    print(f"reference written: {dst}")


if __name__ == "__main__":
    main()
