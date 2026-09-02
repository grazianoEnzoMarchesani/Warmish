"""Dump the desktop app's own ROI statistics, as Phase-3 ground truth.

Drives the real `core.roi_controller.ROIController` against the real
`ThermalEngine`, so masks, per-ROI emissivity and the statistics all come from
the shipping implementation.

    python3 warmish-web/tests/python_roi_reference.py <image.jpg> <rois.json> <out.json>
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
from core.roi_controller import ROIController  # noqa: E402
from core.thermal_engine import ThermalEngine  # noqa: E402


def main() -> None:
    src, roi_src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    _app = QGuiApplication.instance() or QGuiApplication([])

    engine = ThermalEngine()
    if not engine.load_thermal_image(src):
        raise SystemExit(f"desktop engine failed to load {src}")
    if not engine.calculate_temperatures(engine.get_thermal_parameters_from_metadata()):
        raise SystemExit("desktop engine failed to compute temperatures")

    controller = ROIController(engine)
    controller.import_roi_data(json.loads(Path(roi_src).read_text()))

    out = []
    for roi in controller.get_all_rois():
        mask = controller._create_roi_mask(roi)
        out.append(
            {
                "name": roi.name,
                "type": type(roi).__name__,
                "emissivity": roi.emissivity,
                "pixels": int(np.sum(mask)) if mask is not None else 0,
                "min": roi.temp_min,
                "max": roi.temp_max,
                "mean": roi.temp_mean,
                "median": getattr(roi, "temp_median", None),
                "std": roi.temp_std,
                # A checksum of the mask itself, so a geometry mismatch is caught
                # even when it happens to leave the statistics unchanged.
                "maskChecksum": int(np.flatnonzero(mask).sum()) if mask is not None else 0,
            }
        )

    Path(dst).write_bytes(json.dumps({"rois": out}, indent=2).encode())
    print(f"ROI reference written: {dst}")


if __name__ == "__main__":
    main()
