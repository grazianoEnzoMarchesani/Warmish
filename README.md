<div align="center">
  <img src="Warmish Logo.svg" alt="Warmish Logo" width="250">
  <p><em>Professional GUI application for thermal image analysis and visualization</em></p>
</div>

**Warmish** is a cross-platform graphical tool for the advanced analysis of radiometric thermal images (FLIR JPEG). Built on a modern architecture with `QGraphicsView`, it allows you to extract metadata, calculate temperature matrices, visualize thermal maps with customizable palettes, and work with a visible image overlay. The interface, developed in PySide6, offers interactive controls for synchronized zoom/pan, a dynamic legend, and a powerful **Region of Interest (ROI) analysis** system with real-time statistics.

---

### ✨ **Current Version Highlights**

*   **Advanced Graphics Architecture:** Fully migrated to `QGraphicsView` and `QGraphicsScene`, ensuring fluid zooming, responsive panning, and optimal management of graphical objects.
*   **Comprehensive ROI Analysis:** Implemented tools to create **Rectangles, Spots (circles), and Polygons**. ROIs are fully interactive: they can be moved, resized via control handles, and edited (vertex editing for polygons).
*   **Real-time Statistics:** A dedicated table displays statistics (min, max, mean, median) for each ROI, updating automatically with every modification.
*   **Automatic Session Saving:** All settings, including ROIs, calculation parameters, and display configurations, are saved to a `.json` file associated with the image, allowing you to resume your work exactly where you left off.
*   **Synchronized Dual View:** When not in overlay mode, the application displays the thermal and visible images in two separate, perfectly synchronized panels for zoom and pan.

---
 Live Demo on YouTube
See Warmish in action! This video demonstrates the fluid workflow, from loading an image to performing advanced ROI analysis. Click the preview below to watch:
<a href="https://youtu.be/qJgL65pQXTE" title="Watch the Demo on YouTube">
<img src="https://img.youtube.com/vi/qJgL65pQXTE/maxresdefault.jpg" alt="Warmish Demo on YouTube" style="width:100%;">
</a>
---

## Key Features

- **Radiometric Image Loading (FLIR JPEG)**
  - Extraction of the thermal component (`RawThermalImage`) and FLIR/EXIF metadata via ExifTool.
  - Handling of `RawThermalImage` in PNG format with endianness correction (`byteswap`).

- **Metadata Extraction (ExifTool)**
  - Full metadata reading in JSON format, with a complete display for verification.
  - Key parameters (`Emissivity`, `ObjectDistance`, `PlanckR1`, `PlanckR2`, etc.) are read and pre-filled.
  - Automatic reading and application of overlay alignment metadata (`Real2IR`, `OffsetX`, `OffsetY`).

- **Pixel-level Temperature Calculation**
  - Derivation of the temperature matrix (°C) from radiometric data using Planck parameters and emissivity.
  - Dynamic updates when calculation parameters are modified.

- **Advanced Thermal Visualization**
  - Temperature color map with an always-visible legend (`ColorBarLegend`), configurable for ticks, min/max, and precision.
  - Palette selection and **inversion** with a single click.

- **Available Palettes**
  - Iron (Inferno), Rainbow (nipy_spectral), Grayscale, Lava (hot), Arctic (cool), and many more (see `constants.py`).

- **Overlay with Visible Image (on `QGraphicsView`)**
  - Extraction and use of the embedded visible image (`EmbeddedImage`).
  - Toolbar controls: activate overlay, opacity, IR↔Visible scale (`Real2IR`), X/Y offset, and **blending modes** (Normal, Multiply, Screen, Overlay, etc.).
  - "Reset Alignment" button to restore values from metadata.

- **Fluid Interaction (`QGraphicsView`)**
  - Zoom in/out (also with Ctrl + scroll wheel) and zoom reset.
  - Pan by dragging (also with the middle mouse button).
  - Tooltip with pixel temperature (°C) on mouse hover over the thermal image.

- **Full ROI (Region of Interest) Analysis**
  - **Drawing Tools:** Dedicated buttons to create **Spots**, **Rectangles**, and **Polygons**.
  - **Interactive ROIs:**
    - Move with drag & drop.
    - Resize using intuitive control handles.
    - Edit vertices for polygons.
  - **Analysis Table:** A table view with name, emissivity (editable per-ROI), and calculated statistics (Min, Max, Mean, Median) for each area.
  - **On-Image Labels:** Customizable labels display statistics directly above each ROI.
  - **Synchronization:** Selecting an ROI in the table highlights it in the image, and vice-versa.

- **Automatic Save and Restore**
  - Changes to parameters, palette settings, overlay configuration, and **all created ROIs** are automatically saved to a `.json` file next to the loaded image.
  - Reopening the same image restores the entire analysis session.

