

---

<div align="center">
  <img src="Warmish Logo.png" alt="Warmish Logo" width="250">
  <p><em>Professional GUI application for thermal image analysis and visualization</em></p>
</div>
**Warmish** is a cross-platform graphical tool for analyzing radiometric thermal images (FLIR JPEG). It allows you to extract metadata, derive the temperature matrix, visualize thermal maps with customizable palettes, and work in overlay with the visible image. The interface is based on PySide6 (Qt) and includes interactive controls for zoom/pan, color legend, and calculation parameters.

---

## Key Features

- **Radiometric FLIR JPEG Loading**
  - Extraction of the thermal component (RawThermalImage) and FLIR/EXIF metadata via ExifTool.
  - Handling of RawThermalImage in PNG format with endianness correction (byteswap).

- **Metadata Extraction (ExifTool)**
  - Full metadata reading in JSON format, with complete display for verification and debugging.
  - Key parameters read and pre-filled: `Emissivity`, `ObjectDistance`, `ReflectedApparentTemperature`, `PlanckR1`, `PlanckR2`, `PlanckB`, `PlanckF`, `PlanckO`.
  - Automatic reading and application of overlay alignment metadata: `Real2IR`, `OffsetX`, `OffsetY`.

- **Pixel-level Temperature Calculation**
  - Derivation of the temperature matrix (°C) from radiometric data using Planck parameters and emissivity.
  - Dynamic update when calculation parameters are modified.

- **Advanced Thermal Visualization**
  - Temperature color map with always visible legend (dedicated ColorBarLegend widget, configurable ticks and min/max values).
  - Palette selection and **inversion** with a single click.

- **Available Palettes**
  - Iron (Inferno), Rainbow (nipy_spectral), Grayscale, Lava (hot), Arctic (cool), Glowbow (gist_rainbow), Amber (YlOrBr), Sepia (copper), Plasma, Viridis, Magma, Cividis, Turbo, Ocean, Terrain, Jet, Fire (afmhot), Ice (winter), Spring, Summer, Autumn, Bone, Pink, Coolwarm, RdYlBu, Spectral, BrBG, PiYG, PRGn, RdBu, RdGy, Purples, Blues, Greens, Oranges, Reds.

- **Overlay with Visible Image**
  - Extraction of the embedded visible image (EmbeddedImage), if present.
  - Toolbar controls: activate overlay, opacity, IR↔Visible scale (Real2IR), X/Y offset, blending mode (Normal, Multiply, Screen, Overlay, Darken, Lighten, ColorDodge, ColorBurn, Soft/Hard Light, Difference, Exclusion, Additive).
  - “Reset Alignment” button to restore Scale/Offset from metadata.

- **Interaction**
  - Zoom in/out and reset zoom.
  - Pan by dragging.
  - Temperature tooltip on mouse hover (°C) over the thermal image.

- **Structured UI**
  - Toolbar with main actions and palette/overlay/zoom controls.
  - Image area with thermal map and, in non-overlay mode, a separate panel for the visible image.
  - Always visible temperature legend on the side.
  - Tabbed sidebar:
    - Parameters: calculation parameters editing form + JSON metadata panel.
    - Areas & Analysis: “Spot / Rectangle / Polygon” buttons (placeholder for ROI).
    - Batch & Export: section with export options (PNG/CSV/PDF/RAW) and batch (placeholder).

---

## Project Structure

- `main.py` — application startup (creates `QApplication`, shows the main window).
- `ui/main_window.py` — main window “ThermalAnalyzerNG”: image loading, metadata extraction, temperature calculation, thermal visualization, overlay, zoom/pan, toolbar and tabs.
- `ui/widgets/color_bar_legend.py` — color legend widget (ColorBarLegend) with configurable palette, ticks, orientation, and precision.
- `constants.py` — mapping of palette names → Matplotlib colormaps.

Note: If the files are in different locations in your repository, make sure to update imports consistently (the code uses relative imports like `from .widgets.color_bar_legend import ColorBarLegend` in `ui/main_window.py`).

---

## Technical Requirements

- **Language**: Python 3 (developed and tested with Python 3.13.5)
- **GUI**: PySide6 (Qt for Python)
- **Processing**: numpy, Pillow (PIL)
- **Colors**: matplotlib
- **Metadata**: ExifTool (system tool) + Python `exiftool` binding
- **Platforms**: macOS, Windows (including Windows 11), Linux

---

## Installation

### 1) Prerequisites

