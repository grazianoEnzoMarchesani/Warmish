import sys
import json
import io
import os  # AGGIUNGO QUESTO IMPORT
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
        self.secondary_image_view.set_allow_roi_drawing(False)
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
        param_keys = ["Emissivity", "ObjectDistance", "ReflectedApparentTemperature", "PlanckR1", "PlanckR2", "PlanckB", "PlanckF", "PlanckO", "AtmosphericTemperature", "AtmosphericTransmission", "RelativeHumidity"]
        for key in param_keys:
            line_edit = QLineEdit()
            line_edit.editingFinished.connect(self.recalculate_and_update_view)  # <--- CAMBIATO
            self.param_inputs[key] = line_edit
            self.params_layout.addRow(key, self.param_inputs[key])
        
        # Pulsante per reset ai valori EXIF
        self.reset_params_button = QPushButton("Reset to EXIF values")
        self.reset_params_button.setToolTip("Ripristina tutti i parametri ai valori estratti dai metadati EXIF\n" +
                                           "Usa valori di default per parametri non disponibili")
        self.reset_params_button.clicked.connect(self.reset_params_to_exif)
        self.params_layout.addRow("", self.reset_params_button)
        
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
        
        # Rendi i pulsanti checkable per feedback visivo
        self.btn_spot.setCheckable(True)
        self.btn_rect.setCheckable(True)
        self.btn_poly.setCheckable(True)
        
        # Connect ROI drawing buttons
        self.btn_rect.clicked.connect(self.activate_rect_tool)
        self.btn_spot.clicked.connect(self.activate_spot_tool)
        self.btn_poly.clicked.connect(self.activate_polygon_tool)
        
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
        self.roi_table.setSelectionMode(QTableWidget.MultiSelection)  # Aggiungi questa riga
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
        
        # Opzioni label ROI
        label_opts_layout = QHBoxLayout()
        label_opts_layout.addWidget(QLabel("Show in labels:"))

        self.roi_label_settings = {
            "name": True,
            "emissivity": True,
            "min": True,
            "max": True,
            "avg": True,
            "median": False,
        }

        self.cb_label_name  = QCheckBox("Name");    self.cb_label_name.setChecked(self.roi_label_settings["name"])
        self.cb_label_eps   = QCheckBox("ε");       self.cb_label_eps.setChecked(self.roi_label_settings["emissivity"])
        self.cb_label_min   = QCheckBox("Min");     self.cb_label_min.setChecked(self.roi_label_settings["min"])
        self.cb_label_max   = QCheckBox("Max");     self.cb_label_max.setChecked(self.roi_label_settings["max"])
        self.cb_label_avg   = QCheckBox("Avg");     self.cb_label_avg.setChecked(self.roi_label_settings["avg"])
        self.cb_label_med   = QCheckBox("Median");  self.cb_label_med.setChecked(self.roi_label_settings["median"])

        for cb in [self.cb_label_name, self.cb_label_eps, self.cb_label_min,
                   self.cb_label_max, self.cb_label_avg, self.cb_label_med]:
            cb.toggled.connect(self.on_label_settings_changed)
            label_opts_layout.addWidget(cb)

        label_opts_layout.addStretch()
        self.roi_table_layout.addLayout(label_opts_layout)

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
        
        # Salvataggio automatico
        self.current_image_path = None  # Percorso del file JPG correntemente aperto
        self._ignore_auto_save = False  # Flag per evitare salvataggi durante il caricamento

    def reset_application_state(self):
        """Resetta completamente lo stato dell'applicazione prima di caricare una nuova immagine."""
        try:
            self._ignore_auto_save = True  # Previeni salvataggi durante il reset
            
            print("Resettando stato dell'applicazione...")
            
            # 1. Pulisci tutti i ROI esistenti
            self.clear_all_rois()
            
            # 2. Reset palette ai valori di default
            self.palette_combo.setCurrentText("Iron")
            self.selected_palette = "Iron"
            self.palette_inverted = False
            
            # 3. Reset parametri termici ai valori di default (saranno poi sovrascritti dagli EXIF)
            default_values = {
                "Emissivity": "0.950000",
                "ObjectDistance": "1.0000",
                "ReflectedApparentTemperature": "20.0000",
                "AtmosphericTemperature": "20.0000",
                "AtmosphericTransmission": "0.950000",
                "RelativeHumidity": "50.0000",
                "PlanckR1": "",
                "PlanckR2": "",
                "PlanckB": "",
                "PlanckF": "",
                "PlanckO": ""
            }
            
            for param, default_value in default_values.items():
                if param in self.param_inputs:
                    self.param_inputs[param].blockSignals(True)
                    self.param_inputs[param].setText(default_value)
                    self.param_inputs[param].setStyleSheet("")  # Rimuovi colorazioni speciali
                    self.param_inputs[param].blockSignals(False)
            
            # 4. Reset impostazioni overlay ai valori di default
            if hasattr(self, 'scale_spin'):
                self.scale_spin.blockSignals(True)
                self.scale_spin.setValue(1.0)
                self.scale_spin.blockSignals(False)
                self.overlay_scale = 1.0
            
            if hasattr(self, 'offsetx_spin'):
                self.offsetx_spin.blockSignals(True)
                self.offsetx_spin.setValue(0)
                self.offsetx_spin.blockSignals(False)
                self.overlay_offset_x = 0.0
            
            if hasattr(self, 'offsety_spin'):
                self.offsety_spin.blockSignals(True)
                self.offsety_spin.setValue(0)
                self.offsety_spin.blockSignals(False)
                self.overlay_offset_y = 0.0
            
            if hasattr(self, 'overlay_alpha_slider'):
                self.overlay_alpha_slider.blockSignals(True)
                self.overlay_alpha_slider.setValue(50)
                self.overlay_alpha_slider.blockSignals(False)
                self.overlay_alpha = 0.5
            
            if hasattr(self, 'blend_combo'):
                self.blend_combo.blockSignals(True)
                self.blend_combo.setCurrentText("Normal")
                self.blend_combo.blockSignals(False)
                self.overlay_blend_mode = "Normal"
            
            # 5. Disattiva modalità overlay
            if hasattr(self, 'action_overlay_view'):
                self.action_overlay_view.setChecked(False)
                self.overlay_mode = False
            
            # 6. Reset valori meta overlay
            self.meta_overlay_scale = 1.0
            self.meta_offset_x = 0.0
            self.meta_offset_y = 0.0
            
            print("Reset stato completato")
            
        except Exception as e:
            print(f"Errore durante il reset dello stato: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._ignore_auto_save = False

    def open_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Seleziona Immagine FLIR", "", "Immagini JPEG (*.jpg *.jpeg)")
        if not file_path: return

        # Salva il percorso del file corrente
        self.current_image_path = file_path
        
        # AGGIUNTA IMPORTANTE: Reset completo dello stato dell'applicazione
        self.reset_application_state()

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
            
            # Popola i parametri dagli EXIF (questo sovrascriverà i valori di default del reset)
            self.populate_params()

            command = ["exiftool", "-b", "-RawThermalImage", file_path]
            result = subprocess.run(command, capture_output=True, check=True)
            raw_thermal_bytes = result.stdout
            if not raw_thermal_bytes: raise ValueError("Dati termici binari non estratti.")

            image_type = self.metadata.get("APP1:RawThermalImageType", "Unknown")
            if image_type == "PNG":
                self.thermal_data = np.array(Image.open(io.BytesIO(raw_thermal_bytes)))
                self.thermal_data.byteswap(inplace=True)
            else:
                width = self.metadata.get('APP1:RawThermalImageWidth')
                height = self.metadata.get('APP1:RawThermalImageHeight')
                if not width or not height: raise ValueError("Dimensioni immagine non trovate.")
                self.thermal_data = np.frombuffer(raw_thermal_bytes, dtype=np.uint16).reshape((height, width))

            self.update_analysis()
            
            # IMPORTANTE: Carica le impostazioni dal JSON DOPO aver fatto il reset e popolato gli EXIF
            # Così se il JSON esiste sovrascrive il reset, altrimenti rimane lo stato pulito
            self.load_settings_from_json()
            
            # Connetti i segnali per l'auto-salvataggio (solo una volta)
            if not hasattr(self, '_auto_save_connected'):
                self.connect_auto_save_signals()
                self._auto_save_connected = True

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
        
        # Valori di default per parametri ambientali
        default_values = {
            "AtmosphericTemperature": 20.0,
            "AtmosphericTransmission": 0.95,  # Valore standard per distanze brevi (0-10m)
            "RelativeHumidity": 50.0,
            "ObjectDistance": 1.0,
            "Emissivity": 0.95
        }
        
        for key, line_edit in self.param_inputs.items():
            value = self.metadata.get(f"APP1:{key}", self.metadata.get(key, "N/A"))
            
            # Se il valore è N/A, usa il default se disponibile
            if value == "N/A" and key in default_values:
                value = default_values[key]
                line_edit.setStyleSheet("background-color: #fff3cd;")  # Sfondo giallo per indicare valore di default
                line_edit.setToolTip(f"Valore di default utilizzato: {value}")
            else:
                line_edit.setStyleSheet("")  # Reset dello stile
                line_edit.setToolTip("")
            
            # Applica la precisione appropriata
            if isinstance(value, (int, float)) and value != "N/A":
                if key in ["PlanckR1", "PlanckR2", "PlanckB", "PlanckF", "PlanckO"]:
                    line_edit.setText(f"{float(value):.12f}")
                elif key in ["Emissivity", "ReflectedApparentTemperature", "AtmosphericTransmission"]:
                    line_edit.setText(f"{float(value):.6f}")
                else:
                    line_edit.setText(f"{float(value):.4f}")
            else:
                line_edit.setText(str(value))

    def reset_params_to_exif(self):
        """
        Ripristina tutti i parametri di calcolo ai valori estratti dai metadati EXIF.
        Usa valori di default appropriati per parametri non disponibili.
        """
        if not hasattr(self, 'metadata') or not self.metadata:
            # Se non ci sono metadati, usa solo i valori di default
            self._apply_default_values()
            return
        
        # Valori di default per parametri ambientali e altri
        default_values = {
            "AtmosphericTemperature": 20.0,
            "AtmosphericTransmission": 0.95,  # Valore standard per distanze brevi
            "RelativeHumidity": 50.0,
            "ObjectDistance": 1.0,
            "Emissivity": 0.95
        }
        
        reset_count = 0
        default_count = 0
        
        for key, line_edit in self.param_inputs.items():
            # Cerca il valore nei metadati EXIF
            exif_value = self.metadata.get(f"APP1:{key}", self.metadata.get(key))
            
            if exif_value is not None and exif_value != "N/A":
                # Valore trovato nei metadati EXIF
                if isinstance(exif_value, (int, float)):
                    if key in ["PlanckR1", "PlanckR2", "PlanckB", "PlanckF", "PlanckO"]:
                        line_edit.setText(f"{float(exif_value):.12f}")
                    elif key in ["Emissivity", "ReflectedApparentTemperature", "AtmosphericTransmission"]:
                        line_edit.setText(f"{float(exif_value):.6f}")
                    else:
                        line_edit.setText(f"{float(exif_value):.4f}")
                else:
                    line_edit.setText(str(exif_value))
                
                line_edit.setStyleSheet("")  # Reset dello stile
                line_edit.setToolTip(f"Valore da metadati EXIF: {exif_value}")
                reset_count += 1
                
            elif key in default_values:
                # Usa valore di default per parametri non disponibili nei metadati
                default_value = default_values[key]
                if key in ["Emissivity", "AtmosphericTransmission"]:
                    line_edit.setText(f"{default_value:.6f}")
                else:
                    line_edit.setText(f"{default_value:.4f}")
                
                line_edit.setStyleSheet("background-color: #fff3cd;")  # Sfondo giallo per default
                line_edit.setToolTip(f"Valore di default utilizzato: {default_value}\n(Non disponibile nei metadati EXIF)")
                default_count += 1
            else:
                # Parametro non trovato e senza default
                line_edit.setText("N/A")
                line_edit.setStyleSheet("background-color: #f8d7da;")  # Sfondo rosso per errore
                line_edit.setToolTip("Parametro non disponibile nei metadati EXIF")
        
        # Mostra un messaggio di conferma
        print(f"Reset parametri completato:")
        print(f"  - {reset_count} parametri ripristinati da metadati EXIF")
        print(f"  - {default_count} parametri impostati ai valori di default")
        
        # Ricalcola la temperatura con i nuovi parametri
        self.recalculate_and_update_view()

    def _apply_default_values(self):
        """
        Applica solo i valori di default quando non ci sono metadati disponibili.
        """
        default_values = {
            "Emissivity": 0.95,
            "ObjectDistance": 1.0,
            "ReflectedApparentTemperature": 20.0,
            "AtmosphericTemperature": 20.0,
            "AtmosphericTransmission": 0.95,
            "RelativeHumidity": 50.0,
            # I parametri di Planck non hanno default universali
        }
        
        for key, line_edit in self.param_inputs.items():
            if key in default_values:
                default_value = default_values[key]
                if key in ["Emissivity", "AtmosphericTransmission"]:
                    line_edit.setText(f"{default_value:.6f}")
                else:
                    line_edit.setText(f"{default_value:.4f}")
                line_edit.setStyleSheet("background-color: #fff3cd;")
                line_edit.setToolTip(f"Valore di default: {default_value}")
            else:
                line_edit.setText("N/A")
                line_edit.setStyleSheet("background-color: #f8d7da;")
                line_edit.setToolTip("Parametro non disponibile")
        
        print("Applicati valori di default (nessun metadato EXIF disponibile)")

    def apply_environmental_correction(self, temp_data):
        """
        Applica correzioni ambientali per migliorare l'accuratezza della temperatura.
        Basato su parametri ambientali estratti dai metadati FLIR.
        """
        try:
            # Controllo input
            if temp_data is None or np.all(np.isnan(temp_data)):
                print("⚠️ AVVISO: Dati temperatura non validi in input alla correzione ambientale")
                return temp_data
            
            # Estrai parametri ambientali con valori standard appropriati
            atmospheric_temp = self._get_float_param("AtmosphericTemperature", 20.0)
            atmospheric_transmission = self._get_float_param("AtmosphericTransmission", 0.95)  # Valore standard per distanze brevi
            relative_humidity = self._get_float_param("RelativeHumidity", 50.0)
            
            # Verifica che i parametri siano validi
            if not all(np.isfinite([atmospheric_temp, atmospheric_transmission, relative_humidity])):
                print("⚠️ AVVISO: Parametri ambientali non validi - correzione saltata")
                return temp_data
            
            # Correzione per temperatura atmosferica (compensazione deriva termica)
            temp_correction = (atmospheric_temp - 20.0) * 0.0005  # 0.05% per grado di differenza da 20°C
            
            # Correzione per trasmissione atmosferica
            transmission_correction = (1.0 - atmospheric_transmission) * 0.002
            
            # Correzione per umidità relativa
            humidity_correction = (relative_humidity - 50.0) * 0.00002  # Effetto minimo ma presente
            
            # Applica correzioni cumulative
            total_correction = temp_correction + transmission_correction + humidity_correction
            corrected_temp = temp_data + total_correction
            
            # Debug: mostra le correzioni applicate (solo se significative)
            if abs(total_correction) > 0.001:
                print(f"Correzioni ambientali applicate:")
                print(f"  - Temperatura atmosferica: {temp_correction:.6f}°C")
                print(f"  - Trasmissione atmosferica: {transmission_correction:.6f}°C") 
                print(f"  - Umidità relativa: {humidity_correction:.6f}°C")
                print(f"  - Correzione totale: {total_correction:.6f}°C")
            
            return corrected_temp
            
        except Exception as e:
            print(f"Avviso: Correzione ambientale non applicata - {e}")
            return temp_data

    def _get_float_param(self, param_name, default_value):
        """
        Ottiene un parametro float dall'interfaccia utente o dai metadati,
        gestendo correttamente i valori "N/A".
        """
        try:
            # Prima prova dall'interfaccia utente
            if param_name in self.param_inputs:
                ui_value = self.param_inputs[param_name].text().strip()
                if ui_value and ui_value != "N/A":
                    return float(ui_value)
            
            # Poi prova dai metadati
            if hasattr(self, 'metadata') and self.metadata:
                meta_value = self.metadata.get(f"APP1:{param_name}", 
                                             self.metadata.get(param_name))
                if meta_value is not None and meta_value != "N/A":
                    return float(meta_value)
            
            # Se tutto fallisce, usa il valore di default
            return float(default_value)
            
        except (ValueError, TypeError):
            return float(default_value)

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
            
            # Debug: controlla i parametri
            print(f"🔍 Debug parametri Planck:")
            print(f"  R1={R1}, R2={R2}, B={B}, F={F}, O={O}")
            print(f"  Emissivity={emissivity}, ReflTemp={refl_temp_C}°C")
            
            raw_refl = R1 / (R2 * (np.exp(B / refl_temp_K) - F)) - O
            print(f"  raw_refl range: {np.nanmin(raw_refl):.3f} to {np.nanmax(raw_refl):.3f}")
            
            raw_obj = (self.thermal_data - (1 - emissivity) * raw_refl) / max(emissivity, 1e-6)
            print(f"  raw_obj range: {np.nanmin(raw_obj):.3f} to {np.nanmax(raw_obj):.3f}")
            
            log_arg = R1 / (R2 * (raw_obj + O)) + F
            print(f"  log_arg range: {np.nanmin(log_arg):.3f} to {np.nanmax(log_arg):.3f}")
            
            # Controllo condizioni per logaritmo
            valid_indices = log_arg > 0
            valid_count = np.sum(valid_indices)
            total_count = log_arg.size
            print(f"  Pixel validi per logaritmo: {valid_count}/{total_count} ({100*valid_count/total_count:.1f}%)")
            
            if valid_count == 0:
                print("❌ ERRORE: Nessun pixel ha log_arg > 0 - tutti i valori saranno NaN!")
                print("   Possibili cause:")
                print("   - Parametri di Planck incorretti")
                print("   - Emissività troppo bassa")
                print("   - Dati termici grezzi corrotti")
            
            temp_K = np.full(log_arg.shape, np.nan, dtype=np.float64)
            valid_indices = log_arg > 0
            temp_K[valid_indices] = B / np.log(log_arg[valid_indices])
            
            print(f"  temp_K range: {np.nanmin(temp_K):.3f} to {np.nanmax(temp_K):.3f}")

            # Conversione a Celsius
            temp_celsius = temp_K - 273.15
            
            # Applica correzione ambientale
            self.temperature_data = self.apply_environmental_correction(temp_celsius)
            
            # Controllo validità dei dati calcolati
            if np.all(np.isnan(self.temperature_data)):
                print("⚠️ AVVISO: Tutti i valori di temperatura sono NaN - possibile problema nei parametri")
                print("Controllo parametri di Planck e emissività")
                # Fallback ai dati grezzi
                self.temperature_data = self.thermal_data.astype(float) / 100.0  # Semplice conversione
                self.temp_min = np.nanmin(self.temperature_data)
                self.temp_max = np.nanmax(self.temperature_data)
            elif np.any(np.isfinite(self.temperature_data)):
                # Calcola min/max solo sui valori finiti
                finite_data = self.temperature_data[np.isfinite(self.temperature_data)]
                if len(finite_data) > 0:
                    self.temp_min = np.min(finite_data)
                    self.temp_max = np.max(finite_data)
                else:
                    self.temp_min, self.temp_max = 0, 100  # Default range
            else:
                self.temp_min, self.temp_max = 0, 100  # Default range
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
        self.save_settings_to_json()

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
                # Ottieni l'emissività dai parametri
                try:
                    emissivity = float(self.param_inputs["Emissivity"].text())
                    self.temp_tooltip_label.setText(f"{temperature:.2f} °C | ε: {emissivity:.3f}")
                except (ValueError, KeyError):
                    # Fallback se non riesce a leggere l'emissività
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
                    roi_model.temp_median = float(np.median(valid))
                else:
                    roi_model.temp_min = roi_model.temp_max = roi_model.temp_mean = roi_model.temp_std = roi_model.temp_median = None
            else:
                roi_model.temp_min = roi_model.temp_max = roi_model.temp_mean = roi_model.temp_std = roi_model.temp_median = None
        
        # Update the ROI table with new data
        self.update_roi_table()
        
        # Update label for each ROI after calculating stats
        for roi_model in self.rois:
            item = self.roi_items.get(roi_model.id)
            if item and hasattr(item, "refresh_label"):
                item.refresh_label()

        print(f"ROI analysis completed. Total ROIs: {len(self.rois)}")

    def update_roi_table(self):
        """
        Aggiorna la tabella dei ROI con i dati correnti.
        Cancella tutte le righe esistenti e poi popola la tabella con i dati aggiornati.
        """
        print("Updating ROI table...")
        self._updating_roi_table = True
        try:
            # blocca tutti i segnali della tabella durante l'aggiornamento
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
                    median_value = getattr(roi, 'temp_median', None)
                    if median_value is None:
                        median_value = self.calculate_roi_median(roi)
                    median_item = QTableWidgetItem(f"{median_value:.2f}" if median_value is not None else "N/A")
                else:
                    min_item = QTableWidgetItem("N/A")
                    max_item = QTableWidgetItem("N/A")
                    avg_item = QTableWidgetItem("N/A")
                    median_item = QTableWidgetItem("N/A")

                for item in [min_item, max_item, avg_item, median_item]:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    # Rimozione del colore di sfondo hardcoded per supportare il tema scuro
                    # item.setBackground(QColor(240, 240, 240))  # Commentato
                    
                    # Usa il colore di sistema per elementi disabilitati
                    from PySide6.QtWidgets import QApplication
                    palette = QApplication.palette()
                    disabled_color = palette.color(palette.ColorRole.Window)
                    item.setBackground(disabled_color)

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

        # Update label for the specific ROI item
        item_view = self.roi_items.get(roi.id)
        if item_view and hasattr(item_view, "refresh_label"):
            item_view.refresh_label()

    def delete_selected_roi(self):
        """Elimina tutti i ROI selezionati dalla tabella."""
        # Ottieni tutte le righe selezionate
        selected_rows = []
        for item in self.roi_table.selectedItems():
            row = item.row()
            if row not in selected_rows:
                selected_rows.append(row)
        
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select one or more ROIs to delete.")
            return
        
        # Ordina le righe in ordine decrescente per evitare problemi con gli indici durante la cancellazione
        selected_rows.sort(reverse=True)
        
        # Conferma la cancellazione se ci sono più elementi
        if len(selected_rows) > 1:
            reply = QMessageBox.question(self, "Delete Multiple ROIs", 
                                       f"Are you sure you want to delete {len(selected_rows)} ROIs?",
                                       QMessageBox.Yes | QMessageBox.No,
                                       QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        
        # Elimina tutti i ROI selezionati
        for row in selected_rows:
            if row >= len(self.rois):
                continue
                
            roi = self.rois[row]
            
            # Remove from scene
            if roi.id in self.roi_items:
                roi_item = self.roi_items[roi.id]
                self.image_view._scene.removeItem(roi_item)
                del self.roi_items[roi.id]
            
            # Remove from model list
            self.rois.pop(row)
            
            print(f"Deleted ROI: {roi.name}")
        
        # Update analysis after deletion
        self.update_roi_analysis()
        self.save_settings_to_json()

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
        if hasattr(self, 'current_image_path') and self.current_image_path and not getattr(self, '_ignore_auto_save', False):
            self.save_settings_to_json()

    def activate_spot_tool(self):
        """Attiva lo strumento per creare spot ROI."""
        self.current_drawing_tool = "spot"
        if hasattr(self, "image_view"):
            self.image_view.setCursor(Qt.CrossCursor)
        
        # Reset altri pulsanti e attiva questo
        self.btn_rect.setChecked(False)
        self.btn_poly.setChecked(False)
        self.btn_spot.setChecked(True)

    def activate_rect_tool(self):
        """Attiva lo strumento per creare ROI rettangolari."""
        self.current_drawing_tool = "rect"
        if hasattr(self, "image_view"):
            self.image_view.setCursor(Qt.CrossCursor)
        
        # Reset altri pulsanti e attiva questo
        self.btn_spot.setChecked(False)
        self.btn_poly.setChecked(False)
        self.btn_rect.setChecked(True)

    def activate_polygon_tool(self):
        """Attiva lo strumento per creare poligoni ROI."""
        self.current_drawing_tool = "polygon"
        if hasattr(self, "image_view"):
            self.image_view.setCursor(Qt.CrossCursor)
            # Assicura che la vista abbia il focus per ricevere eventi tastiera
            self.image_view.setFocus()
        
        # Reset altri pulsanti e attiva questo
        self.btn_spot.setChecked(False)
        self.btn_rect.setChecked(False)
        self.btn_poly.setChecked(True)
        
        print("🔶 Modalità Poligono attivata!")
        print("   • Click sinistro: Aggiungi punto")
        print("   • INVIO o Doppio-click: Completa poligono") 
        print("   • Click destro: Completa poligono")
        print("   • ESC: Annulla")

    def deactivate_drawing_tools(self):
        """Disattiva tutti gli strumenti di disegno."""
        self.current_drawing_tool = None
        if hasattr(self, "image_view"):
            self.image_view.setCursor(Qt.ArrowCursor)
        
        # Feedback visivo: resetta i pulsanti (opzionale)
        if hasattr(self, "btn_spot"):
            self.btn_spot.setChecked(False)
        if hasattr(self, "btn_rect"):
            self.btn_rect.setChecked(False)
        if hasattr(self, "btn_poly"):
            self.btn_poly.setChecked(False)

    def compute_roi_temperatures(self, roi):
        import numpy as np
        from PySide6.QtCore import QRectF, QPointF
        from analysis.roi_models import SpotROI, PolygonROI

        if self.thermal_data is None or not hasattr(self, "image_view"):
            return None

        # Gestisci diversi tipi di ROI
        if isinstance(roi, SpotROI):
            # Per spot ROI, crea una maschera circolare
            h, w = self.thermal_data.shape
            
            # Bounds del cerchio
            x1, y1, x2, y2 = roi.get_bounds()
            x1, y1 = max(0, int(x1)), max(0, int(y1))
            x2, y2 = min(w, int(x2)), min(h, int(y2))
            
            if x1 >= x2 or y1 >= y2:
                return None
            
            # Crea maschera circolare
            y_indices, x_indices = np.ogrid[y1:y2, x1:x2]
            mask = ((x_indices - roi.x) ** 2 + (y_indices - roi.y) ** 2) <= (roi.radius ** 2)
            
            # Estrai solo i pixel del cerchio
            thermal_roi = self.thermal_data[y1:y2, x1:x2].astype(np.float64)
            thermal_roi = thermal_roi[mask]
            
            if thermal_roi.size == 0:
                return None
                
        elif isinstance(roi, PolygonROI):
            # Per poligoni ROI, crea una maschera poligonale
            h, w = self.thermal_data.shape
            
            # Bounds del poligono
            x1, y1, x2, y2 = roi.get_bounds()
            x1, y1 = max(0, int(x1)), max(0, int(y1))
            x2, y2 = min(w, int(x2)), min(h, int(y2))
            
            if x1 >= x2 or y1 >= y2:
                return None
            
            # Crea maschera poligonale
            mask = np.zeros((y2 - y1, x2 - x1), dtype=bool)
            for i in range(y2 - y1):
                for j in range(x2 - x1):
                    mask[i, j] = roi.contains_point(x1 + j, y1 + i)
            
            # Estrai solo i pixel del poligono
            thermal_roi = self.thermal_data[y1:y2, x1:x2].astype(np.float64)
            thermal_roi = thermal_roi[mask]
            
            if thermal_roi.size == 0:
                return None
        else:
            # Per ROI rettangolari (logica esistente)
            item = self.roi_items.get(roi.id)
            if item is not None and item.parentItem() is self.image_view._thermal_item:
                rect = item.mapRectToParent(item.rect()).normalized()
            else:
                # Fallback: tratta il modello come coordinate termiche (non scena)
                rect = QRectF(float(roi.x), float(roi.y), float(roi.width), float(roi.height)).normalized()

            h, w = self.thermal_data.shape
            x1 = max(0, int(np.floor(rect.left())))
            y1 = max(0, int(np.floor(rect.top())))
            x2 = min(w, int(np.ceil(rect.right())))
            y2 = min(h, int(np.ceil(rect.bottom())))
            if x1 >= x2 or y1 >= y2:
                return None

            thermal_roi = self.thermal_data[y1:y2, x1:x2].astype(np.float64)

        # Applica la conversione di Planck (uguale per tutti i tipi di ROI)
        emissivity = float(getattr(roi, 'emissivity', 0.95))
        refl_temp_C = float(self.param_inputs["ReflectedApparentTemperature"].text())
        R1 = float(self.param_inputs["PlanckR1"].text())
        R2 = float(self.param_inputs["PlanckR2"].text())
        B  = float(self.param_inputs["PlanckB"].text())
        F  = float(self.param_inputs["PlanckF"].text())
        O  = float(self.param_inputs["PlanckO"].text())

        refl_temp_K = refl_temp_C + 273.15
        raw_refl = R1 / (R2 * (np.exp(B / refl_temp_K) - F)) - O
        raw_obj = (thermal_roi - (1 - emissivity) * raw_refl) / max(emissivity, 1e-6)

        log_arg = R1 / (R2 * (raw_obj + O)) + F
        temp_K = np.full(log_arg.shape, np.nan, dtype=np.float64)
        valid = log_arg > 0
        temp_K[valid] = B / np.log(log_arg[valid])
        
        # Conversione a Celsius e applicazione correzione ambientale
        temp_celsius = temp_K - 273.15
        return self.apply_environmental_correction(temp_celsius)

    def update_single_roi(self, roi_model):
        """Aggiorna le statistiche di un singolo ROI."""
        import numpy as np
        from analysis.roi_models import SpotROI, PolygonROI
        
        if self.thermal_data is None:
            roi_model.temp_min = roi_model.temp_max = roi_model.temp_mean = roi_model.temp_std = None
            if hasattr(roi_model, 'temp_median'):
                roi_model.temp_median = None
        else:
            # Per tutti i tipi di ROI, usa compute_roi_temperatures che fa la conversione di Planck
            temps = self.compute_roi_temperatures(roi_model)
            if temps is not None:
                valid = temps[~np.isnan(temps)]
                if valid.size > 0:
                    roi_model.temp_min = float(np.min(valid))
                    roi_model.temp_max = float(np.max(valid))
                    roi_model.temp_mean = float(np.mean(valid))
                    roi_model.temp_std = float(np.std(valid))
                    if hasattr(roi_model, 'temp_median'):
                        roi_model.temp_median = float(np.median(valid))
                else:
                    roi_model.temp_min = roi_model.temp_max = roi_model.temp_mean = roi_model.temp_std = None
                    if hasattr(roi_model, 'temp_median'):
                        roi_model.temp_median = None
            else:
                roi_model.temp_min = roi_model.temp_max = roi_model.temp_mean = roi_model.temp_std = None
                if hasattr(roi_model, 'temp_median'):
                    roi_model.temp_median = None

        # Aggiorna l'etichetta e la tabella
        item = self.roi_items.get(roi_model.id)
        if item and hasattr(item, "refresh_label"):
            item.refresh_label()

        self.update_roi_table()
        self.save_settings_to_json()

    def on_label_settings_changed(self):
        self.roi_label_settings = {
            "name": self.cb_label_name.isChecked(),
            "emissivity": self.cb_label_eps.isChecked(),
            "min": self.cb_label_min.isChecked(),
            "max": self.cb_label_max.isChecked(),
            "avg": self.cb_label_avg.isChecked(),
            "median": self.cb_label_med.isChecked(),
        }
        # Aggiorna tutti i label dei ROI
        for item in self.roi_items.values():
            if hasattr(item, "refresh_label"):
                item.refresh_label()

    # Metodi per il salvataggio automatico (li aggiungo alla fine della classe)
    
    def get_json_file_path(self):
        """Restituisce il percorso del file JSON associato all'immagine corrente."""
        if not self.current_image_path:
            return None
        
        import os
        base_path = os.path.splitext(self.current_image_path)[0]
        return f"{base_path}.json"
    
    def save_settings_to_json(self):
        """Salva tutte le impostazioni nel file JSON."""
        if not self.current_image_path or self._ignore_auto_save:
            return
        
        json_path = self.get_json_file_path()
        if not json_path:
            return
        
        try:
            # Raccogli i parametri termici da salvare
            thermal_params = {}
            params_to_save = ["Emissivity", "AtmosphericTemperature", "AtmosphericTransmission", "RelativeHumidity"]
            for param in params_to_save:
                if param in self.param_inputs and self.param_inputs[param].text():
                    try:
                        thermal_params[param] = float(self.param_inputs[param].text())
                    except ValueError:
                        pass  # Ignora valori non validi
            
            # Raccogli i ROI
            rois_data = []
            for roi in self.rois:
                roi_data = {
                    "type": roi.__class__.__name__,
                    "name": roi.name,
                    "emissivity": getattr(roi, 'emissivity', 0.95)
                }
                
                if hasattr(roi, 'x') and hasattr(roi, 'y'):  # RectROI e SpotROI
                    roi_data["x"] = roi.x
                    roi_data["y"] = roi.y
                
                if hasattr(roi, 'width') and hasattr(roi, 'height'):  # RectROI
                    roi_data["width"] = roi.width
                    roi_data["height"] = roi.height
                elif hasattr(roi, 'radius'):  # SpotROI
                    roi_data["radius"] = roi.radius
                elif hasattr(roi, 'points'):  # PolygonROI
                    roi_data["points"] = roi.points
                
                rois_data.append(roi_data)
            
            # Raccogli le impostazioni overlay
            overlay_settings = {
                "scale": self.scale_spin.value() if hasattr(self, 'scale_spin') else 1.0,
                "offset_x": self.offsetx_spin.value() if hasattr(self, 'offsetx_spin') else 0,
                "offset_y": self.offsety_spin.value() if hasattr(self, 'offsety_spin') else 0,
                "opacity": self.overlay_alpha_slider.value() if hasattr(self, 'overlay_alpha_slider') else 50,
                "blend_mode": self.blend_combo.currentText() if hasattr(self, 'blend_combo') else "Normal"
            }
            
            # Compone il dizionario completo
            settings_data = {
                "version": "1.0",
                "thermal_parameters": thermal_params,
                "rois": rois_data,
                "palette": self.palette_combo.currentText() if hasattr(self, 'palette_combo') else "Iron",
                "palette_inverted": getattr(self, 'palette_inverted', False),
                "overlay_settings": overlay_settings
            }
            
            # Salva nel file JSON
            import os
            os.makedirs(os.path.dirname(json_path), exist_ok=True)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(settings_data, f, indent=2, ensure_ascii=False)
            
            print(f"Impostazioni salvate in: {json_path}")
            
        except Exception as e:
            print(f"Errore nel salvataggio delle impostazioni: {e}")
    
    def load_settings_from_json(self):
        """Carica le impostazioni dal file JSON se esiste."""
        if not self.current_image_path:
            return
        
        json_path = self.get_json_file_path()
        if not json_path or not os.path.exists(json_path):
            return
        
        try:
            self._ignore_auto_save = True  # Previeni salvataggi durante il caricamento
            
            with open(json_path, 'r', encoding='utf-8') as f:
                settings_data = json.load(f)
            
            print(f"Caricando impostazioni da: {json_path}")
            
            # Carica i parametri termici
            if "thermal_parameters" in settings_data:
                for param, value in settings_data["thermal_parameters"].items():
                    if param in self.param_inputs:
                        self.param_inputs[param].setText(str(value))
            
            # Carica la palette
            if "palette" in settings_data:
                palette_name = settings_data["palette"]
                palette_index = self.palette_combo.findText(palette_name)
                if palette_index >= 0:
                    self.palette_combo.setCurrentIndex(palette_index)
                    self.selected_palette = palette_name  # Aggiorna anche la variabile interna
            
            # Carica l'inversione della palette
            if "palette_inverted" in settings_data:
                self.palette_inverted = settings_data["palette_inverted"]
            
            # Carica le impostazioni overlay
            if "overlay_settings" in settings_data:
                overlay = settings_data["overlay_settings"]
                
                if "scale" in overlay and hasattr(self, 'scale_spin'):
                    self.scale_spin.setValue(overlay["scale"])
                    self.overlay_scale = overlay["scale"]  # Aggiorna anche la variabile interna
                if "offset_x" in overlay and hasattr(self, 'offsetx_spin'):
                    self.offsetx_spin.setValue(overlay["offset_x"])
                    self.overlay_offset_x = overlay["offset_x"]  # Aggiorna anche la variabile interna
                if "offset_y" in overlay and hasattr(self, 'offsety_spin'):
                    self.offsety_spin.setValue(overlay["offset_y"])
                    self.overlay_offset_y = overlay["offset_y"]  # Aggiorna anche la variabile interna
                if "opacity" in overlay and hasattr(self, 'overlay_alpha_slider'):
                    self.overlay_alpha_slider.setValue(overlay["opacity"])
                    self.overlay_alpha = overlay["opacity"] / 100.0  # Aggiorna anche la variabile interna
                if "blend_mode" in overlay and hasattr(self, 'blend_combo'):
                    blend_index = self.blend_combo.findText(overlay["blend_mode"])
                    if blend_index >= 0:
                        self.blend_combo.setCurrentIndex(blend_index)
                        self.overlay_blend_mode = overlay["blend_mode"]  # Aggiorna anche la variabile interna
            
            # Carica i ROI
            if "rois" in settings_data:
                self.load_rois_from_data(settings_data["rois"])
            
            # AGGIUNTA IMPORTANTE: Applica visivamente le modifiche a palette e inversione
            if self.temperature_data is not None:
                self.update_view_only()  # Aggiorna la visualizzazione con le nuove impostazioni
            
            print(f"Impostazioni caricate con successo da: {json_path}")
            
        except Exception as e:
            print(f"Errore nel caricamento delle impostazioni: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._ignore_auto_save = False
    
    def load_rois_from_data(self, rois_data):
        """Carica i ROI dai dati JSON."""
        # Prima pulisci i ROI esistenti
        self.clear_all_rois()
        
        from analysis.roi_models import RectROI, SpotROI, PolygonROI
        from ui.roi_items import RectROIItem, SpotROIItem, PolygonROIItem
        from PySide6.QtGui import QColor
        
        for roi_data in rois_data:
            try:
                roi_type = roi_data.get("type", "")
                roi_name = roi_data.get("name", "ROI")
                roi_emissivity = roi_data.get("emissivity", 0.95)
                
                # Crea il modello ROI appropriato
                roi_model = None
                roi_item = None
                
                if roi_type == "RectROI":
                    x = roi_data.get("x", 0)
                    y = roi_data.get("y", 0)
                    width = roi_data.get("width", 50)
                    height = roi_data.get("height", 50)
                    
                    roi_model = RectROI(x=x, y=y, width=width, height=height, name=roi_name)
                    roi_model.emissivity = roi_emissivity
                    
                    # Crea l'item grafico come figlio dell'item termico
                    if hasattr(self, 'image_view') and hasattr(self.image_view, '_thermal_item'):
                        roi_item = RectROIItem(roi_model, parent=self.image_view._thermal_item)
                
                elif roi_type == "SpotROI":
                    x = roi_data.get("x", 0)
                    y = roi_data.get("y", 0)
                    radius = roi_data.get("radius", 5)
                    
                    roi_model = SpotROI(x=x, y=y, radius=radius, name=roi_name)
                    roi_model.emissivity = roi_emissivity
                    
                    if hasattr(self, 'image_view') and hasattr(self.image_view, '_thermal_item'):
                        roi_item = SpotROIItem(roi_model, parent=self.image_view._thermal_item)
                
                elif roi_type == "PolygonROI":
                    points = roi_data.get("points", [(0, 0), (50, 0), (50, 50), (0, 50)])
                    
                    roi_model = PolygonROI(points=points, name=roi_name)
                    roi_model.emissivity = roi_emissivity
                    
                    if hasattr(self, 'image_view') and hasattr(self.image_view, '_thermal_item'):
                        roi_item = PolygonROIItem(roi_model, parent=self.image_view._thermal_item)
                
                if roi_model and roi_item:
                    # Aggiungi alle collezioni
                    self.rois.append(roi_model)
                    self.roi_items[roi_model.id] = roi_item
                    
                    # Imposta il colore (ciclo sulla ruota HSV come nell'originale)
                    hue = (len(self.rois) * 55) % 360
                    color = QColor.fromHsv(hue, 220, 255)
                    roi_model.color = color
                    roi_item.set_color(color)
                    roi_item.setZValue(10)
                    
                    print(f"ROI caricato: {roi_model}")
            
            except Exception as e:
                print(f"Errore nel caricamento del ROI: {e}")
        
        # Aggiorna l'analisi e la tabella
        self.update_roi_analysis()
    
    def connect_auto_save_signals(self):
        """Connette tutti i segnali per il salvataggio automatico."""
        # Parametri termici
        for param_input in self.param_inputs.values():
            if hasattr(param_input, 'editingFinished'):
                param_input.editingFinished.connect(self.save_settings_to_json)
        
        # Palette
        if hasattr(self, 'palette_combo'):
            self.palette_combo.currentTextChanged.connect(self.save_settings_to_json)
        
        # Controlli overlay
        if hasattr(self, 'scale_spin'):
            self.scale_spin.valueChanged.connect(self.save_settings_to_json)
        if hasattr(self, 'offsetx_spin'):
            self.offsetx_spin.valueChanged.connect(self.save_settings_to_json)
        if hasattr(self, 'offsety_spin'):
            self.offsety_spin.valueChanged.connect(self.save_settings_to_json)
        if hasattr(self, 'overlay_alpha_slider'):
            self.overlay_alpha_slider.valueChanged.connect(self.save_settings_to_json)
        if hasattr(self, 'blend_combo'):
            self.blend_combo.currentTextChanged.connect(self.save_settings_to_json)
        
        # L'inversione palette è già connessa nel metodo on_invert_palette()
        
        print("Segnali di auto-salvataggio connessi")