- **Structured UI**
  - Toolbar with main actions, palette, overlay, and zoom controls.
  - Image area with a **synchronized dual view** (thermal and visible) or a single view in overlay mode.
  - Always-visible temperature legend on the side.
  - Tabbed sidebar:
    - **Parameters:** Calculation parameter editing form + JSON metadata panel.
    - **Areas & Analysis:** Drawing tools, ROI analysis table, and label display controls.
    - **Batch & Export:** Section with export options (placeholder).

---

## Project Structure

- `main.py` — Application startup, splash screen management, and main window creation.
- `ui/main_window.py` — `ThermalAnalyzerNG` main window: orchestrates all features, from loading to ROI analysis and auto-saving.
- **`ui/image_graphics_view.py`** — `ImageGraphicsView`, the core of the visualization. Manages zoom/pan, overlay, and interactive ROI drawing.
- **`analysis/roi_models.py`** — Defines the model classes for ROI data (`RectROI`, `SpotROI`, `PolygonROI`).
- **`ui/roi_items.py`** — Defines the graphical objects (`QGraphicsItem`) that represent ROIs in the scene, handling their interactivity (moving, resizing).
- `ui/widgets/color_bar_legend.py` — The color legend widget.
- `constants.py` — Maps palette names to Matplotlib colormaps.

---

## Technical Requirements

- **Language**: Python 3 (developed and tested with Python 3.13+)
- **GUI**: PySide6 (Qt for Python)
- **Processing**: numpy, Pillow (PIL)
- **Colors**: matplotlib
- **Metadata**: ExifTool (system tool) + `exiftool` Python binding
- **Platforms**: macOS, Windows (including Windows 11), Linux

---

## Installation

### 1) Prerequisites

- **Python 3** (3.13.5 or newer recommended).
- **ExifTool** installed and accessible in the system `PATH`.
  - Official website: [ExifTool](https://exiftool.org)
  - Verify the installation with the command: `exiftool -ver`

### 2) Python Dependencies

Clone the repository and install the required libraries using the `requirements.txt` file. Using a virtual environment is highly recommended.

```bash
git clone https://github.com/yourusername/warmish.git
cd warmish

# Optional: create and activate a virtual environment
# python -m venv .venv
# source .venv/bin/activate  (on macOS/Linux)
# .\.venv\Scripts\Activate.ps1 (on Windows PowerShell)

# Install dependencies
pip install -r requirements.txt
```

---

## Running the Application

Launch the application with:

```bash
python main.py
```

**Typical workflow:**
1.  Click "Load Image" and select a radiometric JPEG file.
2.  The app extracts metadata and thermal data. The thermal and visible views are displayed. If a `.json` file exists, the previous session (ROIs, parameters) is loaded.
3.  Use the tools in the "Areas & Analysis" tab to draw **Spots, Rectangles, or Polygons** on the thermal image.
4.  Watch the statistics appear in the table and move/resize the ROIs: the data will update in real-time.
5.  Modify the emissivity for a single ROI directly in the table to refine the analysis.
6.  Activate "Overlay" to superimpose the images; adjust opacity, scale, offset, and blending mode.
7.  Use zoom and pan to explore details; the views (if separate) will remain synchronized.
8.  All changes are saved automatically.

---

## Known Limitations (Current State)

- The **Export** (PNG/CSV/PDF) and **Batch Processing** actions are present in the UI but not yet operational.
- Automatic overlay alignment (searching for offset/scale via correlation) is not yet implemented; metadata and manual controls are used.
- While the ROI features are robust, refinements to usability and edge-case handling are ongoing.

---

## Roadmap

The roadmap is constantly evolving. Many of the initial goals have already been achieved and surpassed. The next priorities include:

1.  **Exporting and Reporting:**
    - Export the rendered thermal image (PNG) with or without overlays and legends.
    - Export analysis data (CSV) with ROI statistics.
    - Create reports (PDF) that summarize the analysis, parameters, and images.

2.  **UI/UX Improvements:**
    - A status bar with global information (image min/max, temperature under the cursor).
    - The ability to group and manage ROIs (e.g., hide/show groups).
    - Saving alignment presets for the overlay.

3.  **Advanced Analysis Features:**
    - Temperature **histograms** for ROIs.
    - Additional measurement tools (e.g., line profiles).
    - Advanced input validation with user feedback.

4.  **Performance:**
    - Optimizing recalculation to separate statistics updates from rendering.
    - Intelligent data caching to improve responsiveness with many ROIs.

5.  **Packaging and Distribution:**
    - Creating executable packages for macOS and Windows 11 to simplify distribution to end-users.

---

## License

Distributed under the GNU GPLv3 License. See `LICENSE`.
