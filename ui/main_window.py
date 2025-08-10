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
    QCheckBox, QPushButton, QSlider, QDoubleSpinBox, QSpinBox, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtGui import QAction, QPixmap, QImage, QIcon, QColor, QPen, QFontMetrics, QPainter, QCursor
from PySide6.QtCore import Qt, QRect, QPointF, QRectF, QSignalBlocker

from constants import PALETTE_MAP
from .widgets.color_bar_legend import ColorBarLegend
from .widgets.image_graphics_view import ImageGraphicsView


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

        # Prima immagine: ImageGraphicsView per la termica (principale)
        self.image_view = ImageGraphicsView()
        self.image_view.setStyleSheet("border: 1px solid gray; background-color: #333;")
        self.image_view.mouse_moved_on_thermal.connect(self.on_thermal_mouse_move)
        # Set main window reference for ROI drawing
        self.image_view.set_main_window(self)
        self.image_area_layout.addWidget(self.image_view, stretch=1)
        
        # Seconda immagine: ANCHE ImageGraphicsView per l'immagine visibile
        self.secondary_image_view = ImageGraphicsView()
        self.secondary_image_view.setStyleSheet("border: 1px solid gray; background-color: #222;")
        # Also set main window reference for the secondary view
        self.secondary_image_view.set_main_window(self)
        self.image_area_layout.addWidget(self.secondary_image_view, stretch=1)
        
        # Connetti i segnali di zoom/pan tra le due viste
        self.sync_views()
        
        # Tooltip per la temperatura
        self.temp_tooltip_label = QLabel("Temp: --.-- °C")
        self.temp_tooltip_label.setStyleSheet("background-color: black; color: white; padding: 4px; border-radius: 3px;")
        self.temp_tooltip_label.setVisible(False)
        self.temp_tooltip_label.setParent(self.image_view)

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
            line_edit.editingFinished.connect(self.recalculate_and_update_view)  # <--- CAMBIATO
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
        
        # Connect ROI drawing buttons
        self.btn_rect.clicked.connect(self.activate_rect_tool)
        
        _areas_tools.addWidget(self.btn_spot)
        _areas_tools.addWidget(self.btn_rect)
        _areas_tools.addWidget(self.btn_poly)
        _areas_tools.addStretch(1)
        self.tab_areas_layout.addWidget(self.areas_tools_widget)

        # ROI Table
        self.roi_table_group = QGroupBox("ROI Analysis")
        self.roi_table_layout = QVBoxLayout(self.roi_table_group)
        
        # Create the table widget
        self.roi_table = QTableWidget()
        self.roi_table.setColumnCount(6)
        
        # Set column headers
        headers = ["Nome", "Emissivity", "Min (°C)", "Max (°C)", "Avg (°C)", "Median (°C)"]
        self.roi_table.setHorizontalHeaderLabels(headers)
        
        # Configure table properties
        self.roi_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.roi_table.setAlternatingRowColors(True)
        self.roi_table.setSortingEnabled(False)  # Disable sorting to maintain ROI order
        
        # Configure column widths
        header = self.roi_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Nome - stretches to fill space
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Emissivity
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Min
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Max  
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Avg
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Median
        
        # Connect table selection signal
        self.roi_table.itemSelectionChanged.connect(self.on_roi_table_selection_changed)
        self.roi_table.itemChanged.connect(self.on_roi_table_item_changed)
        
        self.roi_table_layout.addWidget(self.roi_table)
        
        # ROI controls
        roi_controls_layout = QHBoxLayout()
        self.btn_delete_roi = QPushButton("Delete ROI")
        self.btn_delete_roi.clicked.connect(self.delete_selected_roi)
        self.btn_clear_all_roi = QPushButton("Clear All ROIs")
        self.btn_clear_all_roi.clicked.connect(self.clear_all_rois)
        roi_controls_layout.addWidget(self.btn_delete_roi)
        roi_controls_layout.addWidget(self.btn_clear_all_roi)
        roi_controls_layout.addStretch()
        self.roi_table_layout.addLayout(roi_controls_layout)
        
        self.tab_areas_layout.addWidget(self.roi_table_group)

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
        # Overlay state (ora gestito da ImageGraphicsView)
        self.overlay_mode = False  # Inizia sempre in modalità normale
        self.overlay_alpha = 0.5
        self.overlay_scale = 1.0
        self.overlay_offset_x = 0.0
        self.overlay_offset_y = 0.0
        self.meta_overlay_scale = 1.0
        self.meta_offset_x = 0.0
        self.meta_offset_y = 0.0
        self.overlay_blend_mode = "Normal"
        
        # Assicurati che la seconda vista sia visibile all'inizio
        self.secondary_image_view.setVisible(True)

        # ROI management attributes
        self.rois = []  # Lista per contenere i modelli ROI (es. RectROI)
        self.roi_items = {}  # Mapping ROI ID -> RectROIItem per accesso rapido
        self.current_drawing_tool = None  # Strumento di disegno attivo
        self.roi_start_pos = None  # Posizione iniziale per il disegno
        self.temp_roi_item = None  # Item temporaneo per feedback visivo durante il disegno
        self.is_drawing_roi = False  # Flag per indicare se siamo in modalità disegno
        self._updating_roi_table = False

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
                self.visible_gray_full = np.array(image_rgb.convert("L"), dtype=np.float32) / 255.0
                data = image_rgb.tobytes("raw", "RGB")
                qimage = QImage(data, image_rgb.width, image_rgb.height, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(qimage)
                self.base_pixmap_visible = pixmap
                
                # Aggiorna le viste - assicurati che non siamo in overlay mode all'inizio
                self.overlay_mode = False  # Forza modalità normale
                self.display_images()  # Questo dovrebbe mostrare entrambe le immagini
            else:
                self.base_pixmap_visible = None
                self.display_images()
                
        except Exception as e:
            print(f"Errore caricamento immagine visibile: {e}")
            self.base_pixmap_visible = None
            self.display_images()

    def recalculate_and_update_view(self):
        """Ricalcola la matrice delle temperatures e aggiorna completamente la vista.
        Da usare quando cambiano i parametri termici."""
        if self.thermal_data is None: 
            return
        print(">>> Ricalcolo temperature e visualizzazione...")
        self.calculate_temperature_matrix()
        self.create_colored_pixmap()
        self.update_legend()
        self.display_images()
        
        # Update ROI analysis after temperature recalculation
        if len(self.rois) > 0:
            print("Updating ROI analysis after temperature recalculation...")
            self.update_roi_analysis()

    def update_view_only(self):
        """Aggiorna solo la visualizzazione usando i dati di temperatura già calcolati.
        Da usare quando cambia solo la palette o l'inversione colori."""
        if self.temperature_data is None:
            return
        print(">>> Aggiornamento solo visualizzazione...")
        self.create_colored_pixmap()
        self.update_legend()
        self.display_images()

    # Mantieni update_analysis per compatibilità con altre parti del codice
    def update_analysis(self):
        """Metodo legacy - preferire recalculate_and_update_view()"""
        self.recalculate_and_update_view()

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
        
        # Aggiorna la vista termica SEMPRE quando si crea una nuova pixmap
        self.display_thermal_image()

    def update_legend(self):
        if self.temperature_data is None:
            return
        self.colorbar.set_palette(self.selected_palette, self.palette_inverted)
        self.colorbar.set_range(self.temp_min, self.temp_max)

    def on_palette_changed(self, idx):
        self.selected_palette = self.palette_combo.currentText()
        self.update_view_only()  # Solo ricolorazione

    def on_invert_palette(self):
        self.palette_inverted = not self.palette_inverted
        self.update_view_only()  # Solo ricolorazione

    # NUOVO METODO: Gestione mouse move sulla mappa termica
    def on_thermal_mouse_move(self, point: QPointF):
        """Slot per gestire il movimento del mouse sulla mappa termica."""
        if self.temperature_data is None:
            self.temp_tooltip_label.setVisible(False)
            return
        
        # Converti le coordinate in indici della matrice
        img_h, img_w = self.temperature_data.shape
        matrix_x = int(point.x())
        matrix_y = int(point.y())
        
        if 0 <= matrix_x < img_w and 0 <= matrix_y < img_h:
            temperature = self.temperature_data[matrix_y, matrix_x]
            if not np.isnan(temperature):
                self.temp_tooltip_label.setText(f"{temperature:.2f} °C")
                
                # Posiziona il tooltip vicino al cursore
                cursor_pos = self.image_view.mapFromGlobal(self.cursor().pos())
                self.temp_tooltip_label.move(cursor_pos.x() + 10, cursor_pos.y() + 10)
                self.temp_tooltip_label.setVisible(True)
                self.temp_tooltip_label.adjustSize()
                return
        
        self.temp_tooltip_label.setVisible(False)

    # METODI MODIFICATI: Gestione immagini
    def display_images(self):
        """Aggiorna la visualizzazione delle immagini nella vista."""
        if self.overlay_mode:
            # Assicurati che l'immagine visibile sia impostata nell'ImageGraphicsView
            if self.base_pixmap_visible is not None:
                self.image_view.set_visible_pixmap(self.base_pixmap_visible)
            
            # Attiva la modalità overlay
            offset = QPointF(self.overlay_offset_x, self.overlay_offset_y)
            blend_mode = self.get_qt_composition_mode()
            
            self.image_view.update_overlay(
                visible=True,
                alpha=self.overlay_alpha,
                scale=self.overlay_scale,
                offset=offset,
                blend_mode=blend_mode
            )
            # Nascondi la seconda vista quando in overlay
            self.secondary_image_view.setVisible(False)
        else:
            # In modalità normale, mostra le immagini separate
            self.image_view.update_overlay(visible=False)
            self.display_secondary_image()  # Assicurati che questo venga chiamato
            self.secondary_image_view.setVisible(True)  # Assicurati che sia visibile
    
    def display_thermal_image(self):
        """Imposta l'immagine termica nella vista."""
        if self.base_pixmap is not None:
            self.image_view.set_thermal_pixmap(self.base_pixmap)
    
    def display_secondary_image(self):
        """Imposta l'immagine visibile nella seconda vista."""
        print(f"display_secondary_image called, pixmap available: {self.base_pixmap_visible is not None}")
        if self.base_pixmap_visible is not None:
            self.secondary_image_view.set_thermal_pixmap(self.base_pixmap_visible)
            print(f"Secondary view pixmap set, size: {self.base_pixmap_visible.size()}")
        else:
            self.secondary_image_view.set_thermal_pixmap(QPixmap())
            print("Secondary view cleared")

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
        
        # Aggiorna la vista termica SEMPRE quando si crea una nuova pixmap
        self.display_thermal_image()

    # METODI SEMPLIFICATI: Zoom e Pan
    def zoom_in(self):
        self.image_view.zoom_in()
        if hasattr(self, 'secondary_image_view'):
            self.secondary_image_view.zoom_in()

    def zoom_out(self):
        self.image_view.zoom_out()
        if hasattr(self, 'secondary_image_view'):
            self.secondary_image_view.zoom_out()

    def zoom_reset(self):
        self.image_view.reset_zoom()
        if hasattr(self, 'secondary_image_view'):
            self.secondary_image_view.reset_zoom()

    # METODI DA RIMUOVERE O SEMPLIFICARE:
    # - image_mouse_move_event
    # - image_mouse_press
    # - image_mouse_release  
    # - secondary_image_mouse_move_event
    # - display_overlay_image (logica ora in ImageGraphicsView)
    # - Tutta la logica manuale di calcolo coordinate e canvas

    # METODI MODIFICATI: Overlay controls
    def on_overlay_toggled(self, checked: bool):
        self.overlay_mode = checked
        self.set_overlay_controls_visible(checked)
        
        # Se stiamo attivando l'overlay e c'è un'immagine visibile, impostala
        if checked and self.base_pixmap_visible is not None:
            self.image_view.set_visible_pixmap(self.base_pixmap_visible)
        
        self.display_images()

    def on_overlay_alpha_changed(self, value: int):
        self.overlay_alpha = max(0.0, min(1.0, value / 100.0))
        if self.overlay_mode:
            self.display_images()

    def on_scale_spin_changed(self, value: float):
        self.overlay_scale = float(value)
        if self.overlay_mode:
            self.display_images()
            # Debug: stampa informazioni sulla scala
            if hasattr(self.image_view, 'get_scale_info'):
                scale_info = self.image_view.get_scale_info()
                print(f"Scale info: {scale_info}")

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
            # Aggiorna solo il blend mode senza cambiare altro
            blend_mode = self.get_qt_composition_mode()
            offset = QPointF(self.overlay_offset_x, self.overlay_offset_y)
            
            self.image_view.update_overlay(
                visible=True,
                alpha=self.overlay_alpha,
                scale=self.overlay_scale,
                offset=offset,
                blend_mode=blend_mode
            )

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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Ridimensiona l'immagine visibile quando la finestra viene ridimensionata
        if hasattr(self, 'secondary_image_view') and self.base_pixmap_visible is not None:
            self.display_secondary_image()

    def sync_views(self):
        """Sincronizza zoom e pan tra le due ImageGraphicsView."""
        self.image_view.view_transformed.connect(self.on_primary_view_transformed)
        self.secondary_image_view.view_transformed.connect(self.on_secondary_view_transformed)
        
    def on_primary_view_transformed(self, zoom_factor: float, pan_offset: QPointF, pixmap_size: tuple):
        """Sincronizza la vista secondaria quando cambia quella primaria."""
        if hasattr(self, 'secondary_image_view') and self.secondary_image_view.isVisible():
            self.secondary_image_view.sync_transform(zoom_factor, pan_offset, pixmap_size)
            
    def on_secondary_view_transformed(self, zoom_factor: float, pan_offset: QPointF, pixmap_size: tuple):
        """Sincronizza la vista primaria quando cambia quella secondaria."""
        if self.image_view.isVisible():
            self.image_view.sync_transform(zoom_factor, pan_offset, pixmap_size)

    # === ROI Table Methods ===
    
    def update_roi_analysis(self):
        """
        Aggiorna l'analisi dei ROI dopo la creazione o modifica.
        Itera sulla lista self.rois e calcola le statistiche per ogni ROI.
        """
        import numpy as np
        print(f"Updating ROI analysis for {len(self.rois)} ROIs...")
        
        # Iterate through all ROIs and calculate statistics
        for roi_model in self.rois:
            temps = self.compute_roi_temperatures(roi_model)
            if temps is not None:
                valid = temps[~np.isnan(temps)]
                if valid.size > 0:
                    roi_model.temp_min = float(np.min(valid))
                    roi_model.temp_max = float(np.max(valid))
                    roi_model.temp_mean = float(np.mean(valid))
                    roi_model.temp_std = float(np.std(valid))
                else:
                    roi_model.temp_min = roi_model.temp_max = roi_model.temp_mean = roi_model.temp_std = None
            else:
                roi_model.temp_min = roi_model.temp_max = roi_model.temp_mean = roi_model.temp_std = None
        
        # Update the ROI table with new data
        self.update_roi_table()
        
        print(f"ROI analysis completed. Total ROIs: {len(self.rois)}")

    def update_roi_table(self):
        """
        Aggiorna la tabella dei ROI con i dati correnti.
        Cancella tutte le righe esistenti e poi popola la tabella con i dati aggiornati.
        """
        print("Updating ROI table...")
        self._updating_roi_table = True
        try:
            # blocca tutti i segnali della tabella durante l’aggiornamento
            blocker = QSignalBlocker(self.roi_table)

            self.roi_table.setRowCount(0)
            self.roi_table.clearContents()
            self.roi_table.setRowCount(len(self.rois))

            for row, roi in enumerate(self.rois):
                name_item = QTableWidgetItem(roi.name)
                name_item.setData(Qt.UserRole, roi.id)
                self.roi_table.setItem(row, 0, name_item)

                emissivity_value = getattr(roi, 'emissivity', 0.95)
                emissivity_item = QTableWidgetItem(f"{emissivity_value:.3f}")
                self.roi_table.setItem(row, 1, emissivity_item)

                if (hasattr(roi, 'temp_min') and roi.temp_min is not None and 
                    hasattr(roi, 'temp_max') and roi.temp_max is not None and
                    hasattr(roi, 'temp_mean') and roi.temp_mean is not None):
                    min_item = QTableWidgetItem(f"{roi.temp_min:.2f}")
                    max_item = QTableWidgetItem(f"{roi.temp_max:.2f}")
                    avg_item = QTableWidgetItem(f"{roi.temp_mean:.2f}")
                    median_value = self.calculate_roi_median(roi)
                    median_item = QTableWidgetItem(f"{median_value:.2f}" if median_value is not None else "N/A")
                else:
                    min_item = QTableWidgetItem("N/A")
                    max_item = QTableWidgetItem("N/A")
                    avg_item = QTableWidgetItem("N/A")
                    median_item = QTableWidgetItem("N/A")

                for item in [min_item, max_item, avg_item, median_item]:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    item.setBackground(QColor(240, 240, 240))

                self.roi_table.setItem(row, 2, min_item)
                self.roi_table.setItem(row, 3, max_item)
                self.roi_table.setItem(row, 4, avg_item)
                self.roi_table.setItem(row, 5, median_item)

            print(f"ROI table updated with {len(self.rois)} rows")
        finally:
            # rilascia il blocker e riabilita i segnali
            del blocker
            self._updating_roi_table = False

    def calculate_roi_median(self, roi):
        """Calcola la mediana delle temperature per un ROI."""
        import numpy as np
        temps = self.compute_roi_temperatures(roi)
        if temps is None:
            return None
        valid = temps[~np.isnan(temps)]
        if valid.size == 0:
            return None
        return float(np.median(valid))

    def on_roi_table_selection_changed(self):
        """Gestisce il cambio di selezione nella tabella ROI."""
        current_row = self.roi_table.currentRow()
        if current_row >= 0 and current_row < len(self.rois):
            roi = self.rois[current_row]
            
            # Highlight the corresponding ROI item in the graphics view
            if roi.id in self.roi_items:
                roi_item = self.roi_items[roi.id]
                # Clear previous selection
                for item in self.image_view._scene.selectedItems():
                    item.setSelected(False)
                # Select current ROI
                roi_item.setSelected(True)
                # Center view on ROI
                self.image_view.centerOn(roi_item)

    def on_roi_table_item_changed(self, item):
        """Gestisce le modifiche agli elementi della tabella."""
        if item is None or self._updating_roi_table:
            return
            
        row = item.row()
        col = item.column()
        
        if row >= len(self.rois):
            return
            
        roi = self.rois[row]
        
        if col == 0:  # Nome
            # Update ROI name
            new_name = item.text().strip()
            if new_name:
                roi.name = new_name
                print(f"Updated ROI name to: {new_name}")
            else:
                # Revert to previous name if empty
                item.setText(roi.name)
                
        elif col == 1:  # Emissivity
            try:
                new_emissivity = float(item.text())
                if 0.0 <= new_emissivity <= 1.0:
                    roi.emissivity = new_emissivity
                    print(f"Updated ROI emissivity to: {new_emissivity}")
                    # Ricalcola statistiche con emissività per-ROI
                    self.update_roi_analysis()
                else:
                    # Invalid range, revert
                    emissivity_value = getattr(roi, 'emissivity', 0.95)
                    item.setText(f"{emissivity_value:.3f}")
                    QMessageBox.warning(self, "Invalid Emissivity", 
                                      "Emissivity must be between 0.0 and 1.0")
            except ValueError:
                # Invalid number, revert
                emissivity_value = getattr(roi, 'emissivity', 0.95)
                item.setText(f"{emissivity_value:.3f}")
                QMessageBox.warning(self, "Invalid Emissivity", 
                                  "Please enter a valid number for emissivity")

    def delete_selected_roi(self):
        """Elimina il ROI selezionato dalla tabella."""
        current_row = self.roi_table.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "No Selection", "Please select a ROI to delete.")
            return
            
        if current_row >= len(self.rois):
            return
            
        roi = self.rois[current_row]
        
        # Remove from scene
        if roi.id in self.roi_items:
            roi_item = self.roi_items[roi.id]
            self.image_view._scene.removeItem(roi_item)
            del self.roi_items[roi.id]
        
        # Remove from model list
        self.rois.pop(current_row)
        
        # Update analysis after deletion
        self.update_roi_analysis()
        
        print(f"Deleted ROI: {roi.name}")

    def clear_all_rois(self):
        """Rimuove tutti i ROI."""
        if not self.rois:
            return
            
        # Confirm deletion
        reply = QMessageBox.question(self, "Clear All ROIs", 
                                   "Are you sure you want to delete all ROIs?",
                                   QMessageBox.Yes | QMessageBox.No,
                                   QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            # Remove all items from scene
            for roi_item in self.roi_items.values():
                self.image_view._scene.removeItem(roi_item)
            
            # Clear collections
            self.rois.clear()
            self.roi_items.clear()
            
            # Update analysis after clearing all ROIs
            self.update_roi_analysis()
            
            print("Cleared all ROIs")

    def activate_rect_tool(self):
        self.current_drawing_tool = "rect"
        if hasattr(self, "image_view"):
            self.image_view.setCursor(Qt.CrossCursor)

    def deactivate_drawing_tools(self):
        self.current_drawing_tool = None
        if hasattr(self, "image_view"):
            self.image_view.setCursor(Qt.ArrowCursor)

    def compute_roi_temperatures(self, roi):
        import numpy as np
        if self.thermal_data is None or not hasattr(self, "image_view"):
            return None

        # Mappa i due angoli del ROI dalle coordinate di scena a quelle dell'item termico (pixel)
        tl_scene = QPointF(float(roi.x), float(roi.y))
        br_scene = QPointF(float(roi.x + roi.width), float(roi.y + roi.height))
        tl_img = self.image_view._thermal_item.mapFromScene(tl_scene)
        br_img = self.image_view._thermal_item.mapFromScene(br_scene)

        x1 = int(np.floor(min(tl_img.x(), br_img.x())))
        y1 = int(np.floor(min(tl_img.y(), br_img.y())))
        x2 = int(np.ceil(max(tl_img.x(), br_img.x())))
        y2 = int(np.ceil(max(tl_img.y(), br_img.y())))

        # Clamp ai limiti dell’immagine
        h, w = self.thermal_data.shape
        x1, x2 = max(0, x1), min(w, x2)
        y1, y2 = max(0, y1), min(h, y2)
        if x1 >= x2 or y1 >= y2:
            return None

        thermal_roi = self.thermal_data[y1:y2, x1:x2].astype(np.float64)

        # Parametri e emissività per-ROI
        emissivity = float(getattr(roi, 'emissivity', 0.95))
        refl_temp_C = float(self.param_inputs["ReflectedApparentTemperature"].text())
        R1 = float(self.param_inputs["PlanckR1"].text())
        R2 = float(self.param_inputs["PlanckR2"].text())
        B  = float(self.param_inputs["PlanckB"].text())
        F  = float(self.param_inputs["PlanckF"].text())
        O  = float(self.param_inputs["PlanckO"].text())

        # Stessa formula del globale, ma sul blocco ROI con emissività del ROI
        refl_temp_K = refl_temp_C + 273.15
        raw_refl = R1 / (R2 * (np.exp(B / refl_temp_K) - F)) - O
        raw_obj = (thermal_roi - (1 - emissivity) * raw_refl) / max(emissivity, 1e-6)  # evita div/0

        log_arg = R1 / (R2 * (raw_obj + O)) + F
        temp_K = np.full(log_arg.shape, np.nan, dtype=np.float64)
        valid = log_arg > 0
        temp_K[valid] = B / np.log(log_arg[valid])
        return temp_K - 273.15
