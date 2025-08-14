"""
Main window module for the Warmish thermal analysis application.

This module contains the ThermalAnalyzerNG class which implements the main GUI
window for thermal image analysis. It provides functionality for loading FLIR
thermal images, analyzing temperature data, creating regions of interest (ROI),
and visualizing thermal data with various color palettes.

Classes:
    ThermalAnalyzerNG: Main application window with thermal analysis capabilities.
"""

import json
import io
import os
import subprocess
import exiftool
import numpy as np
from PIL import Image
import matplotlib.cm as cm

from PySide6.QtWidgets import (
    QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QWidget,
    QFileDialog, QMessageBox, QTextEdit, QLineEdit, QFormLayout,
    QGroupBox, QTabWidget, QToolBar, QComboBox, QSizePolicy as QSP,
    QCheckBox, QPushButton, QSlider, QDoubleSpinBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtGui import QAction, QPixmap, QImage, QIcon, QPainter
from PySide6.QtCore import Qt, QPointF, QSignalBlocker

from constants import PALETTE_MAP
from .widgets.color_bar_legend import ColorBarLegend
from .widgets.image_graphics_view import ImageGraphicsView


class ThermalAnalyzerNG(QMainWindow):
    """
    Main window for thermal image analysis application.
    
    This class provides a comprehensive interface for loading, analyzing, and
    visualizing FLIR thermal images. It supports ROI creation, temperature
    calculations with environmental corrections, and various visualization modes.
    
    Attributes:
        thermal_data (np.ndarray): Raw thermal data from FLIR image.
        temperature_data (np.ndarray): Calculated temperature matrix in Celsius.
        metadata (dict): EXIF metadata extracted from thermal image.
        rois (list): List of region of interest models.
        overlay_mode (bool): Whether overlay mode is active.
    """
    
    def __init__(self):
        """Initialize the thermal analyzer main window."""
        super().__init__()
        self.setWindowTitle("Warmish")
        self.setGeometry(100, 100, 1400, 900)
        
        self._setup_toolbar()
        self._init_state_variables()
        self._setup_main_layout()
        self._setup_image_views()
        self._setup_sidebar_tabs()
        self._init_data_storage()
        
    def _setup_toolbar(self):
        """Setup the main toolbar with all actions and controls."""
        self.toolbar = QToolBar("Main Toolbar")
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)
        self.toolbar.setMovable(False)
        
        self.action_open = QAction(QIcon(), "Load Image", self)
        self.action_open.triggered.connect(self.open_image)
        self.toolbar.addAction(self.action_open)
        
        self.action_export = QAction(QIcon(), "Export", self)
        self.toolbar.addAction(self.action_export)
        self.toolbar.addSeparator()
        
        self._setup_palette_controls()
        self._setup_overlay_controls()
        self._setup_zoom_controls()
        
    def _setup_palette_controls(self):
        """Setup palette selection and inversion controls."""
        self.palette_combo = QComboBox()
        self.palette_combo.addItems([
            "Iron", "Rainbow", "Grayscale", "Lava", "Arctic", "Glowbow", 
            "Amber", "Sepia", "Plasma", "Viridis", "Magma", "Cividis", 
            "Turbo", "Ocean", "Terrain", "Jet", "Fire", "Ice", "Spring", 
            "Summer", "Autumn", "Bone", "Pink", "Coolwarm", "RdYlBu", 
            "Spectral", "BrBG", "PiYG", "PRGn", "RdBu", "RdGy", 
            "Purples", "Blues", "Greens", "Oranges", "Reds"
        ])
        self.palette_combo.setCurrentIndex(0)
        self.palette_combo.setToolTip("Select thermal palette")
        self.toolbar.addWidget(self.palette_combo)
        
        self.action_invert_palette = QAction("Invert Palette", self)
        self.action_invert_palette.triggered.connect(self.on_invert_palette)
        self.toolbar.addAction(self.action_invert_palette)
        self.toolbar.addSeparator()
        
    def _setup_overlay_controls(self):
        """Setup overlay mode controls including opacity, scale, and offset."""
        self.action_overlay_view = QAction("Overlay", self)
        self.action_overlay_view.setCheckable(True)
        self.action_overlay_view.toggled.connect(self.on_overlay_toggled)
        self.toolbar.addAction(self.action_overlay_view)
        
        self.overlay_controls_widget = QWidget()
        _ovl = QHBoxLayout(self.overlay_controls_widget)
        _ovl.setContentsMargins(0, 0, 0, 0)
        _ovl.setSpacing(6)
        
        from PySide6.QtWidgets import QLabel as _QLabel
        _ovl.addWidget(_QLabel("Opacity"))
        self.overlay_alpha_slider = QSlider(Qt.Horizontal)
        self.overlay_alpha_slider.setRange(0, 100)
        self.overlay_alpha_slider.setValue(50)
        self.overlay_alpha_slider.setToolTip("Thermal opacity in overlay")
        self.overlay_alpha_slider.setMinimumWidth(160)
        self.overlay_alpha_slider.setMaximumWidth(260)
        self.overlay_alpha_slider.setSizePolicy(QSP.Preferred, QSP.Fixed)
        self.overlay_alpha_slider.valueChanged.connect(self.on_overlay_alpha_changed)
        _ovl.addWidget(self.overlay_alpha_slider)
        
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setDecimals(3)
        self.scale_spin.setRange(0.100, 5.000)
        self.scale_spin.setSingleStep(0.01)
        self.scale_spin.setPrefix("Scale ")
        self.scale_spin.setValue(1.0)
        self.scale_spin.setToolTip("IR scale relative to visible (Real2IR)")
        self.scale_spin.valueChanged.connect(self.on_scale_spin_changed)
        _ovl.addWidget(self.scale_spin)
        
        self.offsetx_spin = QSpinBox()
        self.offsetx_spin.setRange(-2000, 2000)
        self.offsetx_spin.setSingleStep(1)
        self.offsetx_spin.setPrefix("X Offset ")
        self.offsetx_spin.setToolTip("X offset (visible pixels)")
        self.offsetx_spin.valueChanged.connect(self.on_offsetx_changed)
        _ovl.addWidget(self.offsetx_spin)
        
        self.offsety_spin = QSpinBox()
        self.offsety_spin.setRange(-2000, 2000)
        self.offsety_spin.setSingleStep(1)
        self.offsety_spin.setPrefix("Y Offset ")
        self.offsety_spin.setToolTip("Y offset (visible pixels)")
        self.offsety_spin.valueChanged.connect(self.on_offsety_changed)
        _ovl.addWidget(self.offsety_spin)
        
        self.blend_combo = QComboBox()
        self.blend_combo.addItems([
            "Normal", "Multiply", "Screen", "Overlay", "Darken", "Lighten",
            "ColorDodge", "ColorBurn", "SoftLight", "HardLight", 
            "Difference", "Exclusion", "Additive"
        ])
        self.blend_combo.setCurrentText("Normal")
        self.blend_combo.setToolTip("Thermal overlay blending method")
        self.blend_combo.currentTextChanged.connect(self.on_blend_mode_changed)
        _ovl.addWidget(self.blend_combo)
        
        self.overlay_action = self.toolbar.addWidget(self.overlay_controls_widget)
        
        self.action_reset_align = QAction("Reset Alignment", self)
        self.action_reset_align.setToolTip("Restore scale and offset from metadata")
        self.action_reset_align.triggered.connect(self.on_reset_alignment)
        self.toolbar.addAction(self.action_reset_align)
        self.toolbar.addSeparator()
        
        self.set_overlay_controls_visible(False)
        
    def _setup_zoom_controls(self):
        """Setup zoom in, zoom out, and reset zoom controls."""
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
        
        # Spacer to push other toolbar elements to the left
        self.toolbar.addWidget(QWidget())
        self.toolbar.widgetForAction(self.toolbar.actions()[-1]).setSizePolicy(
            QSP.Expanding, QSP.Preferred
        )
        
    def _init_state_variables(self):
        """Initialize application state variables."""
        self.zoom_factor = 1.0
        self.pan_offset = [0, 0]
        self._panning = False
        self._pan_start = None
        
    def _setup_main_layout(self):
        """Setup the main window layout with central widget."""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
    def _setup_image_views(self):
        """Setup image viewing area with primary and secondary views."""
        # Image area widget
        self.image_area_widget = QWidget()
        self.image_area_layout = QVBoxLayout(self.image_area_widget)
        self.image_area_layout.setContentsMargins(24, 24, 24, 24)
        self.image_area_layout.setSpacing(8)
        self.main_layout.addWidget(self.image_area_widget, stretch=4)
        
        # Primary image view (thermal)
        self.image_view = ImageGraphicsView()
        self.image_view.setStyleSheet("border: 1px solid gray; background-color: #333;")
        self.image_view.mouse_moved_on_thermal.connect(self.on_thermal_mouse_move)
        self.image_view.set_main_window(self)
        self.image_area_layout.addWidget(self.image_view, stretch=1)
        
        # Secondary image view (visible light)
        self.secondary_image_view = ImageGraphicsView()
        self.secondary_image_view.setStyleSheet("border: 1px solid gray; background-color: #222;")
        self.secondary_image_view.set_main_window(self)
        self.secondary_image_view.set_allow_roi_drawing(False)
        self.image_area_layout.addWidget(self.secondary_image_view, stretch=1)
        
        self.sync_views()
        
        # Temperature tooltip
        self.temp_tooltip_label = QLabel("Temp: --.-- °C")
        self.temp_tooltip_label.setStyleSheet(
            "background-color: black; color: white; padding: 4px; border-radius: 3px;"
        )
        self.temp_tooltip_label.setVisible(False)
        self.temp_tooltip_label.setParent(self.image_view)
        
        # Color legend
        self.legend_groupbox = QGroupBox("Temperature Legend (°C)")
        self.legend_layout = QVBoxLayout(self.legend_groupbox)
        self.legend_layout.setContentsMargins(8, 8, 8, 8)
        self.legend_layout.setSpacing(6)
        self.legend_layout.setAlignment(Qt.AlignCenter)
        self.colorbar = ColorBarLegend()
        self.legend_layout.addWidget(self.colorbar, alignment=Qt.AlignCenter)
        self.legend_groupbox.setMaximumWidth(140)
        self.main_layout.addWidget(self.legend_groupbox, stretch=0)
        
    def _setup_sidebar_tabs(self):
        """Setup the sidebar with parameters, ROI analysis, and batch processing tabs."""
        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setTabPosition(QTabWidget.East)
        self.sidebar_tabs.setMinimumWidth(400)
        self.main_layout.addWidget(self.sidebar_tabs, stretch=2)
        
        self._setup_parameters_tab()
        self._setup_roi_analysis_tab()
        self._setup_batch_export_tab()
        
    def _setup_parameters_tab(self):
        """Setup the thermal parameters configuration tab."""
        self.tab_params = QWidget()
        self.tab_params_layout = QVBoxLayout(self.tab_params)
        self.tab_params_layout.setContentsMargins(16, 16, 16, 16)
        self.tab_params_layout.setSpacing(12)
        
        # Parameters group
        self.params_groupbox = QGroupBox("Calculation Parameters")
        self.params_layout = QFormLayout(self.params_groupbox)
        self.param_inputs = {}
        
        # Create input fields for thermal calculation parameters
        param_keys = [
            "Emissivity", "ObjectDistance", "ReflectedApparentTemperature", 
            "PlanckR1", "PlanckR2", "PlanckB", "PlanckF", "PlanckO", 
            "AtmosphericTemperature", "AtmosphericTransmission", "RelativeHumidity"
        ]
        
        for key in param_keys:
            line_edit = QLineEdit()
            line_edit.editingFinished.connect(self.recalculate_and_update_view)  
            self.param_inputs[key] = line_edit
            self.params_layout.addRow(key, self.param_inputs[key])
        
        # Reset button
        self.reset_params_button = QPushButton("Reset to EXIF Values")
        self.reset_params_button.setToolTip(
            "Restore all parameters to values extracted from EXIF metadata\n" +
            "Use default values for unavailable parameters"
        )
        self.reset_params_button.clicked.connect(self.reset_params_to_exif)
        self.params_layout.addRow("", self.reset_params_button)
        
        self.tab_params_layout.addWidget(self.params_groupbox)
        
        # Metadata display
        self.all_meta_display = QTextEdit("All extracted metadata will appear here.")
        self.all_meta_display.setReadOnly(True)
        self.tab_params_layout.addWidget(self.all_meta_display)
        
        self.sidebar_tabs.addTab(self.tab_params, "Parameters")
        
    def _setup_roi_analysis_tab(self):
        """Setup the ROI (Region of Interest) analysis tab."""
        self.tab_areas = QWidget()
        self.tab_areas_layout = QVBoxLayout(self.tab_areas)
        self.tab_areas_layout.setContentsMargins(16, 16, 16, 16)
        self.tab_areas_layout.setSpacing(12)
        
        # ROI creation tools
        self._setup_roi_tools()
        
        # ROI analysis table
        self._setup_roi_table()
        
        # ROI label settings
        self._setup_roi_label_settings()
        
        self.sidebar_tabs.addTab(self.tab_areas, "Areas & Analysis")
        
    def _setup_roi_tools(self):
        """Setup ROI creation tool buttons."""
        self.areas_tools_widget = QWidget()
        _areas_tools = QHBoxLayout(self.areas_tools_widget)
        _areas_tools.setContentsMargins(0, 0, 0, 0)
        _areas_tools.setSpacing(12)

        # Tool buttons
        self.btn_spot = QPushButton("Spot")
        self.btn_rect = QPushButton("Rectangle")
        self.btn_poly = QPushButton("Polygon")
        
        # Make buttons checkable for toggle behavior
        self.btn_spot.setCheckable(True)
        self.btn_rect.setCheckable(True)
        self.btn_poly.setCheckable(True)
        
        # Connect button signals
        self.btn_rect.clicked.connect(self.activate_rect_tool)
        self.btn_spot.clicked.connect(self.activate_spot_tool)
        self.btn_poly.clicked.connect(self.activate_polygon_tool)
        
        _areas_tools.addWidget(self.btn_spot)
        _areas_tools.addWidget(self.btn_rect)
        _areas_tools.addWidget(self.btn_poly)
        _areas_tools.addStretch(1)
        
        self.tab_areas_layout.addWidget(self.areas_tools_widget)
        
    def _setup_roi_table(self):
        """Setup the ROI analysis results table."""
        self.roi_table_group = QGroupBox("ROI Analysis")
        self.roi_table_layout = QVBoxLayout(self.roi_table_group)
        
        # Create table
        self.roi_table = QTableWidget()
        self.roi_table.setColumnCount(6)
        headers = ["Name", "Emissivity", "Min (°C)", "Max (°C)", "Mean (°C)", "Median (°C)"]
        self.roi_table.setHorizontalHeaderLabels(headers)
        self.roi_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.roi_table.setSelectionMode(QTableWidget.MultiSelection) 
        self.roi_table.setAlternatingRowColors(True)
        self.roi_table.setSortingEnabled(False)
        
        # Configure column sizing
        header = self.roi_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 6):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        
        # Connect table signals
        self.roi_table.itemSelectionChanged.connect(self.on_roi_table_selection_changed)
        self.roi_table.itemChanged.connect(self.on_roi_table_item_changed)
        
        self.roi_table_layout.addWidget(self.roi_table)
        
        # ROI control buttons
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
        
    def _setup_roi_label_settings(self):
        """Setup ROI label display settings checkboxes."""
        label_opts_layout = QHBoxLayout()
        label_opts_layout.addWidget(QLabel("Show in labels:"))

        # Default label settings
        self.roi_label_settings = {
            "name": True,
            "emissivity": True,
            "min": True,
            "max": True,
            "avg": True,
            "median": False,
        }

        # Create checkboxes for label options
        self.cb_label_name = QCheckBox("Name")
        self.cb_label_eps = QCheckBox("ε")
        self.cb_label_min = QCheckBox("Min")
        self.cb_label_max = QCheckBox("Max")
        self.cb_label_avg = QCheckBox("Mean")
        self.cb_label_med = QCheckBox("Median")
        
        # Set initial states
        self.cb_label_name.setChecked(self.roi_label_settings["name"])
        self.cb_label_eps.setChecked(self.roi_label_settings["emissivity"])
        self.cb_label_min.setChecked(self.roi_label_settings["min"])
        self.cb_label_max.setChecked(self.roi_label_settings["max"])
        self.cb_label_avg.setChecked(self.roi_label_settings["avg"])
        self.cb_label_med.setChecked(self.roi_label_settings["median"])

        # Connect signals
        for cb in [self.cb_label_name, self.cb_label_eps, self.cb_label_min,
                   self.cb_label_max, self.cb_label_avg, self.cb_label_med]:
            cb.toggled.connect(self.on_label_settings_changed)
            label_opts_layout.addWidget(cb)

        label_opts_layout.addStretch()
        self.roi_table_layout.addLayout(label_opts_layout)
        
    def _setup_batch_export_tab(self):
        """Setup the batch processing and export tab."""
        self.tab_batch = QWidget()
        self.tab_batch_layout = QVBoxLayout(self.tab_batch)
        self.tab_batch_layout.setContentsMargins(16, 16, 16, 16)
        self.tab_batch_layout.setSpacing(12)
        
        # Batch processing section
        batch_group = QGroupBox("Batch Processing")
        batch_layout = QVBoxLayout(batch_group)
        
        self.batch_file_label = QLabel(
            "Drag & drop images or click to browse\n"
            "Supports .FLIR, .JPG (with thermal data), .PNG"
        )
        self.batch_file_label.setAlignment(Qt.AlignCenter)
        self.batch_file_label.setStyleSheet(
            "border: 1px dashed #888; padding: 32px; color: #ccc;"
        )
        batch_layout.addWidget(self.batch_file_label)
        
        # Batch processing options
        self.cb_thermal_params = QCheckBox("Thermal Parameters")
        self.cb_analysis_areas = QCheckBox("Analysis Areas (same positions)")
        self.cb_color_palette = QCheckBox("Color Palette")
        
        batch_layout.addWidget(self.cb_thermal_params)
        batch_layout.addWidget(self.cb_analysis_areas)
        batch_layout.addWidget(self.cb_color_palette)
        
        self.btn_process_batch = QPushButton("Process Selected Images")
        self.btn_process_batch.setStyleSheet(
            "background-color: #a259f7; color: white; font-weight: bold;"
        )
        batch_layout.addWidget(self.btn_process_batch)
        
        self.tab_batch_layout.addWidget(batch_group)
        
        # Export section
        export_group = QGroupBox("Export Options")
        export_layout = QVBoxLayout(export_group)
        
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
        
        self.btn_export_current = QPushButton("Export Current Analysis")
        self.btn_export_current.setStyleSheet(
            "background-color: #6c47e6; color: white; font-weight: bold;"
        )
        export_layout.addWidget(self.btn_export_current)
        
        self.tab_batch_layout.addWidget(export_group)
        self.sidebar_tabs.addTab(self.tab_batch, "Batch & Export")
        
    def _init_data_storage(self):
        """Initialize data storage variables and connect signals."""
        # Thermal data storage
        self.thermal_data = None
        self.temperature_data = None
        self.temp_min = 0
        self.temp_max = 0
        self.metadata = None
        
        # Image storage
        self.base_pixmap = None
        self.base_pixmap_visible = None
        
        # Palette settings
        self.selected_palette = "Iron"
        self.palette_inverted = False
        self.palette_combo.currentIndexChanged.connect(self.on_palette_changed)
        
        # Overlay settings
        self.overlay_mode = False
        self.overlay_alpha = 0.5
        self.overlay_scale = 1.0
        self.overlay_offset_x = 0.0
        self.overlay_offset_y = 0.0
        self.meta_overlay_scale = 1.0
        self.meta_offset_x = 0.0
        self.meta_offset_y = 0.0
        self.overlay_blend_mode = "Normal"
        
        # ROI management
        self.rois = []
        self.roi_items = {}
        self.current_drawing_tool = None
        self.roi_start_pos = None
        self.temp_roi_item = None
        self.is_drawing_roi = False
        self._updating_roi_table = False
        
        # Application state
        self.current_image_path = None
        self._ignore_auto_save = False
        
        # Make secondary view visible by default
        self.secondary_image_view.setVisible(True)

    def reset_application_state(self):
        """
        Reset the complete application state before loading a new image.
        
        This method clears all ROIs, resets thermal parameters to defaults,
        and restores UI controls to their initial state. It's called when
        loading a new thermal image to ensure clean state.
        """
        try:
            self._ignore_auto_save = True
            
            print("Resetting application state...")
            
            # Clear all existing ROIs without confirmation
            self.clear_all_rois(confirm=False)
            
            # Reset palette settings
            self.palette_combo.setCurrentText("Iron")
            self.selected_palette = "Iron"
            self.palette_inverted = False
            
            # Reset thermal parameters to default values
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
            
            # Apply default values to parameter inputs
            for param, default_value in default_values.items():
                if param in self.param_inputs:
                    self.param_inputs[param].blockSignals(True)
                    self.param_inputs[param].setText(default_value)
                    self.param_inputs[param].setStyleSheet("")
                    self.param_inputs[param].blockSignals(False)
            
            # Reset overlay controls to default values
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
                
            # Reset overlay mode
            if hasattr(self, 'action_overlay_view'):
                self.action_overlay_view.setChecked(False)
                self.overlay_mode = False
                
            # Reset metadata overlay values
            self.meta_overlay_scale = 1.0
            self.meta_offset_x = 0.0
            self.meta_offset_y = 0.0
            
            print("State reset completed")
            
        except Exception as e:
            print(f"Error during state reset: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._ignore_auto_save = False

    def open_image(self):
        """
        Open and load a FLIR thermal image file.
        
        This method handles the complete process of loading a thermal image:
        - File selection dialog
        - EXIF metadata extraction
        - Raw thermal data extraction
        - Temperature calculation setup
        - Visible light image extraction (if available)
        
        The method also resets the application state and loads saved settings
        if a corresponding JSON file exists.
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select FLIR Image", "", "JPEG Images (*.jpg *.jpeg)"
        )
        if not file_path: 
            return
            
        self.current_image_path = file_path
        self.reset_application_state()

        try:
            # Update window title with filename
            self.setWindowTitle(f"Warmish - {file_path.split('/')[-1]}")
            
            # Extract EXIF metadata using exiftool
            with exiftool.ExifTool() as et:
                json_string = et.execute(b"-json", file_path.encode())
                self.metadata = json.loads(json_string)[0]
                self.all_meta_display.setPlainText(
                    json.dumps(self.metadata, indent=4, default=str)
                )
                
                # Extract overlay alignment parameters from metadata
                try:
                    self.meta_overlay_scale = 1/float(self.metadata.get("APP1:Real2IR", 1.0))
                    self.overlay_scale = self.meta_overlay_scale
                except Exception:
                    self.meta_overlay_scale = 1.0
                    self.overlay_scale = 1.0
                    
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
                
                # Update UI controls with metadata values
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
                    
            # Populate thermal calculation parameters from metadata
            self.populate_params()

            # Extract raw thermal data using exiftool
            command = ["exiftool", "-b", "-RawThermalImage", file_path]
            result = subprocess.run(command, capture_output=True, check=True)
            raw_thermal_bytes = result.stdout
            
            if not raw_thermal_bytes: 
                raise ValueError("Binary thermal data not extracted.")

            # Process thermal data based on image type
            image_type = self.metadata.get("APP1:RawThermalImageType", "Unknown")
            if image_type == "PNG":
                # PNG format thermal data
                self.thermal_data = np.array(Image.open(io.BytesIO(raw_thermal_bytes)))
                self.thermal_data.byteswap(inplace=True)  # Ensure correct byte order
            else:
                # Raw binary thermal data
                width = self.metadata.get('APP1:RawThermalImageWidth')
                height = self.metadata.get('APP1:RawThermalImageHeight')
                if not width or not height: 
                    raise ValueError("Image dimensions not found.")
                self.thermal_data = np.frombuffer(
                    raw_thermal_bytes, dtype=np.uint16
                ).reshape((height, width))

            # Calculate temperatures and update display
            self.update_analysis()
            
            # Load saved settings from JSON file
            self.load_settings_from_json()
            
            # Connect auto-save signals (only once)
            if not hasattr(self, '_auto_save_connected'):
                self.connect_auto_save_signals()
                self._auto_save_connected = True

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Unable to process file:\n{e}")
            import traceback
            traceback.print_exc()
            
        # Extract visible light image if available
        try:
            command_rgb = ["exiftool", "-b", "-EmbeddedImage", file_path]
            result_rgb = subprocess.run(command_rgb, capture_output=True, check=True)
            rgb_bytes = result_rgb.stdout
            
            if rgb_bytes:
                # Process visible light image
                image_rgb = Image.open(io.BytesIO(rgb_bytes))
                image_rgb = image_rgb.convert("RGB")
                self.visible_gray_full = np.array(image_rgb.convert("L"), dtype=np.float32) / 255.0
                
                # Convert to QPixmap for display
                data = image_rgb.tobytes("raw", "RGB")
                qimage = QImage(data, image_rgb.width, image_rgb.height, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(qimage)
                self.base_pixmap_visible = pixmap
                self.overlay_mode = False
                self.display_images()
            else:
                self.base_pixmap_visible = None
                self.display_images()
                
        except Exception as e:
            print(f"Error loading visible image: {e}")
            self.base_pixmap_visible = None
            self.display_images()

    def recalculate_and_update_view(self):
        """
        Recalculate temperature matrix and update the complete view.
        
        This method should be used when thermal parameters change, as it
        performs a full recalculation of the temperature data from raw
        thermal values using the current Planck and environmental parameters.
        """
        if self.thermal_data is None: 
            return
            
        print(">>> Recalculating temperatures and visualisation...")
        self.calculate_temperature_matrix()
        self.create_colored_pixmap()
        self.update_legend()
        self.display_images()
        
        # Update ROI analysis if ROIs exist
        if len(self.rois) > 0:
            print("Updating ROI analysis after temperature recalculation...")
            self.update_roi_analysis()

    def update_view_only(self):
        """
        Update only the visualisation using already calculated temperature data.
        
        This method should be used when only palette or colour inversion changes,
        as it doesn't recalculate temperatures but only updates the visual
        representation of existing data.
        """
        if self.temperature_data is None:
            return
            
        print(">>> Updating visualisation only...")
        self.create_colored_pixmap()
        self.update_legend()
        self.display_images()
        
    def update_analysis(self):
        """
        Legacy method - prefer recalculate_and_update_view().
        
        This method is maintained for backward compatibility but new code
        should use the more explicit recalculate_and_update_view() method.
        """
        self.recalculate_and_update_view()

    def populate_params(self):
        """
        Populate thermal calculation parameters from EXIF metadata.
        
        This method extracts thermal calculation parameters from the loaded
        image metadata and populates the UI input fields. For missing
        parameters, appropriate default values are used and highlighted.
        """
        if not self.metadata: 
            return
            
        # Default values for missing parameters
        default_values = {
            "AtmosphericTemperature": 20.0,
            "AtmosphericTransmission": 0.95,
            "RelativeHumidity": 50.0,
            "ObjectDistance": 1.0,
            "Emissivity": 0.95
        }
        
        for key, line_edit in self.param_inputs.items():
            # Try to get value from metadata
            value = self.metadata.get(f"APP1:{key}", self.metadata.get(key, "N/A"))
            
            # Use default value if not found in metadata
            if value == "N/A" and key in default_values:
                value = default_values[key]
                line_edit.setStyleSheet("background-color: #fff3cd;")  # Yellow highlight
                line_edit.setToolTip(f"Default value used: {value}")
            else:
                line_edit.setStyleSheet("")
                line_edit.setToolTip("")
                
            # Format numeric values appropriately
            if isinstance(value, (int, float)) and value != "N/A":
                if key in ["PlanckR1", "PlanckR2", "PlanckB", "PlanckF", "PlanckO"]:
                    line_edit.setText(f"{float(value):.12f}")  # High precision for Planck constants
                elif key in ["Emissivity", "ReflectedApparentTemperature", "AtmosphericTransmission"]:
                    line_edit.setText(f"{float(value):.6f}")   # Medium precision
                else:
                    line_edit.setText(f"{float(value):.4f}")   # Standard precision
            else:
                line_edit.setText(str(value))

    def reset_params_to_exif(self):
        """
        Reset all calculation parameters to values extracted from EXIF metadata.
        
        This method restores thermal calculation parameters to their original
        EXIF values when available, or to appropriate default values when
        EXIF data is missing. The UI is updated to reflect the source of
        each parameter value.
        """
        if not hasattr(self, 'metadata') or not self.metadata:
            self._apply_default_values()
            return
            
        # Default values for parameters not available in EXIF
        default_values = {
            "AtmosphericTemperature": 20.0,
            "AtmosphericTransmission": 0.95,
            "RelativeHumidity": 50.0,
            "ObjectDistance": 1.0,
            "Emissivity": 0.95
        }
        
        reset_count = 0
        default_count = 0
        
        for key, line_edit in self.param_inputs.items():
            exif_value = self.metadata.get(f"APP1:{key}", self.metadata.get(key))
            
            if exif_value is not None and exif_value != "N/A":
                # Use EXIF value
                if isinstance(exif_value, (int, float)):
                    if key in ["PlanckR1", "PlanckR2", "PlanckB", "PlanckF", "PlanckO"]:
                        line_edit.setText(f"{float(exif_value):.12f}")
                    elif key in ["Emissivity", "ReflectedApparentTemperature", "AtmosphericTransmission"]:
                        line_edit.setText(f"{float(exif_value):.6f}")
                    else:
                        line_edit.setText(f"{float(exif_value):.4f}")
                else:
                    line_edit.setText(str(exif_value))
                
                line_edit.setStyleSheet("")
                line_edit.setToolTip(f"Value from EXIF metadata: {exif_value}")
                reset_count += 1
                
            elif key in default_values:
                # Use default value
                default_value = default_values[key]
                if key in ["Emissivity", "AtmosphericTransmission"]:
                    line_edit.setText(f"{default_value:.6f}")
                else:
                    line_edit.setText(f"{default_value:.4f}")
                
                line_edit.setStyleSheet("background-color: #fff3cd;")  # Yellow highlight
                line_edit.setToolTip(
                    f"Default value used: {default_value}\n"
                    "(Not available in EXIF metadata)"
                )
                default_count += 1
            else:
                # Parameter not available
                line_edit.setText("N/A")
                line_edit.setStyleSheet("background-color: #f8d7da;")  # Red highlight
                line_edit.setToolTip("Parameter not available in EXIF metadata")
                
        print(f"Parameters reset completed:")
        print(f"  - {reset_count} parameters restored from EXIF metadata")
        print(f"  - {default_count} parameters set to default values")
        
        # Trigger recalculation with new parameters
        self.recalculate_and_update_view()

    def _apply_default_values(self):
        """
        Apply only default values when no metadata is available.
        
        This private method is called when EXIF metadata is completely
        unavailable and all parameters must be set to sensible defaults.
        """
        default_values = {
            "Emissivity": 0.95,
            "ObjectDistance": 1.0,
            "ReflectedApparentTemperature": 20.0,
            "AtmosphericTemperature": 20.0,
            "AtmosphericTransmission": 0.95,
            "RelativeHumidity": 50.0,
        }
        
        for key, line_edit in self.param_inputs.items():
            if key in default_values:
                default_value = default_values[key]
                if key in ["Emissivity", "AtmosphericTransmission"]:
                    line_edit.setText(f"{default_value:.6f}")
                else:
                    line_edit.setText(f"{default_value:.4f}")
                line_edit.setStyleSheet("background-color: #fff3cd;")
                line_edit.setToolTip(f"Default value: {default_value}")
            else:
                line_edit.setText("N/A")
                line_edit.setStyleSheet("background-color: #f8d7da;")
                line_edit.setToolTip("Parameter not available")
        
        print("Applied default values (no EXIF metadata available)")

    def apply_environmental_correction(self, temp_data):
        """
        Apply environmental corrections to improve temperature accuracy.
        
        This method applies corrections based on environmental parameters
        extracted from FLIR metadata to improve the accuracy of temperature
        measurements by accounting for atmospheric conditions.
        
        Args:
            temp_data (np.ndarray): Raw temperature data in Celsius.
            
        Returns:
            np.ndarray: Environmentally corrected temperature data.
        """
        try:
            if temp_data is None or np.all(np.isnan(temp_data)):
                print("⚠️ WARNING: Invalid temperature data input to environmental correction")
                return temp_data
                
            # Extract environmental parameters
            atmospheric_temp = self._get_float_param("AtmosphericTemperature", 20.0)
            atmospheric_transmission = self._get_float_param("AtmosphericTransmission", 0.95)
            relative_humidity = self._get_float_param("RelativeHumidity", 50.0)
            
            # Validate parameters
            if not all(np.isfinite([atmospheric_temp, atmospheric_transmission, relative_humidity])):
                print("⚠️ WARNING: Invalid environmental parameters - correction skipped")
                return temp_data
                
            # Calculate corrections based on atmospheric conditions
            temp_correction = (atmospheric_temp - 20.0) * 0.0005
            transmission_correction = (1.0 - atmospheric_transmission) * 0.002
            humidity_correction = (relative_humidity - 50.0) * 0.00002
            
            total_correction = temp_correction + transmission_correction + humidity_correction
            corrected_temp = temp_data + total_correction
            
            # Log correction details if significant
            if abs(total_correction) > 0.001:
                print(f"Environmental corrections applied:")
                print(f"  - Atmospheric temperature: {temp_correction:.6f}°C")
                print(f"  - Atmospheric transmission: {transmission_correction:.6f}°C") 
                print(f"  - Relative humidity: {humidity_correction:.6f}°C")
                print(f"  - Total correction: {total_correction:.6f}°C")
            
            return corrected_temp
            
        except Exception as e:
            print(f"Warning: Environmental correction not applied - {e}")
            return temp_data

    def _get_float_param(self, param_name, default_value):
        """
        Get a float parameter from UI input or metadata with fallback.
        
        This helper method safely extracts numeric parameters from either
        the UI input fields or the metadata, handling "N/A" values and
        conversion errors gracefully.
        
        Args:
            param_name (str): Name of the parameter to retrieve.
            default_value (float): Default value if parameter is unavailable.
            
        Returns:
            float: The parameter value or default if unavailable.
        """
        try:
            # Try to get value from UI input first
            if param_name in self.param_inputs:
                ui_value = self.param_inputs[param_name].text().strip()
                if ui_value and ui_value != "N/A":
                    return float(ui_value)
                    
            # Fallback to metadata
            if hasattr(self, 'metadata') and self.metadata:
                meta_value = self.metadata.get(f"APP1:{param_name}", 
                                             self.metadata.get(param_name))
                if meta_value is not None and meta_value != "N/A":
                    return float(meta_value)
                    
            return float(default_value)
            
        except (ValueError, TypeError):
            return float(default_value)

    def _calculate_temperatures_from_raw(self, raw_data, emissivity, debug=False):
        """
        Calculate temperatures from raw thermal data using Planck equation.
        
        This private method contains the core thermal calculation logic that applies
        the Planck equation with emissivity and environmental parameters to convert
        raw thermal sensor values to calibrated temperatures in Celsius.
        
        Args:
            raw_data (np.ndarray): Raw thermal data from sensor.
            emissivity (float): Emissivity value for the calculation.
            debug (bool): Whether to print debug information.
            
        Returns:
            np.ndarray: Calculated temperatures in Celsius (before environmental correction).
        """
        try:
            # Extract calculation parameters from UI
            refl_temp_C = float(self.param_inputs["ReflectedApparentTemperature"].text())
            R1 = float(self.param_inputs["PlanckR1"].text())
            R2 = float(self.param_inputs["PlanckR2"].text())
            B = float(self.param_inputs["PlanckB"].text())
            F = float(self.param_inputs["PlanckF"].text())
            O = float(self.param_inputs["PlanckO"].text())
            
            refl_temp_K = refl_temp_C + 273.15  # Convert to Kelvin
            
            if debug:
                print(f"🔍 Debug Planck parameters:")
                print(f"  R1={R1}, R2={R2}, B={B}, F={F}, O={O}")
                print(f"  Emissivity={emissivity}, ReflTemp={refl_temp_C}°C")
            
            # Calculate reflected temperature component
            raw_refl = R1 / (R2 * (np.exp(B / refl_temp_K) - F)) - O
            if debug:
                print(f"  raw_refl range: {np.nanmin(raw_refl):.3f} to {np.nanmax(raw_refl):.3f}")
            
            # Apply emissivity correction
            raw_obj = (raw_data - (1 - emissivity) * raw_refl) / max(emissivity, 1e-6)
            if debug:
                print(f"  raw_obj range: {np.nanmin(raw_obj):.3f} to {np.nanmax(raw_obj):.3f}")
            
            # Prepare for logarithm calculation
            log_arg = R1 / (R2 * (raw_obj + O)) + F
            if debug:
                print(f"  log_arg range: {np.nanmin(log_arg):.3f} to {np.nanmax(log_arg):.3f}")
            
            # Check validity of logarithm arguments
            if debug:
                valid_indices = log_arg > 0
                valid_count = np.sum(valid_indices)
                total_count = log_arg.size
                print(f"  Pixels valid for logarithm: {valid_count}/{total_count} ({100*valid_count/total_count:.1f}%)")
                
                if valid_count == 0:
                    print("❌ ERROR: No pixels have log_arg > 0 - all values will be NaN!")
                    print("   Possible causes:")
                    print("   - Incorrect Planck parameters")
                    print("   - Emissivity too low")
                    print("   - Corrupted raw thermal data")
            
            # Apply Planck equation to calculate temperature
            temp_K = np.full(log_arg.shape, np.nan, dtype=np.float64)
            valid_indices = log_arg > 0
            temp_K[valid_indices] = B / np.log(log_arg[valid_indices])
            
            if debug:
                print(f"  temp_K range: {np.nanmin(temp_K):.3f} to {np.nanmax(temp_K):.3f}")
            
            # Convert to Celsius
            temp_celsius = temp_K - 273.15
            return temp_celsius
            
        except Exception as e:
            print(f"Error in Planck calculation: {e}")
            # Return NaN array on error
            return np.full(raw_data.shape, np.nan, dtype=np.float64)

    def calculate_temperature_matrix(self):
        """
        Calculate temperature matrix from raw thermal data using Planck equation.
        
        This method performs the core thermal calculation by applying the
        Planck equation with the current emissivity and environmental parameters
        to convert raw thermal sensor values to calibrated temperatures in Celsius.
        
        The calculation includes:
        - Emissivity correction
        - Reflected apparent temperature compensation
        - Planck equation application
        - Environmental corrections
        """
        try:
            # Extract emissivity from UI
            emissivity = float(self.param_inputs["Emissivity"].text())
            
            # Calculate temperatures using the refactored method
            temp_celsius = self._calculate_temperatures_from_raw(
                self.thermal_data, emissivity, debug=True
            )
            
            # Apply environmental corrections
            self.temperature_data = self.apply_environmental_correction(temp_celsius)
            
            # Handle edge cases and calculate temperature range
            if np.all(np.isnan(self.temperature_data)):
                print("⚠️ WARNING: All temperature values are NaN - possible problem with parameters")
                print("Checking Planck parameters and emissivity")
                # Fallback: use raw data scaled
                self.temperature_data = self.thermal_data.astype(float) / 100.0
                self.temp_min = np.nanmin(self.temperature_data)
                self.temp_max = np.nanmax(self.temperature_data)
            elif np.any(np.isfinite(self.temperature_data)):
                finite_data = self.temperature_data[np.isfinite(self.temperature_data)]
                if len(finite_data) > 0:
                    self.temp_min = np.min(finite_data)
                    self.temp_max = np.max(finite_data)
                else:
                    self.temp_min, self.temp_max = 0, 100
            else:
                self.temp_min, self.temp_max = 0, 100
                
        except Exception as e:
            print(f"Error calculating temperature: {e}")
            # Fallback to zero data
            self.temperature_data = np.zeros_like(self.thermal_data, dtype=float)
            self.temp_min, self.temp_max = 0, 0

    def create_colored_pixmap(self):
        """
        Create a colored pixmap from temperature data using the selected palette.
        
        This method converts the calculated temperature matrix into a colored
        visualization using the selected color palette. It handles normalization,
        palette inversion, and creates the final QPixmap for display.
        """
        if self.temperature_data is None: 
            return
            
        # Normalize temperature data to 0-1 range
        temp_range = self.temp_max - self.temp_min
        if temp_range == 0: 
            temp_range = 1  # Avoid division by zero
        
        norm_data = (self.temperature_data - self.temp_min) / temp_range
        norm_data = np.nan_to_num(norm_data)  # Replace NaN with 0
        
        # Apply color mapping
        cmap = PALETTE_MAP.get(self.selected_palette, cm.inferno)
        if self.palette_inverted:
            norm_data = 1.0 - norm_data
            
        colored_data = cmap(norm_data)
        
        # Convert to 8-bit RGB
        image_8bit = (colored_data[:, :, :3] * 255).astype(np.uint8)
        
        # Create QPixmap
        height, width, _ = image_8bit.shape
        q_image = QImage(image_8bit.data, width, height, width * 3, QImage.Format_RGB888)
        self.base_pixmap = QPixmap.fromImage(q_image)
        
        self.display_thermal_image()

    def update_legend(self):
        """
        Update the color bar legend with current palette and temperature range.
        
        This method synchronizes the color bar legend widget with the current
        selected palette, inversion state, and calculated temperature range.
        """
        if self.temperature_data is None:
            return
            
        self.colorbar.set_palette(self.selected_palette, self.palette_inverted)
        self.colorbar.set_range(self.temp_min, self.temp_max)

    def on_palette_changed(self, idx):
        """
        Handle palette selection change.
        
        Args:
            idx (int): Index of the selected palette.
        """
        self.selected_palette = self.palette_combo.currentText()
        self.update_view_only()

    def on_invert_palette(self):
        """Handle palette inversion toggle."""
        self.palette_inverted = not self.palette_inverted
        self.update_view_only()
        self.save_settings_to_json()
        
    def on_thermal_mouse_move(self, point: QPointF):
        """
        Handle mouse movement over thermal image to display temperature tooltip.
        
        Args:
            point (QPointF): Mouse position in image coordinates.
        """
        if self.temperature_data is None:
            self.temp_tooltip_label.setVisible(False)
            return
            
        img_h, img_w = self.temperature_data.shape
        matrix_x = int(point.x())
        matrix_y = int(point.y())
        
        # Check if point is within image bounds
        if 0 <= matrix_x < img_w and 0 <= matrix_y < img_h:
            temperature = self.temperature_data[matrix_y, matrix_x]
            if not np.isnan(temperature):
                try:
                    emissivity = float(self.param_inputs["Emissivity"].text())
                    self.temp_tooltip_label.setText(f"{temperature:.2f} °C | ε: {emissivity:.3f}")
                except (ValueError, KeyError):
                    self.temp_tooltip_label.setText(f"{temperature:.2f} °C")
                    
                # Position tooltip near cursor
                cursor_pos = self.image_view.mapFromGlobal(self.cursor().pos())
                self.temp_tooltip_label.move(cursor_pos.x() + 10, cursor_pos.y() + 10)
                self.temp_tooltip_label.setVisible(True)
                self.temp_tooltip_label.adjustSize()
                return
        
        self.temp_tooltip_label.setVisible(False)
        
    def display_images(self):
        """
        Update the display of images in the view.
        
        This method handles both overlay and side-by-side display modes,
        updating the appropriate image views based on the current mode.
        """
        if self.overlay_mode:
            # Overlay mode: show thermal over visible
            if self.base_pixmap_visible is not None:
                self.image_view.set_visible_pixmap(self.base_pixmap_visible)
                
            offset = QPointF(self.overlay_offset_x, self.overlay_offset_y)
            blend_mode = self.get_qt_composition_mode()
            
            self.image_view.update_overlay(
                visible=True,
                alpha=self.overlay_alpha,
                scale=self.overlay_scale,
                offset=offset,
                blend_mode=blend_mode
            )
            self.secondary_image_view.setVisible(False)
        else:
            # Side-by-side mode: show thermal and visible separately
            self.image_view.update_overlay(visible=False)
            self.display_secondary_image()
            self.secondary_image_view.setVisible(True)
    
    def display_thermal_image(self):
        """Set the thermal image in the primary view."""
        if self.base_pixmap is not None:
            self.image_view.set_thermal_pixmap(self.base_pixmap)
    
    def display_secondary_image(self):
        """Set the visible light image in the secondary view."""
        print(f"display_secondary_image called, pixmap available: {self.base_pixmap_visible is not None}")
        if self.base_pixmap_visible is not None:
            self.secondary_image_view.set_thermal_pixmap(self.base_pixmap_visible)
            print(f"Secondary view pixmap set, size: {self.base_pixmap_visible.size()}")
        else:
            self.secondary_image_view.set_thermal_pixmap(QPixmap())
            print("Secondary view cleared")

    def zoom_in(self):
        """Zoom in both image views."""
        self.image_view.zoom_in()
        if hasattr(self, 'secondary_image_view'):
            self.secondary_image_view.zoom_in()

    def zoom_out(self):
        """Zoom out both image views."""
        self.image_view.zoom_out()
        if hasattr(self, 'secondary_image_view'):
            self.secondary_image_view.zoom_out()

    def zoom_reset(self):
        """Reset zoom level to fit in both image views."""
        self.image_view.reset_zoom()
        if hasattr(self, 'secondary_image_view'):
            self.secondary_image_view.reset_zoom()
            
    def on_overlay_toggled(self, checked: bool):
        """
        Handle overlay mode toggle.
        
        Args:
            checked (bool): Whether overlay mode is enabled.
        """
        self.overlay_mode = checked
        self.set_overlay_controls_visible(checked)
        
        if checked and self.base_pixmap_visible is not None:
            self.image_view.set_visible_pixmap(self.base_pixmap_visible)
        
        self.display_images()

    def on_overlay_alpha_changed(self, value: int):
        """
        Handle overlay opacity change.
        
        Args:
            value (int): Opacity value (0-100).
        """
        self.overlay_alpha = max(0.0, min(1.0, value / 100.0))
        if self.overlay_mode:
            self.display_images()

    def on_scale_spin_changed(self, value: float):
        """
        Handle overlay scale change.
        
        Args:
            value (float): Scale factor for thermal overlay.
        """
        self.overlay_scale = float(value)
        if self.overlay_mode:
            self.display_images()
            if hasattr(self.image_view, 'get_scale_info'):
                scale_info = self.image_view.get_scale_info()
                print(f"Scale info: {scale_info}")

    def on_offsetx_changed(self, value: int):
        """
        Handle X offset change for overlay alignment.
        
        Args:
            value (int): X offset in pixels.
        """
        self.overlay_offset_x = float(value)
        if self.overlay_mode:
            self.display_images()

    def on_offsety_changed(self, value: int):
        """
        Handle Y offset change for overlay alignment.
        
        Args:
            value (int): Y offset in pixels.
        """
        self.overlay_offset_y = float(value)
        if self.overlay_mode:
            self.display_images()

    def on_reset_alignment(self):
        """Reset overlay alignment to metadata values."""
        self.overlay_scale = float(self.meta_overlay_scale)
        self.overlay_offset_x = float(self.meta_offset_x)
        self.overlay_offset_y = float(self.meta_offset_y)
        
        # Update UI controls
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
            
        self.display_images()

    def on_blend_mode_changed(self, mode: str):
        """
        Handle blend mode change for overlay.
        
        Args:
            mode (str): Name of the blend mode.
        """
        self.overlay_blend_mode = mode
        if self.overlay_mode:
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
        """
        Convert blend mode name to Qt composition mode constant.
        
        Returns:
            QPainter.CompositionMode: Qt composition mode constant.
        """
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
        """
        Set visibility of overlay control widgets.
        
        Args:
            visible (bool): Whether overlay controls should be visible.
        """
        if hasattr(self, 'overlay_action') and self.overlay_action is not None:
            self.overlay_action.setVisible(visible)
        self.action_reset_align.setVisible(visible)

    def resizeEvent(self, event):
        """
        Handle window resize events.
        
        Args:
            event: Qt resize event.
        """
        super().resizeEvent(event)
        if hasattr(self, 'secondary_image_view') and self.base_pixmap_visible is not None:
            self.display_secondary_image()

    def sync_views(self):
        """Synchronize zoom and pan between the two ImageGraphicsView instances."""
        self.image_view.view_transformed.connect(self.on_primary_view_transformed)
        self.secondary_image_view.view_transformed.connect(self.on_secondary_view_transformed)
        
    def on_primary_view_transformed(self, zoom_factor: float, pan_offset: QPointF, pixmap_size: tuple):
        """
        Synchronize secondary view when primary view transform changes.
        
        Args:
            zoom_factor (float): Current zoom factor.
            pan_offset (QPointF): Current pan offset.
            pixmap_size (tuple): Size of the pixmap being displayed.
        """
        if hasattr(self, 'secondary_image_view') and self.secondary_image_view.isVisible():
            self.secondary_image_view.sync_transform(zoom_factor, pan_offset, pixmap_size)
            
    def on_secondary_view_transformed(self, zoom_factor: float, pan_offset: QPointF, pixmap_size: tuple):
        """
        Synchronize primary view when secondary view transform changes.
        
        Args:
            zoom_factor (float): Current zoom factor.
            pan_offset (QPointF): Current pan offset.
            pixmap_size (tuple): Size of the pixmap being displayed.
        """
        if self.image_view.isVisible():
            self.image_view.sync_transform(zoom_factor, pan_offset, pixmap_size)
    
    def update_roi_analysis(self):
        """
        Update ROI analysis after creation or modification.
        
        This method iterates through all ROIs and calculates temperature
        statistics for each one. It then updates the ROI table and refreshes
        the visual labels on the ROI items.
        """
        import numpy as np
        print(f"Updating ROI analysis for {len(self.rois)} ROIs...")
        
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
                    # No valid temperature data
                    roi_model.temp_min = roi_model.temp_max = roi_model.temp_mean = None
                    roi_model.temp_std = roi_model.temp_median = None
            else:
                # ROI computation failed
                roi_model.temp_min = roi_model.temp_max = roi_model.temp_mean = None
                roi_model.temp_std = roi_model.temp_median = None
                
        self.update_roi_table()
        
        # Refresh visual labels on ROI items
        for roi_model in self.rois:
            item = self.roi_items.get(roi_model.id)
            if item and hasattr(item, "refresh_label"):
                item.refresh_label()

        print(f"ROI analysis completed. Total ROIs: {len(self.rois)}")
        self.save_settings_to_json()

    def update_roi_table(self):
        """
        Update the ROI table with current data.
        
        This method clears all existing rows and repopulates the table
        with updated ROI data including names, emissivity values, and
        calculated temperature statistics.
        """
        print("Updating ROI table...")
        self._updating_roi_table = True
        
        try:
            # Block signals during update to prevent recursion
            blocker = QSignalBlocker(self.roi_table)

            # Clear and recreate table content
            self.roi_table.setRowCount(0)
            self.roi_table.clearContents()
            self.roi_table.setRowCount(len(self.rois))

            for row, roi in enumerate(self.rois):
                # Name column (editable)
                name_item = QTableWidgetItem(roi.name)
                name_item.setData(Qt.UserRole, roi.id)  # Store ROI ID for reference
                self.roi_table.setItem(row, 0, name_item)

                # Emissivity column (editable)
                emissivity_value = getattr(roi, 'emissivity', 0.95)
                emissivity_item = QTableWidgetItem(f"{emissivity_value:.3f}")
                self.roi_table.setItem(row, 1, emissivity_item)

                # Temperature statistics columns (read-only)
                if (hasattr(roi, 'temp_min') and roi.temp_min is not None and 
                    hasattr(roi, 'temp_max') and roi.temp_max is not None and
                    hasattr(roi, 'temp_mean') and roi.temp_mean is not None):
                    
                    min_item = QTableWidgetItem(f"{roi.temp_min:.2f}")
                    max_item = QTableWidgetItem(f"{roi.temp_max:.2f}")
                    avg_item = QTableWidgetItem(f"{roi.temp_mean:.2f}")
                    
                    # Handle median value
                    median_value = getattr(roi, 'temp_median', None)
                    if median_value is None:
                        median_value = self.calculate_roi_median(roi)
                    median_item = QTableWidgetItem(
                        f"{median_value:.2f}" if median_value is not None else "N/A"
                    )
                else:
                    # No temperature data available
                    min_item = QTableWidgetItem("N/A")
                    max_item = QTableWidgetItem("N/A")
                    avg_item = QTableWidgetItem("N/A")
                    median_item = QTableWidgetItem("N/A")

                # Make temperature columns read-only and visually distinct
                for item in [min_item, max_item, avg_item, median_item]:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    from PySide6.QtWidgets import QApplication
                    palette = QApplication.palette()
                    disabled_color = palette.color(palette.ColorRole.Window)
                    item.setBackground(disabled_color)

                # Set items in table
                self.roi_table.setItem(row, 2, min_item)
                self.roi_table.setItem(row, 3, max_item)
                self.roi_table.setItem(row, 4, avg_item)
                self.roi_table.setItem(row, 5, median_item)

            print(f"ROI table updated with {len(self.rois)} rows")
            
        finally:
            del blocker  # Re-enable signals
            self._updating_roi_table = False

    def calculate_roi_median(self, roi):
        """
        Calculate the median temperature for an ROI.
        
        Args:
            roi: ROI model object.
            
        Returns:
            float or None: Median temperature or None if calculation fails.
        """
        import numpy as np
        temps = self.compute_roi_temperatures(roi)
        if temps is None:
            return None
            
        valid = temps[~np.isnan(temps)]
        if valid.size == 0:
            return None
            
        return float(np.median(valid))

    def on_roi_table_selection_changed(self):
        """Handle selection changes in the ROI table."""
        current_row = self.roi_table.currentRow()
        if current_row >= 0 and current_row < len(self.rois):
            roi = self.rois[current_row]
            if roi.id in self.roi_items:
                roi_item = self.roi_items[roi.id]
                
                # Clear other selections
                for item in self.image_view._scene.selectedItems():
                    item.setSelected(False)
                    
                # Select and center on the ROI item
                roi_item.setSelected(True)
                self.image_view.centerOn(roi_item)

    def on_roi_table_item_changed(self, item):
        """
        Handle changes to ROI table items.
        
        Args:
            item (QTableWidgetItem): The changed table item.
        """
        if item is None or self._updating_roi_table:
            return
            
        row = item.row()
        col = item.column()
        
        if row >= len(self.rois):
            return
            
        roi = self.rois[row]
        
        if col == 0:
            # Name column changed
            new_name = item.text().strip()
            if new_name:
                roi.name = new_name
                print(f"Updated ROI name to: {new_name}")
                self.save_settings_to_json()
            else:
                item.setText(roi.name)  # Restore original name
                
        elif col == 1:
            # Emissivity column changed
            try:
                new_emissivity = float(item.text())
                if 0.0 <= new_emissivity <= 1.0:
                    roi.emissivity = new_emissivity
                    print(f"Updated ROI emissivity to: {new_emissivity}")
                    self.update_roi_analysis()  # Recalculate with new emissivity
                else:
                    # Invalid range - restore original value
                    emissivity_value = getattr(roi, 'emissivity', 0.95)
                    item.setText(f"{emissivity_value:.3f}")
                    QMessageBox.warning(self, "Invalid Emissivity", 
                                      "Emissivity must be between 0.0 and 1.0")
            except ValueError:
                # Invalid number - restore original value
                emissivity_value = getattr(roi, 'emissivity', 0.95)
                item.setText(f"{emissivity_value:.3f}")
                QMessageBox.warning(self, "Invalid Emissivity", 
                                  "Please enter a valid number for emissivity")
                                  
        # Refresh the visual label on the ROI item
        item_view = self.roi_items.get(roi.id)
        if item_view and hasattr(item_view, "refresh_label"):
            item_view.refresh_label()

    def delete_selected_roi(self):
        """Delete all selected ROIs from the table."""
        selected_rows = []
        for item in self.roi_table.selectedItems():
            row = item.row()
            if row not in selected_rows:
                selected_rows.append(row)
        
        if not selected_rows:
            QMessageBox.information(self, "No Selection", 
                                  "Please select one or more ROIs to delete.")
            return
            
        # Sort in reverse order to delete from bottom up
        selected_rows.sort(reverse=True)
        
        # Confirm deletion for multiple ROIs
        if len(selected_rows) > 1:
            reply = QMessageBox.question(
                self, "Delete Multiple ROIs", 
                f"Are you sure you want to delete {len(selected_rows)} ROIs?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
                
        # Delete selected ROIs
        for row in selected_rows:
            if row >= len(self.rois):
                continue
                
            roi = self.rois[row]
            
            # Remove from scene and items dict
            if roi.id in self.roi_items:
                roi_item = self.roi_items[roi.id]
                self.image_view._scene.removeItem(roi_item)
                del self.roi_items[roi.id]
                
            # Remove from ROIs list
            self.rois.pop(row)
            print(f"Deleted ROI: {roi.name}")
            
        self.update_roi_analysis()
        self.save_settings_to_json()

    def clear_all_rois(self, confirm=True):
        """
        Remove all ROIs from the analysis.
        
        Args:
            confirm (bool): Whether to show confirmation dialogue.
        """
        if not self.rois:
            return
        
        should_clear = True
        if confirm:
            reply = QMessageBox.question(
                self, "Clear All ROIs", 
                "Are you sure you want to delete all ROIs?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            should_clear = (reply == QMessageBox.Yes)
        
        if should_clear:
            # Remove all ROI items from scene
            for roi_item in self.roi_items.values():
                self.image_view._scene.removeItem(roi_item)
                
            # Clear data structures
            self.rois.clear()
            self.roi_items.clear()
            self.update_roi_analysis()
            
            print("Cleared all ROIs")
            
        # Save settings if not ignoring auto-save
        if (should_clear and hasattr(self, 'current_image_path') and 
            self.current_image_path and not getattr(self, '_ignore_auto_save', False)):
            self.save_settings_to_json()

    def activate_spot_tool(self):
        """Activate the spot ROI creation tool."""
        self.current_drawing_tool = "spot"
        if hasattr(self, "image_view"):
            self.image_view.setCursor(Qt.CrossCursor)
            
        # Update button states
        self.btn_rect.setChecked(False)
        self.btn_poly.setChecked(False)
        self.btn_spot.setChecked(True)

    def activate_rect_tool(self):
        """Activate the rectangular ROI creation tool."""
        self.current_drawing_tool = "rect"
        if hasattr(self, "image_view"):
            self.image_view.setCursor(Qt.CrossCursor)
            
        # Update button states
        self.btn_spot.setChecked(False)
        self.btn_poly.setChecked(False)
        self.btn_rect.setChecked(True)

    def activate_polygon_tool(self):
        """Activate the polygon ROI creation tool."""
        self.current_drawing_tool = "polygon"
        if hasattr(self, "image_view"):
            self.image_view.setCursor(Qt.CrossCursor)
            self.image_view.setFocus()
            
        # Update button states
        self.btn_spot.setChecked(False)
        self.btn_rect.setChecked(False)
        self.btn_poly.setChecked(True)
        
        # Print usage instructions
        print("🔶 Polygon mode activated!")
        print("   • Left click: Add point")
        print("   • ENTER or Double-click: Complete polygon") 
        print("   • Right click: Complete polygon")
        print("   • ESC: Cancel")

    def deactivate_drawing_tools(self):
        """Deactivate all ROI drawing tools."""
        self.current_drawing_tool = None
        if hasattr(self, "image_view"):
            self.image_view.setCursor(Qt.ArrowCursor)
            
        # Uncheck all tool buttons
        if hasattr(self, "btn_spot"):
            self.btn_spot.setChecked(False)
        if hasattr(self, "btn_rect"):
            self.btn_rect.setChecked(False)
        if hasattr(self, "btn_poly"):
            self.btn_poly.setChecked(False)

    def compute_roi_temperatures(self, roi):
        """
        Compute temperature values for pixels within an ROI.
        
        This method extracts temperature data for all pixels contained
        within the specified ROI and applies ROI-specific thermal
        calculations including individual emissivity values.
        
        Args:
            roi: ROI model object (RectROI, SpotROI, or PolygonROI).
            
        Returns:
            np.ndarray or None: Temperature values in Celsius for ROI pixels.
        """
        import numpy as np
        from PySide6.QtCore import QRectF, QPointF
        from analysis.roi_models import SpotROI, PolygonROI

        if self.thermal_data is None or not hasattr(self, "image_view"):
            return None
            
        # Handle different ROI types and extract thermal data
        if isinstance(roi, SpotROI):
            # Circular ROI processing
            h, w = self.thermal_data.shape
            x1, y1, x2, y2 = roi.get_bounds()
            x1, y1 = max(0, int(x1)), max(0, int(y1))
            x2, y2 = min(w, int(x2)), min(h, int(y2))
            
            if x1 >= x2 or y1 >= y2:
                return None
                
            # Create circular mask
            y_indices, x_indices = np.ogrid[y1:y2, x1:x2]
            mask = ((x_indices - roi.x) ** 2 + (y_indices - roi.y) ** 2) <= (roi.radius ** 2)
            thermal_roi = self.thermal_data[y1:y2, x1:x2].astype(np.float64)
            thermal_roi = thermal_roi[mask]
            
            if thermal_roi.size == 0:
                return None
                
        elif isinstance(roi, PolygonROI):
            # Polygon ROI processing
            h, w = self.thermal_data.shape
            x1, y1, x2, y2 = roi.get_bounds()
            x1, y1 = max(0, int(x1)), max(0, int(y1))
            x2, y2 = min(w, int(x2)), min(h, int(y2))
            
            if x1 >= x2 or y1 >= y2:
                return None
                
            # Create polygon mask
            mask = np.zeros((y2 - y1, x2 - x1), dtype=bool)
            for i in range(y2 - y1):
                for j in range(x2 - x1):
                    mask[i, j] = roi.contains_point(x1 + j, y1 + i)
                    
            thermal_roi = self.thermal_data[y1:y2, x1:x2].astype(np.float64)
            thermal_roi = thermal_roi[mask]
            
            if thermal_roi.size == 0:
                return None
        else:
            # Rectangular ROI processing
            item = self.roi_items.get(roi.id)
            if item is not None and item.parentItem() is self.image_view._thermal_item:
                rect = item.mapRectToParent(item.rect()).normalized()
            else:
                rect = QRectF(
                    float(roi.x), float(roi.y), 
                    float(roi.width), float(roi.height)
                ).normalized()

            h, w = self.thermal_data.shape
            x1 = max(0, int(np.floor(rect.left())))
            y1 = max(0, int(np.floor(rect.top())))
            x2 = min(w, int(np.ceil(rect.right())))
            y2 = min(h, int(np.ceil(rect.bottom())))
            
            if x1 >= x2 or y1 >= y2:
                return None

            thermal_roi = self.thermal_data[y1:y2, x1:x2].astype(np.float64)
            
        # Apply thermal calculation with ROI-specific emissivity using refactored method
        emissivity = float(getattr(roi, 'emissivity', 0.95))
        temp_celsius = self._calculate_temperatures_from_raw(thermal_roi, emissivity, debug=False)
        
        # Apply environmental corrections and return
        return self.apply_environmental_correction(temp_celsius)

    def update_single_roi(self, roi_model):
        """
        Update statistics for a single ROI.
        
        Args:
            roi_model: The ROI model to update.
        """
        import numpy as np
        from analysis.roi_models import SpotROI, PolygonROI
        
        if self.thermal_data is None:
            # No thermal data available
            roi_model.temp_min = roi_model.temp_max = roi_model.temp_mean = None
            roi_model.temp_std = None
            if hasattr(roi_model, 'temp_median'):
                roi_model.temp_median = None
        else:
            # Calculate temperature statistics
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
                    # No valid temperature data
                    roi_model.temp_min = roi_model.temp_max = roi_model.temp_mean = None
                    roi_model.temp_std = None
                    if hasattr(roi_model, 'temp_median'):
                        roi_model.temp_median = None
            else:
                # Temperature computation failed
                roi_model.temp_min = roi_model.temp_max = roi_model.temp_mean = None
                roi_model.temp_std = None
                if hasattr(roi_model, 'temp_median'):
                    roi_model.temp_median = None
                    
        # Refresh visual label
        item = self.roi_items.get(roi_model.id)
        if item and hasattr(item, "refresh_label"):
            item.refresh_label()

        self.update_roi_table()
        self.save_settings_to_json()

    def on_label_settings_changed(self):
        """Handle changes to ROI label display settings."""
        self.roi_label_settings = {
            "name": self.cb_label_name.isChecked(),
            "emissivity": self.cb_label_eps.isChecked(),
            "min": self.cb_label_min.isChecked(),
            "max": self.cb_label_max.isChecked(),
            "avg": self.cb_label_avg.isChecked(),
            "median": self.cb_label_med.isChecked(),
        }
        
        # Refresh all ROI labels
        for item in self.roi_items.values():
            if hasattr(item, "refresh_label"):
                item.refresh_label()
    
    def get_json_file_path(self):
        """
        Get the JSON file path associated with the current image.
        
        Returns:
            str or None: Path to the JSON settings file.
        """
        if not self.current_image_path:
            return None
        
        import os
        base_path = os.path.splitext(self.current_image_path)[0]
        return f"{base_path}.json"
    
    def save_settings_to_json(self):
        """
        Save all current settings to a JSON file.
        
        This method saves the complete application state including thermal
        parameters, ROI definitions, palette settings, and overlay configuration
        to a JSON file with the same base name as the current image file.
        
        The saved settings can be automatically reloaded when the same image
        is opened again, providing persistent configuration across sessions.
        """
        if not self.current_image_path or self._ignore_auto_save:
            return
        
        json_path = self.get_json_file_path()
        if not json_path:
            return
        
        try:
            # Collect thermal calculation parameters
            thermal_params = {}
            params_to_save = [
                "Emissivity", "AtmosphericTemperature", 
                "AtmosphericTransmission", "RelativeHumidity"
            ]
            
            for param in params_to_save:
                if param in self.param_inputs and self.param_inputs[param].text():
                    try:
                        thermal_params[param] = float(self.param_inputs[param].text())
                    except ValueError:
                        pass  # Skip invalid values
                        
            # Collect ROI data
            rois_data = []
            for roi in self.rois:
                roi_data = {
                    "type": roi.__class__.__name__,
                    "name": roi.name,
                    "emissivity": getattr(roi, 'emissivity', 0.95)
                }
                
                # Add position data
                if hasattr(roi, 'x') and hasattr(roi, 'y'):
                    roi_data["x"] = roi.x
                    roi_data["y"] = roi.y
                
                # Add geometry-specific data
                if hasattr(roi, 'width') and hasattr(roi, 'height'):
                    roi_data["width"] = roi.width
                    roi_data["height"] = roi.height
                elif hasattr(roi, 'radius'):
                    roi_data["radius"] = roi.radius
                elif hasattr(roi, 'points'):
                    roi_data["points"] = roi.points
                
                rois_data.append(roi_data)
                
            # Collect overlay settings
            overlay_settings = {
                "scale": self.scale_spin.value() if hasattr(self, 'scale_spin') else 1.0,
                "offset_x": self.offsetx_spin.value() if hasattr(self, 'offsetx_spin') else 0,
                "offset_y": self.offsety_spin.value() if hasattr(self, 'offsety_spin') else 0,
                "opacity": self.overlay_alpha_slider.value() if hasattr(self, 'overlay_alpha_slider') else 50,
                "blend_mode": self.blend_combo.currentText() if hasattr(self, 'blend_combo') else "Normal"
            }
            
            # Assemble complete settings data
            settings_data = {
                "version": "1.0",
                "thermal_parameters": thermal_params,
                "rois": rois_data,
                "palette": self.palette_combo.currentText() if hasattr(self, 'palette_combo') else "Iron",
                "palette_inverted": getattr(self, 'palette_inverted', False),
                "overlay_settings": overlay_settings
            }
            
            # Ensure directory exists and save to file
            import os
            os.makedirs(os.path.dirname(json_path), exist_ok=True)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(settings_data, f, indent=2, ensure_ascii=False)
            
            print(f"Settings saved to: {json_path}")
            
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def load_settings_from_json(self):
        """
        Load settings from JSON file if it exists.
        
        This method attempts to load previously saved settings from a JSON file
        associated with the current image. If the file exists, it restores:
        - Thermal calculation parameters
        - Color palette and inversion settings
        - Overlay alignment settings
        - ROI definitions
        
        The loading process is protected against errors and will gracefully
        handle missing or corrupted settings files.
        """
        if not self.current_image_path:
            return
        
        json_path = self.get_json_file_path()
        if not json_path or not os.path.exists(json_path):
            return
        
        try:
            # Disable auto-save during loading to prevent conflicts
            self._ignore_auto_save = True
            
            # Load settings data from file
            with open(json_path, 'r', encoding='utf-8') as f:
                settings_data = json.load(f)
            
            print(f"Loading settings from: {json_path}")
            
            # Restore thermal parameters
            if "thermal_parameters" in settings_data:
                for param, value in settings_data["thermal_parameters"].items():
                    if param in self.param_inputs:
                        self.param_inputs[param].setText(str(value))
                        
            # Restore palette settings
            if "palette" in settings_data:
                palette_name = settings_data["palette"]
                palette_index = self.palette_combo.findText(palette_name)
                if palette_index >= 0:
                    self.palette_combo.setCurrentIndex(palette_index)
                    self.selected_palette = palette_name
                    
            # Restore palette inversion
            if "palette_inverted" in settings_data:
                self.palette_inverted = settings_data["palette_inverted"]
                
            # Restore overlay settings
            if "overlay_settings" in settings_data:
                overlay = settings_data["overlay_settings"]
                
                if "scale" in overlay and hasattr(self, 'scale_spin'):
                    self.scale_spin.setValue(overlay["scale"])
                    self.overlay_scale = overlay["scale"]
                    
                if "offset_x" in overlay and hasattr(self, 'offsetx_spin'):
                    self.offsetx_spin.setValue(overlay["offset_x"])
                    self.overlay_offset_x = overlay["offset_x"]
                    
                if "offset_y" in overlay and hasattr(self, 'offsety_spin'):
                    self.offsety_spin.setValue(overlay["offset_y"])
                    self.overlay_offset_y = overlay["offset_y"]
                    
                if "opacity" in overlay and hasattr(self, 'overlay_alpha_slider'):
                    self.overlay_alpha_slider.setValue(overlay["opacity"])
                    self.overlay_alpha = overlay["opacity"] / 100.0
                    
                if "blend_mode" in overlay and hasattr(self, 'blend_combo'):
                    blend_index = self.blend_combo.findText(overlay["blend_mode"])
                    if blend_index >= 0:
                        self.blend_combo.setCurrentIndex(blend_index)
                        self.overlay_blend_mode = overlay["blend_mode"]
                        
            # Restore ROI definitions
            if "rois" in settings_data:
                self.load_rois_from_data(settings_data["rois"])
                
            # Update visualization if temperature data is available
            if self.temperature_data is not None:
                self.update_view_only()
            
            print(f"Settings loaded successfully from: {json_path}")
            
        except Exception as e:
            print(f"Error loading settings: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Re-enable auto-save
            self._ignore_auto_save = False
    
    def load_rois_from_data(self, rois_data):
        """
        Load ROI definitions from JSON data.
        
        This method reconstructs ROI objects from their JSON representation
        and creates the corresponding visual items in the image view. It
        supports all ROI types (rectangular, spot, and polygon) and handles
        color assignment and positioning.
        
        Args:
            rois_data (list): List of ROI dictionaries from JSON data.
        """
        # Clear existing ROIs first
        self.clear_all_rois()
        
        from analysis.roi_models import RectROI, SpotROI, PolygonROI
        from ui.roi_items import RectROIItem, SpotROIItem, PolygonROIItem
        from PySide6.QtGui import QColor
        
        for roi_data in rois_data:
            try:
                # Extract common ROI properties
                roi_type = roi_data.get("type", "")
                roi_name = roi_data.get("name", "ROI")
                roi_emissivity = roi_data.get("emissivity", 0.95)
                roi_model = None
                roi_item = None
                
                # Create ROI based on type
                if roi_type == "RectROI":
                    x = roi_data.get("x", 0)
                    y = roi_data.get("y", 0)
                    width = roi_data.get("width", 50)
                    height = roi_data.get("height", 50)
                    
                    roi_model = RectROI(x=x, y=y, width=width, height=height, name=roi_name)
                    roi_model.emissivity = roi_emissivity
                    
                    if hasattr(self, 'image_view') and hasattr(self.image_view, '_thermal_item'):
                        roi_item = RectROIItem(roi_model, parent=self.image_view._thermal_item)
                
                elif roi_type == "SpotROI":
                    x = roi_data.get("x", 0)
                    y = roi_data.get("y", 0)
                    radius = roi_data.get("radius", 5)  # Default radius for spot ROI
                    
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
                
                # Add ROI to collections if successfully created
                if roi_model and roi_item:
                    self.rois.append(roi_model)
                    self.roi_items[roi_model.id] = roi_item
                    
                    # Assign distinct color based on ROI index
                    hue = (len(self.rois) * 55) % 360  # Distribute hues around color wheel
                    color = QColor.fromHsv(hue, 220, 255)
                    roi_model.color = color
                    roi_item.set_color(color)
                    roi_item.setZValue(10)  # Ensure ROIs appear above image
                    
                    print(f"ROI loaded: {roi_model}")
            
            except Exception as e:
                print(f"Error loading ROI: {e}")
                
        # Update analysis after loading all ROIs
        self.update_roi_analysis()
    
    def connect_auto_save_signals(self):
        """
        Connect all UI control signals to auto-save functionality.
        
        This method establishes signal connections that trigger automatic
        saving of settings whenever the user modifies thermal parameters,
        palette settings, or overlay controls. This ensures that changes
        are persisted without requiring manual save operations.
        """
        # Connect thermal parameter input signals
        for param_input in self.param_inputs.values():
            if hasattr(param_input, 'editingFinished'):
                param_input.editingFinished.connect(self.save_settings_to_json)
                
        # Connect palette control signals
        if hasattr(self, 'palette_combo'):
            self.palette_combo.currentTextChanged.connect(self.save_settings_to_json)
            
        # Connect overlay control signals
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
        
        print("Auto-save signals connected")