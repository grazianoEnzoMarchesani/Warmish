# Warmish

![Warmish Logo](Warmish%20logo.png "Warmish - Thermal Image Analyzer")

**Warmish** is a graphical, cross-platform thermal image analysis tool. It enables the extraction, processing, and visualization of radiometric metadata and temperature maps from FLIR thermal images. With an intuitive interface and robust computational backend, Warmish transforms raw data into clear thermal visualizations and provides interactive exploration of temperature information at the pixel level.

---

## Features

- **Open FLIR Thermal Images**: Load FLIR JPEG images and extract embedded radiometric data and metadata.
- **Robust Metadata Extraction**: Automatically parses and displays all available EXIF and FLIR-specific metadata using ExifTool.
- **Pixel-Level Temperature Mapping**: Calculates and visualizes temperature matrices from raw thermal data, accounting for physical parameters like emissivity and distance.
- **Customizable Analysis**: Edit temperature calculation parameters (emissivity, object distance, Planck constants, etc.) to match your scenario and immediately update results.
- **Thermal Visualization**: Displays a color-coded temperature map using the Inferno colormap, accompanied by a live temperature legend.
- **Interactive Tooltips**: Hover over the thermal image to view precise temperature values for each pixel.
- **Comprehensive Metadata Panel**: Full JSON display of all extracted metadata for transparency and debugging.
- **Responsive User Interface**: Built with PySide6 for a modern, resizable GUI layout and smooth user experience.
- **Error Handling**: Integrated checks and user-friendly notifications for unsupported files or data errors.

---

## Technical Overview

- **Language**: Python 3
- **Core Libraries**:
  - PySide6 (Qt for Python): GUI development
  - exiftool and exiftool Python bindings: Metadata extraction
  - numpy: Numeric and matrix operations
  - PIL (Pillow): Image processing
  - matplotlib: Color mapping for visualization
- **Platform**: Cross-platform (Linux, Windows, macOS)

---

## Installation

### Prerequisites

- Python 3.8+
- [ExifTool](https://exiftool.org/) installed and accessible from system PATH.

### Required Python Packages

Install dependencies via pip:

```bash
pip install PySide6 exiftool numpy pillow matplotlib
```

### Installation Steps

1. Clone this repository:
    ```bash
    git clone https://github.com/yourusername/warmish.git
    cd warmish
    ```

2. (Optional) Create a virtual environment for isolation:
    ```bash
    python -m venv venv
    source venv/bin/activate   # On Windows use: venv\Scripts\activate
    ```

3. Install dependencies as above.

---

## Usage

Run the application with:

```bash
python thermal_analyzer_ng.py
```

### Main Workflow

1. **Open** a FLIR JPEG image using the "Open FLIR Thermal Image" button.
2. Warmish extracts all metadata and radiometric data.
3. The thermal map and color legend appear. Hover on the image to see temperature tooltips.
4. Adjust analysis parameters in the dedicated panel as needed.
5. Inspect all metadata in the JSON viewer.

---

## GUI Overview

- **Left Panel**: Image display and controls (Open file, temperature tooltip on hover).
- **Right Panel**: Editable analysis parameters, dynamic temperature legend, full metadata display (JSON format).

---

## License

This project is licensed under the GNU General Public License v3.0 (GPLv3).  
See the [LICENSE](LICENSE) file for more details.

---

## Acknowledgements

- Uses ExifTool for robust metadata extraction.
- Based on the PySide6 Qt framework for Python.

---

## Contribution

Issues and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.


---

## Features

- **Open FLIR Thermal Images**: Load FLIR JPEG images and extract embedded radiometric data and metadata.
- **Robust Metadata Extraction**: Automatically parses and displays all available EXIF and FLIR-specific metadata using ExifTool.
- **Pixel-Level Temperature Mapping**: Calculates and visualizes temperature matrices from raw thermal data, accounting for physical parameters like emissivity and distance.
- **Customizable Analysis**: Edit temperature calculation parameters (emissivity, object distance, Planck constants, etc.) to match your scenario and immediately update results.
- **Thermal Visualization**: Displays a color-coded temperature map using the Inferno colormap, accompanied by a live temperature legend.
- **Interactive Tooltips**: Hover over the thermal image to view precise temperature values for each pixel.
- **Comprehensive Metadata Panel**: Full JSON display of all extracted metadata for transparency and debugging.
- **Responsive User Interface**: Built with PySide6 for a modern, resizable GUI layout and smooth user experience.
- **Error Handling**: Integrated checks and user-friendly notifications for unsupported files or data errors.

---

## Technical Overview

- **Language**: Python 3
- **Core Libraries**:
  - PySide6 (Qt for Python): GUI development
  - exiftool and exiftool Python bindings: Metadata extraction
  - numpy: Numeric and matrix operations
  - PIL (Pillow): Image processing
  - matplotlib: Color mapping for visualization
- **Platform**: Cross-platform (Linux, Windows, macOS)

---

## Installation

### Prerequisites

- Python 3.8+
- [ExifTool](https://exiftool.org/) installed and accessible from system PATH.

### Required Python Packages

Install dependencies via pip:

```bash
pip install PySide6 exiftool numpy pillow matplotlib
```

### Installation Steps

1. Clone this repository:
    ```bash
    git clone https://github.com/yourusername/warmish.git
    cd warmish
    ```

2. (Optional) Create a virtual environment for isolation:
    ```bash
    python -m venv venv
    source venv/bin/activate   # On Windows use: venv\Scripts\activate
    ```

3. Install dependencies as above.

---

## Usage

Run the application with:

```bash
python thermal_analyzer_ng.py
```

### Main Workflow

1. **Open** a FLIR JPEG image using the "Open FLIR Thermal Image" button.
2. Warmish extracts all metadata and radiometric data.
3. The thermal map and color legend appear. Hover on the image to see temperature tooltips.
4. Adjust analysis parameters in the dedicated panel as needed.
5. Inspect all metadata in the JSON viewer.

---

## GUI Overview

- **Left Panel**: Image display and controls (Open file, temperature tooltip on hover).
- **Right Panel**: Editable analysis parameters, dynamic temperature legend, full metadata display (JSON format).

---

## License

This project is licensed under the GNU General Public License v3.0 (GPLv3).  
See the [LICENSE](LICENSE) file for more details.

---

## Acknowledgements

- Uses ExifTool for robust metadata extraction.
- Based on the PySide6 Qt framework for Python.

---

## Contribution

Issues and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
