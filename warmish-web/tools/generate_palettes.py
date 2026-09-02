"""Precompute the 36 Warmish palettes as 256x3 byte LUTs.

Build-time only: run once whenever constants.PALETTE_MAP changes, and check the
generated file in. The web app has no runtime dependency on matplotlib.

    python3 warmish-web/tools/generate_palettes.py
"""
import base64
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
from constants import PALETTE_MAP  # noqa: E402

OUT = REPO / "warmish-web" / "src" / "core" / "palettes.json"


def main() -> None:
    # matplotlib maps a float in [0, 1] to index int(x * 256), clamped to 255.
    # Sampling at bin centres reproduces that mapping exactly.
    xs = (np.arange(256) + 0.5) / 256.0
    palettes = {}
    for name, cmap in PALETTE_MAP.items():
        rgba = cmap(xs)
        lut = (rgba[:, :3] * 255).astype(np.uint8)
        palettes[name] = base64.b64encode(lut.tobytes()).decode("ascii")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(palettes, indent=0, sort_keys=False))
    print(f"Wrote {len(palettes)} palettes -> {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