- Python 3 (3.13.5 recommended).
- ExifTool installed and accessible in PATH:
  - Official website: [ExifTool](https://exiftool.org)
  - macOS: You can use the “MacOS Package: ExifTool-13.33.pkg” (confirmed installed). After installation, verify with:
    - `exiftool -ver`
  - Windows 11: Install ExifTool and ensure the `exiftool` command is available in Command Prompt/PowerShell (verify with `exiftool -ver`).

### 2) Python Dependencies

Install the required libraries:

```bash
pip install PySide6 exiftool numpy pillow matplotlib
```

### 3) Cloning and Environment Setup

```bash
git clone https://github.com/yourusername/warmish.git
cd warmish
```

Optional: Virtual environment
- macOS/Linux:
  ```bash
  python -m venv .venv
  source .venv/bin/activate
  ```
- Windows 11 (PowerShell):
  ```powershell
  py -m venv .venv
  .\.venv\Scripts\Activate.ps1
  ```

---

## Running the Application

Launch the application:

```bash
python main.py
```

Typical workflow:
1. Click “Load Image” and select a radiometric FLIR JPEG.
2. The app extracts metadata and thermal data. The thermal map is displayed with a legend.
3. Hover your mouse over the thermal image to read the pixel temperature (tooltip).
4. Adjust parameters (emissivity, Planck constants, etc.) in the “Parameters” tab and observe the update.
5. Change palettes or invert the palette from the toolbar; the legend updates.
6. Optional: Activate “Overlay” to superimpose the thermal image on the visible one; adjust opacity, scale (Real2IR), and X/Y offset; try various blending modes; use “Reset Alignment” to restore metadata values.
7. Use Zoom +/– and pan to explore details.

---

## Implementation Notes

- RawThermalImage extraction via ExifTool (`-b -RawThermalImage`). If the thermal image is PNG, `byteswap` is performed for endianness before calculation.
- The overlay scale is initialized from metadata (`Real2IR`), as are the offsets (`OffsetX`, `OffsetY`). Controls allow manual override.
- ColorBarLegend manages orientation, ticks, numeric format, and units (°C).

---

## Troubleshooting

- “ExifTool not found”:
  - Verify installation (`exiftool -ver`) and PATH.
  - On Windows 11, restart the terminal after installation to update PATH.

- “No visible image found”:
  - Not all files have `EmbeddedImage`. Overlay requires the embedded visible image.

- Incorrect/NaN temperatures:
  - Check emissivity and Planck parameters in metadata.
  - For PNG thermal images, `byteswap` correction is already applied; if the file is not PNG, ensure radiometric width/height are read from metadata.

- Zoom/pan glitches or inconsistent behavior:
  - Use “Reset Zoom”.
  - Some refinements are in progress (see Limitations/Roadmap).

---

## Known Limitations (current state)

- The ROI buttons (Spot/Rectangle/Polygon) are placeholders: measurement/area analysis tools are not yet implemented.
- Export actions (PNG/CSV/PDF/RAW) are present in the UI but not yet operational.
- Automatic overlay alignment (automatic search for offset/scale) is not yet implemented; currently, metadata and manual controls are used.
- Some details of stability/robustness and UI refinement (incremental zoom, event handler naming, minor syntactic corrections) are in progress.

---

## Roadmap

1. Quality and Bug Fixes
   - Syntactic corrections, imports, and spacing; unification of handler names (e.g., `image_mouse_move_event`).
   - Correct incremental zoom (multiplicative), panning refinement, and size management.
   - Better error handling and user messages.

2. Performance and Architecture
   - Separation of temperature recalculation vs. recoloring only (caching of `temperature_data` and normalization).
   - Improved rendering pipeline and reduction of redraws.

3. Rendering/UX
   - Migration to `QGraphicsView/QGraphicsScene` for fluid zoom/pan and composite overlay.
   - Status bar with global min/max and value under cursor.

4. Overlay
   - Automatic alignment (correlation on grayscale visible image).
   - Better scale/offset synchronization with metadata and preset saving.

5. ROI and Analysis
   - Spot/Rectangle/Polygon tools with statistics (min/max/avg, histograms).
   - ROI overlay and results tab.

6. Export
   - Export of colorized thermal image (PNG) with/without legend.
   - Data export (CSV) and reports (PDF) with parameter/ROI summary.
   - Export of raw/temperature data (NPZ/TIFF/RAW) for external processing.

7. Validation and Defaults
   - Input parameter validation (emissivity range, plausible temperatures).
   - Robust default values and quick reset.

8. Testing and CI
   - Unit tests for temperature calculation and metadata parsing.
   - Example dataset and golden tests.
   - CI pipeline.

9. Packaging
   - Distributions for macOS and Windows 11 with runtime ExifTool detection and clear instructions for the end-user.

10. Documentation
    - User manual with screenshots, overlay guide, and best practices.
    - Use case examples and demonstration datasets.

---

## ExifTool Installation (note)

- Official website: [ExifTool](https://exiftool.org)
- macOS: Installation confirmed via “MacOS Package: ExifTool-13.33.pkg (5.4 MB)”.
- Windows 11: Install ExifTool and verify with `exiftool -ver`. Ensure the command is available in your terminal.

---

## License

Distributed under GNU GPLv3. See `LICENSE`.

---

## Contributing

Issues and pull requests are welcome. Please clearly indicate:
- Example input file (if possible).
- Operating system (e.g., Windows 11, macOS).
- Python version and output of `exiftool -ver`.

---
