import sys
import exiftool
import numpy as np
import json
import subprocess
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QWidget,
    QFileDialog, QMessageBox, QTextEdit, QSizePolicy, QLineEdit, QFormLayout,
    QGroupBox, QTabWidget, QToolBar, QComboBox, QSizePolicy as QSP,
    QCheckBox, QPushButton
)
from PySide6.QtGui import QAction
from PySide6.QtGui import QPixmap, QImage, QIcon
from PySide6.QtCore import Qt
from PIL import Image
import io
import matplotlib.cm as cm

# Palette mapping
PALETTE_MAP = {
    "Iron": cm.inferno,
    "Rainbow": cm.nipy_spectral,
    "Grayscale": cm.gray,
    "Lava": cm.hot,
    "Arctic": cm.cool,
    "Glowbow": cm.gist_rainbow,
    "Amber": cm.YlOrBr,
    "Sepia": cm.copper,
    "Plasma": cm.plasma,
    "Viridis": cm.viridis,
    "Magma": cm.magma,
    "Cividis": cm.cividis,
    "Turbo": cm.turbo,
    "Ocean": cm.ocean,
    "Terrain": cm.terrain,
    "Jet": cm.jet,
    "Fire": cm.afmhot,
    "Ice": cm.winter,
    "Spring": cm.spring,
    "Summer": cm.summer,
    "Autumn": cm.autumn,
    "Bone": cm.bone,
    "Pink": cm.pink,
    "Coolwarm": cm.coolwarm,
    "RdYlBu": cm.RdYlBu,
    "Spectral": cm.Spectral,
    "BrBG": cm.BrBG,
    "PiYG": cm.PiYG,
    "PRGn": cm.PRGn,
    "RdBu": cm.RdBu,
    "RdGy": cm.RdGy,
    "Purples": cm.Purples,
    "Blues": cm.Blues,
    "Greens": cm.Greens,
    "Oranges": cm.Oranges,
    "Reds": cm.Reds,
}

