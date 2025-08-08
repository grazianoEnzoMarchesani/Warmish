import sys
import json
import io
import subprocess
import exiftool
import numpy as np
from PIL import Image
import matplotlib.cm as cm

from PySide6.QtWidgets import (
    QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QWidget,
    QFileDialog, QMessageBox, QTextEdit, QSizePolicy, QLineEdit, QFormLayout,
    QGroupBox, QTabWidget, QToolBar, QComboBox, QSizePolicy as QSP,
    QCheckBox, QPushButton, QSlider, QDoubleSpinBox, QSpinBox
)
from PySide6.QtGui import QAction, QPixmap, QImage, QIcon, QColor, QPen, QFontMetrics, QPainter
from PySide6.QtCore import Qt, QRect

from constants import PALETTE_MAP
from .widgets.color_bar_legend import ColorBarLegend


class ThermalAnalyzerNG(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Warmish")
        self.setGeometry(100, 100, 1400, 900)

        # --- Toolbar/Header ---
        self.toolbar = QToolBar("Main Toolbar")
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)
        self.toolbar.setMovable(False)
        # 1) File actions
        self.action_open = QAction(QIcon(), "Carica Immagine", self)
        self.action_open.triggered.connect(self.open_image)
        self.toolbar.addAction(self.action_open)
        self.action_save = QAction(QIcon(), "Salva", self)
        self.toolbar.addAction(self.action_save)  # TODO: implementa salvataggio
        self.action_export = QAction(QIcon(), "Esporta", self)
        self.toolbar.addAction(self.action_export)  # TODO: implementa esportazione
        self.toolbar.addSeparator()
        # 2) Palette controls
        self.palette_combo = QComboBox()
        self.palette_combo.addItems([
            "Iron", "Rainbow", "Grayscale", "Lava", "Arctic", "Glowbow", "Amber", "Sepia", "Plasma", "Viridis", "Magma", "Cividis", "Turbo", "Ocean", "Terrain", "Jet", "Fire", "Ice", "Spring", "Summer", "Autumn", "Bone", "Pink", "Coolwarm", "RdYlBu", "Spectral", "BrBG", "PiYG", "PRGn", "RdBu", "RdGy", "Purples", "Blues", "Greens", "Oranges", "Reds"
        ])
        self.palette_combo.setCurrentIndex(0)
        self.palette_combo.setToolTip("Seleziona palette termica")
        self.toolbar.addWidget(self.palette_combo)
        # Pulsante per invertire la palette
        self.action_invert_palette = QAction("Inverti Palette", self)
        self.action_invert_palette.triggered.connect(self.on_invert_palette)
        self.toolbar.addAction(self.action_invert_palette)
        self.toolbar.addSeparator()
        # 3) Overlay toggle + grouped overlay controls
        self.action_overlay_view = QAction("Overlay", self)
        self.action_overlay_view.setCheckable(True)
        self.action_overlay_view.toggled.connect(self.on_overlay_toggled)
        self.toolbar.addAction(self.action_overlay_view)
        # Crea un contenitore compatto per i controlli overlay, così lo slider non si comprime eccessivamente
        self.overlay_controls_widget = QWidget()
        _ovl = QHBoxLayout(self.overlay_controls_widget)
        _ovl.setContentsMargins(0, 0, 0, 0)
        _ovl.setSpacing(6)
        # Slider opacità con etichetta e larghezza minima
        from PySide6.QtWidgets import QLabel as _QLabel
        _ovl.addWidget(_QLabel("Opacità"))
        self.overlay_alpha_slider = QSlider(Qt.Horizontal)
        self.overlay_alpha_slider.setRange(0, 100)
        self.overlay_alpha_slider.setValue(50)
        self.overlay_alpha_slider.setToolTip("Opacità termica in overlay")
        self.overlay_alpha_slider.setMinimumWidth(160)
        self.overlay_alpha_slider.setMaximumWidth(260)
        self.overlay_alpha_slider.setSizePolicy(QSP.Preferred, QSP.Fixed)
        self.overlay_alpha_slider.valueChanged.connect(self.on_overlay_alpha_changed)
        _ovl.addWidget(self.overlay_alpha_slider)
        # Spinbox scala manuale
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setDecimals(3)
        self.scale_spin.setRange(0.100, 5.000)
        self.scale_spin.setSingleStep(0.01)
        self.scale_spin.setPrefix("Scala ")
        self.scale_spin.setValue(1.0)
        self.scale_spin.setToolTip("Scala IR rispetto al visibile (Real2IR)")
        self.scale_spin.valueChanged.connect(self.on_scale_spin_changed)
        _ovl.addWidget(self.scale_spin)
        # Spinbox offset manuali (in pixel visibile)
        self.offsetx_spin = QSpinBox()
        self.offsetx_spin.setRange(-2000, 2000)
        self.offsetx_spin.setSingleStep(1)
        self.offsetx_spin.setPrefix("OffX ")
        self.offsetx_spin.setToolTip("Offset X (pixel visibile)")
        self.offsetx_spin.valueChanged.connect(self.on_offsetx_changed)
        _ovl.addWidget(self.offsetx_spin)
        self.offsety_spin = QSpinBox()
        self.offsety_spin.setRange(-2000, 2000)
        self.offsety_spin.setSingleStep(1)
        self.offsety_spin.setPrefix("OffY ")
        self.offsety_spin.setToolTip("Offset Y (pixel visibile)")
        self.offsety_spin.valueChanged.connect(self.on_offsety_changed)
        _ovl.addWidget(self.offsety_spin)
        # Combo box metodo di fusione (visibile solo in overlay)
        self.blend_combo = QComboBox()
        self.blend_combo.addItems([
            "Normal", "Multiply", "Screen", "Overlay", "Darken", "Lighten",
            "ColorDodge", "ColorBurn", "SoftLight", "HardLight", "Difference", "Exclusion", "Additive"
        ])
        self.blend_combo.setCurrentText("Normal")
        self.blend_combo.setToolTip("Metodo di fusione per l'overlay termico")
        self.blend_combo.currentTextChanged.connect(self.on_blend_mode_changed)
        _ovl.addWidget(self.blend_combo)
        # Inserisci il gruppo nella toolbar come singola azione
        self.overlay_action = self.toolbar.addWidget(self.overlay_controls_widget)
        # Pulsante reset allineamento (vicino ai controlli overlay)
        self.action_reset_align = QAction("Reset Allineamento", self)
        self.action_reset_align.setToolTip("Ripristina Scala e Offset da metadati")
        self.action_reset_align.triggered.connect(self.on_reset_alignment)
        self.toolbar.addAction(self.action_reset_align)
        self.toolbar.addSeparator()
        # Nascondi il gruppo overlay finché non è attivo
        self.set_overlay_controls_visible(False)
        # 4) Zoom controls
        self.zoom_factor = 1.0
        self.pan_offset = [0, 0]
        self._panning = False
        self._pan_start = None
        self.action_zoom_in = QAction("Zoom +", self)
        self.action_zoom_in.triggered.connect(self.zoom_in)
        self.toolbar.addAction(self.action_zoom_in)
        self.action_zoom_out = QAction("Zoom -", self)
        self.action_zoom_out.triggered.connect(self.zoom_out)
        self.toolbar.addAction(self.action_zoom_out)
        self.action_zoom_reset = QAction("Reset Zoom", self)
        self.action_zoom_reset.triggered.connect(self.zoom_reset)
        self.toolbar.addAction(self.action_zoom_reset)
        self.toolbar.addSeparator()
        # 5) Strumenti di disegno spostati nel Tab "Aree & Analisi"
        # Spacer per spingere gli elementi a sinistra
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
        self.image_label.mouseMoveEvent = self.image_mouse_move_event
        self.image_label.mousePressEvent = self.image_mouse_press
        self.image_label.mouseReleaseEvent = self.image_mouse_release
        self.image_area_layout.addWidget(self.image_label, stretch=1)
        
        # Seconda immagine (sotto l'immagine termica)
        self.secondary_image_label = QLabel("Seconda immagine (opzionale).")
        self.secondary_image_label.setAlignment(Qt.AlignCenter)
        self.secondary_image_label.setStyleSheet("border: 1px solid gray; background-color: #222;")
        self.secondary_image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.secondary_image_label.setMouseTracking(True)
        self.secondary_image_label.mousePressEvent = self.image_mouse_press
        self.secondary_image_label.mouseReleaseEvent = self.image_mouse_release
        self.secondary_image_label.mouseMoveEvent = self.secondary_image_mouse_move_event  # <--- CAMBIA QUI
        self.image_area_layout.addWidget(self.secondary_image_label, stretch=1)
        
        # TODO: Visualizzazione immagine visibile (se presente)
        # TODO: Overlay aree/spot/poligoni (placeholder)

        # Tooltip per la temperatura
        self.temp_tooltip_label = QLabel("Temp: --.-- °C")
        self.temp_tooltip_label.setStyleSheet("background-color: black; color: white; padding: 4px; border-radius: 3px;")
        self.temp_tooltip_label.setVisible(False)
        self.temp_tooltip_label.setParent(self.image_label)

        # --- Legenda sempre visibile accanto alle immagini ---
        self.legend_groupbox = QGroupBox("Legenda Temperatura (°C)")
        self.legend_layout = QVBoxLayout(self.legend_groupbox)
        self.legend_layout.setContentsMargins(8, 8, 8, 8)
        self.legend_layout.setSpacing(6)
        self.legend_layout.setAlignment(Qt.AlignCenter)
        self.colorbar = ColorBarLegend()
        self.legend_layout.addWidget(self.colorbar, alignment=Qt.AlignCenter)
        self.legend_groupbox.setMaximumWidth(140)
        # Inserisci la legenda tra l'area immagini e la sidebar a tab
        self.main_layout.addWidget(self.legend_groupbox, stretch=0)

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
        # (Legenda spostata accanto alle immagini; rimossa dal tab)
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

        # Barra strumenti disegno (Spot, Rettangolo, Poligono) nella scheda Aree & Analisi
        self.areas_tools_widget = QWidget()
        _areas_tools = QHBoxLayout(self.areas_tools_widget)
        _areas_tools.setContentsMargins(0, 0, 0, 0)
        _areas_tools.setSpacing(12)

        self.btn_spot = QPushButton("Spot")
        self.btn_rect = QPushButton("Rettangolo")
        self.btn_poly = QPushButton("Poligono")
        _areas_tools.addWidget(self.btn_spot)
        _areas_tools.addWidget(self.btn_rect)
        _areas_tools.addWidget(self.btn_poly)
        _areas_tools.addStretch(1)
        self.tab_areas_layout.addWidget(self.areas_tools_widget)

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
        self.base_pixmap_visible = None  # <--- AGGIUNGI QUESTA RIGA
        self.selected_palette = "Iron"
        self.palette_inverted = False  # Stato inversione palette
        self.palette_combo.currentIndexChanged.connect(self.on_palette_changed)
        # Overlay state
        self.overlay_mode = False
        self.overlay_alpha = 0.5
        self.overlay_scale = 1.0
        self.visible_gray_full = None
        self.overlay_offset_x = 0.0
        self.overlay_offset_y = 0.0
        self.meta_overlay_scale = 1.0
        self.meta_offset_x = 0.0
        self.meta_offset_y = 0.0
        self.overlay_blend_mode = "Normal"

    def open_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Seleziona Immagine FLIR", "", "Immagini JPEG (*.jpg *.jpeg)")
        if not file_path: return

        try:
            self.setWindowTitle(f"Warmish - {file_path.split('/')[-1]}")
            with exiftool.ExifTool() as et:
                json_string = et.execute(b"-json", file_path.encode())
                self.metadata = json.loads(json_string)[0]
                self.all_meta_display.setPlainText(json.dumps(self.metadata, indent=4, default=str))
                # Imposta scala overlay direttamente dai metadati, se disponibile
                try:
                    self.meta_overlay_scale = 1/float(self.metadata.get("APP1:Real2IR", 1.0))
                    self.overlay_scale = self.meta_overlay_scale
                except Exception:
                    self.meta_overlay_scale = 1.0
                    self.overlay_scale = 1.0
                # Imposta offset overlay (in pixel visibile)
                try:
                    self.meta_offset_x = float(self.metadata.get("APP1:OffsetX", 0.0))
                    self.overlay_offset_x = self.meta_offset_x
                except Exception:
                    self.meta_offset_x = 0.0
                    self.overlay_offset_x = 0.0
                try:
                    self.meta_offset_y = float(self.metadata.get("APP1:OffsetY", 0.0))
                    self.overlay_offset_y = self.meta_offset_y
                except Exception:
                    self.meta_offset_y = 0.0
                    self.overlay_offset_y = 0.0
                # Aggiorna lo spinbox con la scala
                try:
                    self.scale_spin.blockSignals(True)
                    self.scale_spin.setValue(self.overlay_scale)
                    self.offsetx_spin.blockSignals(True)
                    self.offsetx_spin.setValue(int(round(self.overlay_offset_x)))
                    self.offsety_spin.blockSignals(True)
                    self.offsety_spin.setValue(int(round(self.overlay_offset_y)))
                finally:
                    self.scale_spin.blockSignals(False)
                    self.offsetx_spin.blockSignals(False)
                    self.offsety_spin.blockSignals(False)
            
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
                # Salva anche versione grayscale per auto-allineamento
                self.visible_gray_full = np.array(image_rgb.convert("L"), dtype=np.float32) / 255.0
                data = image_rgb.tobytes("raw", "RGB")
                qimage = QImage(data, image_rgb.width, image_rgb.height, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(qimage)
                self.base_pixmap_visible = pixmap  # <--- SALVA LA PIXMAP ORIGINALE
                # Scala overlay già impostata da metadati; aggiorna la vista
                self.display_images()
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
        self.display_images()

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
        if self.temperature_data is None:
            return
        self.colorbar.set_palette(self.selected_palette, self.palette_inverted)
        self.colorbar.set_range(self.temp_min, self.temp_max)

    def image_mouse_move(self, event):
        if self.temperature_data is None:
            return

        pos = event.position()
        label_size = self.image_label.size()
        # Calcola la dimensione dell'immagine visualizzata (dopo zoom)
        target_size = label_size * self.zoom_factor
        pixmap_width = int(target_size.width())
        pixmap_height = int(target_size.height())

        # Calcola l'offset per centrare l'immagine e aggiungi il pan
        offset_x = (label_size.width() - pixmap_width) // 2 + int(self.pan_offset[0])
        offset_y = (label_size.height() - pixmap_height) // 2 + int(self.pan_offset[1])

        # Posizione del mouse relativa all'immagine visualizzata
        pix_x = pos.x() - offset_x
        pix_y = pos.y() - offset_y

        img_h, img_w = self.temperature_data.shape
        # Mappa la posizione del mouse sulla matrice dati
        if 0 <= pix_x < pixmap_width and 0 <= pix_y < pixmap_height:
            matrix_x = int(pix_x * img_w / pixmap_width)
            matrix_y = int(pix_y * img_h / pixmap_height)
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
        else:
            self.temp_tooltip_label.setVisible(False)
        
    # --- Panning Methods ---
    def image_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._panning = True
            self._pan_start = (event.position().x(), event.position().y())

    def image_mouse_release(self, event):
        if event.button() == Qt.LeftButton:
            self._panning = False
            self._pan_start = None

    def image_mouse_move_event(self, event):
        # Gestione panning
        if self._panning and self._pan_start:
            dx = event.position().x() - self._pan_start[0]
            dy = event.position().y() - self._pan_start[1]
            self._pan_start = (event.position().x(), event.position().y())
            self.pan_offset[0] += dx
            self.pan_offset[1] += dy
            self.display_images()
            # Nascondi il tooltip durante il pan
            self.temp_tooltip_label.setVisible(False)
        else:
            # Gestione tooltip temperatura
            if self.temperature_data is None:
                self.temp_tooltip_label.setVisible(False)
                return

            pos = event.position()
            label_size = self.image_label.size()
            target_size = label_size * self.zoom_factor

            # Se overlay attivo, usa le dimensioni della termica in overlay e includi offset
            if self.overlay_mode:
                thr_pixmap = self.base_pixmap.scaled(
                    int(target_size.width() * self.overlay_scale),
                    int(target_size.height() * self.overlay_scale),
                    Qt.KeepAspectRatio, Qt.SmoothTransformation
                ) if self.base_pixmap is not None else None
                if thr_pixmap is None:
                    self.temp_tooltip_label.setVisible(False)
                    return
                if self.base_pixmap_visible is not None:
                    vis_pixmap = self.base_pixmap_visible.scaled(
                        int(target_size.width()), int(target_size.height()),
                        Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                    x_vis = (label_size.width() - vis_pixmap.width()) // 2 + int(self.pan_offset[0])
                    y_vis = (label_size.height() - vis_pixmap.height()) // 2 + int(self.pan_offset[1])
                    base_vis_w = self.base_pixmap_visible.width()
                    base_vis_h = self.base_pixmap_visible.height()
                    scale_vx = vis_pixmap.width() / base_vis_w if base_vis_w else 1.0
                    scale_vy = vis_pixmap.height() / base_vis_h if base_vis_h else 1.0
                    ox = int(round(self.overlay_offset_x * scale_vx))
                    oy = int(round(self.overlay_offset_y * scale_vy))
                    pixmap_width = thr_pixmap.width()
                    pixmap_height = thr_pixmap.height()
                    offset_x = x_vis + (vis_pixmap.width() - pixmap_width) // 2 + ox
                    offset_y = y_vis + (vis_pixmap.height() - pixmap_height) // 2 + oy
                else:
                    pixmap_width = thr_pixmap.width()
                    pixmap_height = thr_pixmap.height()
                    offset_x = (label_size.width() - pixmap_width) // 2 + int(self.pan_offset[0])
                    offset_y = (label_size.height() - pixmap_height) // 2 + int(self.pan_offset[1])
            else:
                pixmap_width = int(target_size.width())
                pixmap_height = int(target_size.height())
                offset_x = (label_size.width() - pixmap_width) // 2 + int(self.pan_offset[0])
                offset_y = (label_size.height() - pixmap_height) // 2 + int(self.pan_offset[1])

            pix_x = pos.x() - offset_x
            pix_y = pos.y() - offset_y

            img_h, img_w = self.temperature_data.shape
            if 0 <= pix_x < pixmap_width and 0 <= pix_y < pixmap_height:
                matrix_x = int(pix_x * img_w / pixmap_width)
                matrix_y = int(pix_y * img_h / pixmap_height)
                if 0 <= matrix_x < img_w and 0 <= matrix_y < img_h:
                    temperature = self.temperature_data[matrix_y, matrix_x]
                    if not np.isnan(temperature):
                        self.temp_tooltip_label.setText(f"{temperature:.2f} °C")
                        self.temp_tooltip_label.move(int(pos.x()) + 10, int(pos.y()) + 10)
                        self.temp_tooltip_label.setVisible(True)
                        self.temp_tooltip_label.adjustSize()
                        return
            self.temp_tooltip_label.setVisible(False)

    def secondary_image_mouse_move_event(self, event):
        self.temp_tooltip_label.setVisible(False)  # <--- NASCONDI SEMPRE IL TOOLTIP

    # --- Zoom Methods ---
    def zoom_in(self):
        self.zoom_factor *= 1.2
        self.display_images()

    def zoom_out(self):
        self.zoom_factor /= 1.2
        self.display_images()

    def zoom_reset(self):
        self.zoom_factor = 1.0
        self.pan_offset = [0, 0]
        self.display_images()

    def display_images(self):
        if self.overlay_mode and self.base_pixmap_visible is not None:
            self.display_overlay_image()
            self.secondary_image_label.setVisible(False)
        else:
            self.display_thermal_image()
            self.display_secondary_image()
            self.secondary_image_label.setVisible(True)

    def display_thermal_image(self):
        if self.base_pixmap is None:
            return
        target_size = self.image_label.size() * self.zoom_factor
        pixmap = self.base_pixmap.scaled(
            int(target_size.width()), int(target_size.height()),
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        # Crea una QPixmap vuota della dimensione del widget
        canvas = QPixmap(self.image_label.size())
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        # Calcola il centro e applica il pan
        x = (self.image_label.width() - pixmap.width()) // 2 + int(self.pan_offset[0])
        y = (self.image_label.height() - pixmap.height()) // 2 + int(self.pan_offset[1])
        painter.drawPixmap(x, y, pixmap)
        painter.end()
        self.image_label.setPixmap(canvas)

    def display_overlay_image(self):
        if self.base_pixmap is None and self.base_pixmap_visible is None:
            return
        target_size = self.image_label.size() * self.zoom_factor
        # Visibile come base
        if self.base_pixmap_visible is not None:
            vis_pixmap = self.base_pixmap_visible.scaled(
                int(target_size.width()), int(target_size.height()),
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        else:
            vis_pixmap = None
        # Termica come overlay con scala relativa
        if self.base_pixmap is not None:
            thr_pixmap = self.base_pixmap.scaled(
                int(target_size.width() * self.overlay_scale),
                int(target_size.height() * self.overlay_scale),
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        else:
            thr_pixmap = None

        canvas = QPixmap(self.image_label.size())
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)

        if vis_pixmap is not None:
            x_vis = (self.image_label.width() - vis_pixmap.width()) // 2 + int(self.pan_offset[0])
            y_vis = (self.image_label.height() - vis_pixmap.height()) // 2 + int(self.pan_offset[1])
            painter.drawPixmap(x_vis, y_vis, vis_pixmap)

        if thr_pixmap is not None:
            # Se c'è la visibile, allinea al suo centro e applica offset metadati
            if vis_pixmap is not None:
                base_vis_w = self.base_pixmap_visible.width()
                base_vis_h = self.base_pixmap_visible.height()
                scale_vx = vis_pixmap.width() / base_vis_w if base_vis_w else 1.0
                scale_vy = vis_pixmap.height() / base_vis_h if base_vis_h else 1.0
                ox = int(round(self.overlay_offset_x * scale_vx))
                oy = int(round(self.overlay_offset_y * scale_vy))
                x_thr = x_vis + (vis_pixmap.width() - thr_pixmap.width()) // 2 + ox
                y_thr = y_vis + (vis_pixmap.height() - thr_pixmap.height()) // 2 + oy
            else:
                x_thr = (self.image_label.width() - thr_pixmap.width()) // 2 + int(self.pan_offset[0])
                y_thr = (self.image_label.height() - thr_pixmap.height()) // 2 + int(self.pan_offset[1])
            # Blend mode
            painter.setCompositionMode(self.get_qt_composition_mode())
            painter.setOpacity(self.overlay_alpha)
            painter.drawPixmap(x_thr, y_thr, thr_pixmap)
            painter.setOpacity(1.0)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        painter.end()
        self.image_label.setPixmap(canvas)

    def display_secondary_image(self):
        if self.base_pixmap_visible is not None:
            target_size = self.secondary_image_label.size() * self.zoom_factor
            pixmap = self.base_pixmap_visible.scaled(
                int(target_size.width()), int(target_size.height()),
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            canvas = QPixmap(self.secondary_image_label.size())
            canvas.fill(Qt.transparent)
            painter = QPainter(canvas)
            x = (self.secondary_image_label.width() - pixmap.width()) // 2 + int(self.pan_offset[0])
            y = (self.secondary_image_label.height() - pixmap.height()) // 2 + int(self.pan_offset[1])
            painter.drawPixmap(x, y, pixmap)
            painter.end()
            self.secondary_image_label.setPixmap(canvas)
        else:
            self.secondary_image_label.clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.display_images()
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

    # --- Overlay related helpers ---
    def on_overlay_toggled(self, checked: bool):
        self.overlay_mode = checked
        self.set_overlay_controls_visible(checked)
        self.display_images()

    def on_overlay_alpha_changed(self, value: int):
        self.overlay_alpha = max(0.0, min(1.0, value / 100.0))
        if self.overlay_mode:
            self.display_images()

    def on_scale_spin_changed(self, value: float):
        self.overlay_scale = float(value)
        if self.overlay_mode:
            self.display_images()

    def on_offsetx_changed(self, value: int):
        self.overlay_offset_x = float(value)
        if self.overlay_mode:
            self.display_images()

    def on_offsety_changed(self, value: int):
        self.overlay_offset_y = float(value)
        if self.overlay_mode:
            self.display_images()

    def on_reset_alignment(self):
        # Ripristina valori letti dai metadati (se presenti)
        self.overlay_scale = float(self.meta_overlay_scale)
        self.overlay_offset_x = float(self.meta_offset_x)
        self.overlay_offset_y = float(self.meta_offset_y)
        # Sincronizza controlli UI
        try:
            self.scale_spin.blockSignals(True)
            self.offsetx_spin.blockSignals(True)
            self.offsety_spin.blockSignals(True)
            self.scale_spin.setValue(self.overlay_scale)
            self.offsetx_spin.setValue(int(round(self.overlay_offset_x)))
            self.offsety_spin.setValue(int(round(self.overlay_offset_y)))
        finally:
            self.scale_spin.blockSignals(False)
            self.offsetx_spin.blockSignals(False)
            self.offsety_spin.blockSignals(False)
        # Aggiorna la vista
        self.display_images()

    def on_blend_mode_changed(self, mode: str):
        self.overlay_blend_mode = mode
        if self.overlay_mode:
            self.display_images()

    def get_qt_composition_mode(self):
        mapping = {
            "Normal": QPainter.CompositionMode_SourceOver,
            "Multiply": QPainter.CompositionMode_Multiply,
            "Screen": QPainter.CompositionMode_Screen,
            "Overlay": QPainter.CompositionMode_Overlay,
            "Darken": QPainter.CompositionMode_Darken,
            "Lighten": QPainter.CompositionMode_Lighten,
            "ColorDodge": QPainter.CompositionMode_ColorDodge,
            "ColorBurn": QPainter.CompositionMode_ColorBurn,
            "HardLight": QPainter.CompositionMode_HardLight,
            "SoftLight": QPainter.CompositionMode_SoftLight,
            "Difference": QPainter.CompositionMode_Difference,
            "Exclusion": QPainter.CompositionMode_Exclusion,
            "Additive": QPainter.CompositionMode_Plus,
        }
        return mapping.get(self.overlay_blend_mode, QPainter.CompositionMode_SourceOver)

    def set_overlay_controls_visible(self, visible: bool):
        # Mostra/Nasconde i controlli specifici dell'overlay
        # Nascondi/mostra l'intero gruppo dei controlli overlay come singola azione
        if hasattr(self, 'overlay_action') and self.overlay_action is not None:
            self.overlay_action.setVisible(visible)
        self.action_reset_align.setVisible(visible)