class ThermalAnalyzerNG(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Warmish")
        self.setGeometry(100, 100, 1400, 900)

        # --- Toolbar/Header ---
        self.toolbar = QToolBar("Main Toolbar")
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)
        self.toolbar.setMovable(False)
        # Pulsanti principali
        self.action_open = QAction(QIcon(), "Carica Immagine", self)
        self.action_open.triggered.connect(self.open_image)
        self.toolbar.addAction(self.action_open)
        self.action_save = QAction(QIcon(), "Salva", self)
        self.toolbar.addAction(self.action_save)  # TODO: implementa salvataggio
        self.action_export = QAction(QIcon(), "Esporta", self)
        self.toolbar.addAction(self.action_export)  # TODO: implementa esportazione
        self.toolbar.addSeparator()
        # Selettore palette
        self.palette_combo = QComboBox()
        self.palette_combo.addItems([
            "Iron", "Rainbow", "Grayscale", "Lava", "Arctic", "Glowbow", "Amber", "Sepia", "Plasma", "Viridis", "Magma", "Cividis", "Turbo", "Ocean", "Terrain", "Jet", "Fire", "Ice", "Spring", "Summer", "Autumn", "Bone", "Pink", "Coolwarm", "RdYlBu", "Spectral", "BrBG", "PiYG", "PRGn", "RdBu", "RdGy", "Purples", "Blues", "Greens", "Oranges", "Reds"
        ])
        self.palette_combo.setCurrentIndex(0)
        self.palette_combo.setToolTip("Seleziona palette termica")
        self.toolbar.addWidget(self.palette_combo)
        # Pulsante per invertire la palette
        self.btn_invert_palette = QPushButton("Inverti Palette")
        self.btn_invert_palette.setToolTip("Inverti i colori della palette selezionata")
        self.btn_invert_palette.clicked.connect(self.on_invert_palette)
        self.toolbar.addWidget(self.btn_invert_palette)
        self.toolbar.addSeparator()
        # Strumenti di disegno (placeholder)
        self.action_spot = QAction("Spot", self)
        self.toolbar.addAction(self.action_spot)  # TODO: implementa aggiunta spot
        self.action_rect = QAction("Rettangolo", self)
        self.toolbar.addAction(self.action_rect)  # TODO: implementa aggiunta rettangolo
        self.action_poly = QAction("Poligono", self)
        self.toolbar.addAction(self.action_poly)  # TODO: implementa aggiunta poligono
        self.toolbar.addSeparator()
        # Spacer per allineare a sinistra
        self.toolbar.addWidget(QWidget())
        self.toolbar.widgetForAction(self.toolbar.actions()[-1]).setSizePolicy(QSP.Expanding, QSP.Preferred)

        # --- Layout Principale ---
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # --- Area Centrale: Immagine ---
        self.image_area_widget = QWidget()
        self.image_area_layout = QVBoxLayout(self.image_area_widget)
        self.image_area_layout.setContentsMargins(24, 24, 24, 24)
        self.image_area_layout.setSpacing(8)
        self.main_layout.addWidget(self.image_area_widget, stretch=4)

        # Immagine termica
        self.image_label = QLabel("Nessuna immagine caricata.")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("border: 1px solid gray; background-color: #333;")
        self.image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image_label.setMouseTracking(True)
        self.image_label.mouseMoveEvent = self.image_mouse_move
        self.image_area_layout.addWidget(self.image_label, stretch=1)
        
        # Seconda immagine (sotto l'immagine termica)
        self.secondary_image_label = QLabel("Seconda immagine (opzionale).")
        self.secondary_image_label.setAlignment(Qt.AlignCenter)
        self.secondary_image_label.setStyleSheet("border: 1px solid gray; background-color: #222;")
        self.secondary_image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image_area_layout.addWidget(self.secondary_image_label, stretch=1)
        
        # TODO: Visualizzazione immagine visibile (se presente)
        # TODO: Overlay aree/spot/poligoni (placeholder)

        # Tooltip per la temperatura
        self.temp_tooltip_label = QLabel("Temp: --.-- °C")
        self.temp_tooltip_label.setStyleSheet("background-color: black; color: white; padding: 4px; border-radius: 3px;")
        self.temp_tooltip_label.setVisible(False)
        self.temp_tooltip_label.setParent(self.image_label)

        # --- Sidebar a Tab ---
        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setTabPosition(QTabWidget.East)
        self.sidebar_tabs.setMinimumWidth(400)
        self.main_layout.addWidget(self.sidebar_tabs, stretch=2)

        # --- Tab 1: Parametri Termici ---
        self.tab_params = QWidget()
        self.tab_params_layout = QVBoxLayout(self.tab_params)
        self.tab_params_layout.setContentsMargins(16, 16, 16, 16)
        self.tab_params_layout.setSpacing(12)
        # Parametri di calcolo
        self.params_groupbox = QGroupBox("Parametri di Calcolo")
        self.params_layout = QFormLayout(self.params_groupbox)
        self.param_inputs = {}
        param_keys = ["Emissivity", "ObjectDistance", "ReflectedApparentTemperature", "PlanckR1", "PlanckR2", "PlanckB", "PlanckF", "PlanckO"]
        for key in param_keys:
            line_edit = QLineEdit()
            line_edit.editingFinished.connect(self.update_analysis)
            self.param_inputs[key] = line_edit
            self.params_layout.addRow(key, self.param_inputs[key])
        self.tab_params_layout.addWidget(self.params_groupbox)
        # Legenda
        self.legend_groupbox = QGroupBox("Legenda Temperatura (°C)")
        self.legend_layout = QVBoxLayout(self.legend_groupbox)
        self.legend_layout.setAlignment(Qt.AlignCenter)
        self.legend_label_max = QLabel("Max")
        self.legend_label_max.setAlignment(Qt.AlignCenter)
        self.legend_gradient = QLabel()
        self.legend_gradient.setMinimumHeight(200)
        self.legend_label_min = QLabel("Min")
        self.legend_label_min.setAlignment(Qt.AlignCenter)
        self.legend_layout.addWidget(self.legend_label_max)
        self.legend_layout.addWidget(self.legend_gradient, stretch=1)
        self.legend_layout.addWidget(self.legend_label_min)
        self.tab_params_layout.addWidget(self.legend_groupbox)
        # Metadati
        self.all_meta_display = QTextEdit("Tutti i metadati estratti appariranno qui.")
        self.all_meta_display.setReadOnly(True)
        self.tab_params_layout.addWidget(self.all_meta_display)
        self.sidebar_tabs.addTab(self.tab_params, "Parametri")

        # --- Tab 2: Aree/Spot/Poligoni ---
        self.tab_areas = QWidget()
        self.tab_areas_layout = QVBoxLayout(self.tab_areas)
        self.tab_areas_layout.setContentsMargins(16, 16, 16, 16)
        self.tab_areas_layout.setSpacing(12)
        # TODO: Lista aree/spot/poligoni con statistiche e parametri area
        self.tab_areas_layout.addWidget(QLabel("[TODO] Qui verrà la lista delle aree, spot e poligoni con statistiche e parametri area."))
        self.sidebar_tabs.addTab(self.tab_areas, "Aree & Analisi")

        # --- Tab 3: Batch/Export ---
        self.tab_batch = QWidget()
        self.tab_batch_layout = QVBoxLayout(self.tab_batch)
        self.tab_batch_layout.setContentsMargins(16, 16, 16, 16)
        self.tab_batch_layout.setSpacing(12)

        # --- Batch Processing Group ---
        batch_group = QGroupBox("Batch Processing")
        batch_layout = QVBoxLayout(batch_group)

        # Selettore immagini (drag & drop o click)
        self.batch_file_label = QLabel("Drag & drop images or click to browse\nSupports .FLIR, .JPG (with thermal data), .PNG")
        self.batch_file_label.setAlignment(Qt.AlignCenter)
        self.batch_file_label.setStyleSheet("border: 1px dashed #888; padding: 32px; color: #ccc;")
        batch_layout.addWidget(self.batch_file_label)

        # Checkbox opzioni
        self.cb_thermal_params = QCheckBox("Thermal Parameters")
        self.cb_analysis_areas = QCheckBox("Analysis Areas (same positions)")
        self.cb_color_palette = QCheckBox("Color Palette")
        batch_layout.addWidget(self.cb_thermal_params)
        batch_layout.addWidget(self.cb_analysis_areas)
        batch_layout.addWidget(self.cb_color_palette)

        # Bottone processa
        self.btn_process_batch = QPushButton("Process Selected Images")
        self.btn_process_batch.setStyleSheet("background-color: #a259f7; color: white; font-weight: bold;")
        batch_layout.addWidget(self.btn_process_batch)

        self.tab_batch_layout.addWidget(batch_group)

        # --- Export Options Group ---
        export_group = QGroupBox("Export Options")
        export_layout = QVBoxLayout(export_group)

        # Formati export
        export_format_layout = QHBoxLayout()
        self.btn_export_png = QPushButton("Image (.PNG)")
        self.btn_export_csv = QPushButton("Data (.CSV)")
        self.btn_export_pdf = QPushButton("Report (.PDF)")
        self.btn_export_raw = QPushButton("Raw Data")
        export_format_layout.addWidget(self.btn_export_png)
        export_format_layout.addWidget(self.btn_export_csv)
        export_format_layout.addWidget(self.btn_export_pdf)
        export_format_layout.addWidget(self.btn_export_raw)
        export_layout.addLayout(export_format_layout)

        # Bottone export
        self.btn_export_current = QPushButton("Export Current Analysis")
        self.btn_export_current.setStyleSheet("background-color: #6c47e6; color: white; font-weight: bold;")
        export_layout.addWidget(self.btn_export_current)

        self.tab_batch_layout.addWidget(export_group)

        self.sidebar_tabs.addTab(self.tab_batch, "Batch & Export")

        # --- Dati immagine ---
        self.thermal_data = None
        self.temperature_data = None
        self.temp_min = 0
        self.temp_max = 0
        self.metadata = None
        self.base_pixmap = None
        self.selected_palette = "Iron"
        self.palette_inverted = False  # Stato inversione palette
        self.palette_combo.currentIndexChanged.connect(self.on_palette_changed)

    def open_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Seleziona Immagine FLIR", "", "Immagini JPEG (*.jpg *.jpeg)")
        if not file_path: return

        try:
            self.setWindowTitle(f"Warmish - {file_path.split('/')[-1]}")
            with exiftool.ExifTool() as et:
                json_string = et.execute(b"-json", file_path.encode())
                self.metadata = json.loads(json_string)[0]
                self.all_meta_display.setPlainText(json.dumps(self.metadata, indent=4, default=str))
            
            self.populate_params()

            command = ["exiftool", "-b", "-RawThermalImage", file_path]
            result = subprocess.run(command, capture_output=True, check=True)
            raw_thermal_bytes = result.stdout
            if not raw_thermal_bytes: raise ValueError("Dati termici binari non estratti.")

            image_type = self.metadata.get("APP1:RawThermalImageType", "Unknown")
            if image_type == "PNG":
                self.thermal_data = np.array(Image.open(io.BytesIO(raw_thermal_bytes)))
                
                # LA CORREZIONE FONDAMENTALE: Invertiamo l'ordine dei byte!
                # Le PNG di FLIR usano un ordine dei byte non standard (MSB).
                # NumPy lo legge nell'ordine nativo della macchina (LSB).
                # Dobbiamo invertirlo per ottenere i valori corretti.
                self.thermal_data.byteswap(inplace=True)

            else:
                width = self.metadata.get('APP1:RawThermalImageWidth')
                height = self.metadata.get('APP1:RawThermalImageHeight')
                if not width or not height: raise ValueError("Dimensioni immagine non trovate.")
                self.thermal_data = np.frombuffer(raw_thermal_bytes, dtype=np.uint16).reshape((height, width))

            self.update_analysis()
            # QMessageBox.information(self, "Successo", "Immagine radiometrica caricata con successo!")

        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Impossibile processare il file:\n{e}")
            import traceback
            traceback.print_exc()

        # --- Estrazione e visualizzazione immagine visibile (se presente) ---
        try:
            command_rgb = ["exiftool", "-b", "-EmbeddedImage", file_path]
            result_rgb = subprocess.run(command_rgb, capture_output=True, check=True)
            rgb_bytes = result_rgb.stdout
            if rgb_bytes:
                image_rgb = Image.open(io.BytesIO(rgb_bytes))
                image_rgb = image_rgb.convert("RGB")
                data = image_rgb.tobytes("raw", "RGB")
                qimage = QImage(data, image_rgb.width, image_rgb.height, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(qimage)
                self.secondary_image_label.setPixmap(
                    pixmap.scaled(self.secondary_image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
            else:
                self.secondary_image_label.setText("Nessuna immagine visibile trovata.")
        except Exception as e:
            self.secondary_image_label.setText("Errore caricamento immagine visibile.")

    def update_analysis(self):
        if self.thermal_data is None: return
        print(">>> Ricalcolo temperature e visualizzazione...")
        self.calculate_temperature_matrix()
        self.create_colored_pixmap()
        self.update_legend()
        self.display_thermal_image()

    def populate_params(self):
        if not self.metadata: return
        for key, line_edit in self.param_inputs.items():
            value = self.metadata.get(f"APP1:{key}", self.metadata.get(key, "N/A"))
            line_edit.setText(str(value))

    def calculate_temperature_matrix(self):
        try:
            emissivity = float(self.param_inputs["Emissivity"].text())
            refl_temp_C = float(self.param_inputs["ReflectedApparentTemperature"].text())
            R1 = float(self.param_inputs["PlanckR1"].text())
            R2 = float(self.param_inputs["PlanckR2"].text())
            B = float(self.param_inputs["PlanckB"].text())
            F = float(self.param_inputs["PlanckF"].text())
            O = float(self.param_inputs["PlanckO"].text())
            refl_temp_K = refl_temp_C + 273.15
            
            raw_refl = R1 / (R2 * (np.exp(B / refl_temp_K) - F)) - O
            raw_obj = (self.thermal_data - (1 - emissivity) * raw_refl) / emissivity
            
            log_arg = R1 / (R2 * (raw_obj + O)) + F
            temp_K = np.full(log_arg.shape, np.nan, dtype=np.float64)
            valid_indices = log_arg > 0
            temp_K[valid_indices] = B / np.log(log_arg[valid_indices])

            self.temperature_data = temp_K - 273.15
            self.temp_min = np.nanmin(self.temperature_data)
            self.temp_max = np.nanmax(self.temperature_data)
        except Exception as e:
            print(f"Errore calcolo temperature: {e}")
            self.temperature_data = np.zeros_like(self.thermal_data, dtype=float)
            self.temp_min, self.temp_max = 0, 0
    
    def create_colored_pixmap(self):
        if self.temperature_data is None: return
        
        # Normalizza i dati di temperatura da min/max a 0-1
        # Aggiungiamo un piccolo epsilon per evitare divisioni per zero se min=max
        temp_range = self.temp_max - self.temp_min
        if temp_range == 0: temp_range = 1 
        
        norm_data = (self.temperature_data - self.temp_min) / temp_range
        norm_data = np.nan_to_num(norm_data)

        # Usa la colormap selezionata
        cmap = PALETTE_MAP.get(self.selected_palette, cm.inferno)
        if self.palette_inverted:
            norm_data = 1.0 - norm_data
        colored_data = cmap(norm_data)
        image_8bit = (colored_data[:, :, :3] * 255).astype(np.uint8)
        
        height, width, _ = image_8bit.shape
        q_image = QImage(image_8bit.data, width, height, width * 3, QImage.Format_RGB888)
        self.base_pixmap = QPixmap.fromImage(q_image)

    def update_legend(self):
        # Usa la colormap selezionata anche per la legenda
        gradient_array = np.linspace(1, 0, 256).reshape(256, 1)
        cmap = PALETTE_MAP.get(self.selected_palette, cm.inferno)
        if self.palette_inverted:
            gradient_array = 1.0 - gradient_array
        gradient_colored = cmap(gradient_array)
        gradient_8bit = (gradient_colored[:, :, :3] * 255).astype(np.uint8)
        
        h, w, _ = gradient_8bit.shape
        q_image = QImage(gradient_8bit.data, w, h, w * 3, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)
        
        self.legend_gradient.setPixmap(pixmap.scaled(self.legend_gradient.width(), self.legend_gradient.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
        self.legend_label_max.setText(f"{self.temp_max:.2f} °C")
        self.legend_label_min.setText(f"{self.temp_min:.2f} °C")
        
    def image_mouse_move(self, event):
        if self.temperature_data is None: return
        pos = event.position()
        label_size = self.image_label.size()
        pixmap_size = self.image_label.pixmap().size()
        if pixmap_size.width() == 0 or pixmap_size.height() == 0: return

        offset_x = (label_size.width() - pixmap_size.width()) / 2
        offset_y = (label_size.height() - pixmap_size.height()) / 2
        pix_x, pix_y = pos.x() - offset_x, pos.y() - offset_y
        
        img_h, img_w = self.temperature_data.shape
        matrix_x = int(pix_x * img_w / pixmap_size.width())
        matrix_y = int(pix_y * img_h / pixmap_size.height())

        if 0 <= matrix_x < img_w and 0 <= matrix_y < img_h:
            temperature = self.temperature_data[matrix_y, matrix_x]
            if not np.isnan(temperature):
                self.temp_tooltip_label.setText(f"{temperature:.2f} °C")
                self.temp_tooltip_label.move(int(pos.x()) + 10, int(pos.y()) + 10)
                self.temp_tooltip_label.setVisible(True)
                self.temp_tooltip_label.adjustSize()
            else:
                self.temp_tooltip_label.setVisible(False)
        else:
            self.temp_tooltip_label.setVisible(False)
        
    def display_thermal_image(self):
        if self.base_pixmap is None: return
        self.image_label.setPixmap(
            self.base_pixmap.scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.display_thermal_image()
        self.update_legend()
        # Aggiorna anche la seconda immagine
        if self.secondary_image_label.pixmap():
            self.secondary_image_label.setPixmap(
                self.secondary_image_label.pixmap().scaled(
                    self.secondary_image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )

    def on_palette_changed(self, idx):
        self.selected_palette = self.palette_combo.currentText()
        self.update_analysis()

    def on_invert_palette(self):
        self.palette_inverted = not self.palette_inverted
        self.update_analysis()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ThermalAnalyzerNG()
    window.show()
    sys.exit(app.exec())
