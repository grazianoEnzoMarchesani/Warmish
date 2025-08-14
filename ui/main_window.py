"""
Thermal Analyzer NG - Main Window Module

This module contains the main application window for the thermal imaging analysis
application, providing a complete interface for loading, processing, and analyzing
FLIR thermal images with advanced ROI (Region of Interest) capabilities.
"""

import os

import json
import numpy as np


# Third-party imports

import matplotlib.cm as cm

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QTextEdit, QTabWidget,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QFileDialog, QMessageBox, QSlider, QSpinBox,
    QDoubleSpinBox, QComboBox, QApplication, QToolBar
)
from PySide6.QtCore import Qt, QPointF, QRectF, QSignalBlocker, QTimer
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QAction, QKeySequence

from ui.widgets.image_graphics_view import ImageGraphicsView
from ui.widgets.color_bar_legend import ColorBarLegend
from constants import *

from core.thermal_engine import ThermalEngine
from core.roi_controller import ROIController
from core.settings_manager import SettingsManager


class ThermalAnalyzerNG(QMainWindow):
    """
    Main window for the Thermal Analyzer NG application.
    
    This class now acts as an orchestrator, coordinating interactions between
    the UI components and the business logic classes (ThermalEngine, 
    ROIController, SettingsManager).
    """
    
    def __init__(self, parent=None):
        """Initialize the main window and setup the user interface."""
        super().__init__(parent)
        
        self.setWindowTitle("Thermal Analyzer NG")
        self.setMinimumSize(1200, 800)
        
        # Initialize business logic components
        self.thermal_engine = ThermalEngine()
        self.roi_controller = ROIController(self.thermal_engine)
        self.settings_manager = SettingsManager()
        
        # Initialize UI data storage
        self._init_ui_storage()
        
        # Setup UI components
        self._setup_menu_bar()
        self._setup_toolbar()
        self._setup_main_layout()
        self._setup_sidebar_tabs()
        
        # Connect business logic signals
        self._connect_business_logic_signals()
        
        # Connect UI signals
        self._connect_ui_signals()
        
        print("Main window initialization completed.")

    def _init_ui_storage(self):
        """Initialize UI-specific data storage variables."""
        # UI state variables
        self.roi_items = {}
        self.current_drawing_tool = None
        self._updating_roi_table = False
        
        # Temperature range (for UI display)
        self.temp_min = 0.0
        self.temp_max = 100.0
        self.base_pixmap = None
        self.base_pixmap_visible = None
        
        # Palette settings
        self.selected_palette = "Iron"
        self.palette_inverted = False
        
        # Overlay settings
        self.overlay_mode = False
        self.overlay_alpha = 0.5
        self.overlay_scale = 1.0
        self.overlay_offset_x = 0.0
        self.overlay_offset_y = 0.0
        self.overlay_blend_mode = "Normal"
        
        # ROI label settings
        self.roi_label_settings = {
            "name": True,
            "emissivity": True,
            "min": True,
            "max": True,
            "avg": True,
            "median": False,
        }

    def _connect_business_logic_signals(self):
        """Connect signals from business logic components."""
        # ThermalEngine signals
        self.thermal_engine.data_loaded.connect(self.on_thermal_data_loaded)
        self.thermal_engine.temperatures_calculated.connect(self.on_temperatures_calculated)
        self.thermal_engine.error_occurred.connect(self.on_thermal_error)
        
        # ROIController signals
        self.roi_controller.roi_added.connect(self.on_roi_added)
        self.roi_controller.roi_removed.connect(self.on_roi_removed)
        self.roi_controller.roi_modified.connect(self.on_roi_modified)
        self.roi_controller.rois_cleared.connect(self.on_rois_cleared)
        self.roi_controller.analysis_updated.connect(self.on_roi_analysis_updated)
        
        # SettingsManager signals
        self.settings_manager.settings_loaded.connect(self.on_settings_loaded)
        self.settings_manager.settings_saved.connect(self.on_settings_saved)
        self.settings_manager.error_occurred.connect(self.on_settings_error)

    def open_image(self):
        """Open and load a FLIR thermal image file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select FLIR Image", "", "JPEG Images (*.jpg *.jpeg)"
        )
        if not file_path: 
            return
            
        # Reset application state
        self.reset_application_state()
        
        # Update window title
        self.setWindowTitle(f"Warmish - {file_path.split('/')[-1]}")
        
        # Load thermal data using engine
        if self.thermal_engine.load_thermal_image(file_path):
            # Set image path for settings
            self.settings_manager.set_current_image_path(file_path)
            
            # Load saved settings
            self.settings_manager.load_settings()
        else:
            QMessageBox.critical(self, "Error", "Failed to load thermal image")

    def on_thermal_data_loaded(self):
        """Handle thermal data loaded event."""
        print("Thermal data loaded successfully")
        
        # Populate thermal parameters from metadata
        self.populate_params_from_engine()
        
        # Calculate initial temperatures
        thermal_params = self.get_current_thermal_parameters()
        self.thermal_engine.calculate_temperatures(thermal_params)

    def on_temperatures_calculated(self):
        """Handle temperatures calculated event."""
        print("Temperatures calculated successfully")
        
        # Update temperature range for UI
        self.temp_min = self.thermal_engine.temp_min
        self.temp_max = self.thermal_engine.temp_max
        
        # Update visualization
        self.update_thermal_display()
        self.update_legend()
        self.display_images()

    def populate_params_from_engine(self):
        """Populate UI thermal parameter inputs from engine metadata."""
        if not self.thermal_engine.metadata:
            return
            
        thermal_params = self.thermal_engine.get_thermal_parameters_from_metadata()
        
        # Update UI inputs
        for key, value in thermal_params.items():
            if key in self.param_inputs:
                line_edit = self.param_inputs[key]
                
                if value is not None:
                    # Format appropriately based on parameter type
                    if key in ["PlanckR1", "PlanckR2", "PlanckB", "PlanckF", "PlanckO"]:
                        line_edit.setText(f"{float(value):.12f}")
                    elif key in ["Emissivity", "ReflectedApparentTemperature", "AtmosphericTransmission"]:
                        line_edit.setText(f"{float(value):.6f}")
                    else:
                        line_edit.setText(f"{float(value):.4f}")
                    
                    line_edit.setStyleSheet("")
                    line_edit.setToolTip("")
                else:
                    line_edit.setText("N/A")
                    line_edit.setStyleSheet("background-color: #f8d7da;")
                    line_edit.setToolTip("Parameter not available in EXIF metadata")

    def get_current_thermal_parameters(self) -> dict:
        """Get current thermal parameters from UI inputs."""
        parameters = {}
        
        for key, line_edit in self.param_inputs.items():
            text = line_edit.text().strip()
            if text and text != "N/A":
                try:
                    parameters[key] = float(text)
                except ValueError:
                    pass  # Skip invalid values
                    
        return parameters

    def recalculate_and_update_view(self):
        """Recalculate temperatures and update the complete view."""
        thermal_params = self.get_current_thermal_parameters()
        
        if self.thermal_engine.calculate_temperatures(thermal_params):
            # Update ROI analysis with new temperatures
            self.roi_controller.update_all_analyses()
            
            # Auto-save settings
            self.auto_save_settings()

    def update_thermal_display(self):
        """Update the thermal image display with current palette settings."""
        pixmap = self.thermal_engine.create_colored_pixmap(
            self.selected_palette, self.palette_inverted
        )
        
        if not pixmap.isNull():
            self.base_pixmap = pixmap
            self.display_thermal_image()

    def create_rect_roi(self, thermal_rect: QRectF):
        """Create a rectangular ROI from the image view signal.
        
        Args:
            thermal_rect (QRectF): Rectangle in thermal image coordinates.
        """
        # Use ROI controller to create the ROI
        roi_model = self.roi_controller.create_rect_roi(
            x=thermal_rect.x(),
            y=thermal_rect.y(),
            width=thermal_rect.width(),
            height=thermal_rect.height()
        )
        
        print(f"Created rectangular ROI: {roi_model.name}")

    def create_spot_roi(self, center_point: QPointF, radius: float):
        """Create a spot ROI from the image view signal.
        
        Args:
            center_point (QPointF): Center point in thermal image coordinates.
            radius (float): Radius in thermal pixels.
        """
        # Use ROI controller to create the ROI
        roi_model = self.roi_controller.create_spot_roi(
            x=center_point.x(),
            y=center_point.y(),
            radius=radius
        )
        
        print(f"Created spot ROI: {roi_model.name}")

    def create_polygon_roi(self, points: list):
        """Create a polygon ROI from the image view signal.
        
        Args:
            points (list): List of (x, y) coordinate tuples in thermal image space.
        """
        # Use ROI controller to create the ROI
        roi_model = self.roi_controller.create_polygon_roi(points=points)
        
        print(f"Created polygon ROI: {roi_model.name}")

    def on_roi_added(self, roi_model):
        """Handle ROI added event from controller."""
        from ui.roi_items import RectROIItem, SpotROIItem, PolygonROIItem
        
        print(f"ROI added: {roi_model.name}")
        
        # Create appropriate visual item
        roi_item = None
        if roi_model.__class__.__name__ == "RectROI":
            roi_item = RectROIItem(roi_model, parent=self.image_view._thermal_item)
        elif roi_model.__class__.__name__ == "SpotROI":
            roi_item = SpotROIItem(roi_model, parent=self.image_view._thermal_item)
        elif roi_model.__class__.__name__ == "PolygonROI":
            roi_item = PolygonROIItem(roi_model, parent=self.image_view._thermal_item)
        
        if roi_item:
            # Setup visual properties
            roi_item.set_color(roi_model.color)
            roi_item.setZValue(10)
            
            # Register in UI collection
            self.roi_items[roi_model.id] = roi_item
            
            # Update table
            self.update_roi_table()
            
            # Auto-save
            self.auto_save_settings()

    def auto_save_settings(self):
        """Automatically save current settings if enabled."""
        if not self.settings_manager.is_auto_save_enabled():
            return
            
        thermal_params = self.get_current_thermal_parameters()
        palette_settings = {
            "palette": self.selected_palette,
            "inverted": self.palette_inverted
        }
        overlay_settings = {
            "scale": self.overlay_scale,
            "offset_x": self.overlay_offset_x,
            "offset_y": self.overlay_offset_y,
            "opacity": int(self.overlay_alpha * 100),
            "blend_mode": self.overlay_blend_mode
        }
        roi_data = self.roi_controller.export_roi_data()
        
        self.settings_manager.save_settings(
            thermal_parameters=thermal_params,
            palette_settings=palette_settings,
            overlay_settings=overlay_settings,
            roi_data=roi_data,
            roi_label_settings=self.roi_label_settings
        )

    def on_settings_loaded(self, settings_data):
        """Handle settings loaded event."""
        print("Applying loaded settings...")
        
        # Disable auto-save during loading
        self.settings_manager.set_auto_save_enabled(False)
        
        try:
            # Apply thermal parameters
            if "thermal_parameters" in settings_data:
                for param, value in settings_data["thermal_parameters"].items():
                    if param in self.param_inputs:
                        self.param_inputs[param].setText(str(value))
                        
            # Apply palette settings
            if "palette" in settings_data:
                palette_name = settings_data["palette"]
                index = self.palette_combo.findText(palette_name)
                if index >= 0:
                    self.palette_combo.setCurrentIndex(index)
                    self.selected_palette = palette_name
                    
            self.palette_inverted = settings_data.get("palette_inverted", False)
            if hasattr(self, 'invert_palette_button'):
                self.invert_palette_button.setChecked(self.palette_inverted)
            
            # Apply overlay settings
            overlay = settings_data.get("overlay_settings", {})
            self.overlay_scale = overlay.get("scale", 1.0)
            self.overlay_offset_x = overlay.get("offset_x", 0.0)
            self.overlay_offset_y = overlay.get("offset_y", 0.0)
            self.overlay_alpha = overlay.get("opacity", 50) / 100.0
            self.overlay_blend_mode = overlay.get("blend_mode", "Normal")
            
            # Update overlay UI controls
            if hasattr(self, 'scale_spin'):
                self.scale_spin.blockSignals(True)
                self.scale_spin.setValue(self.overlay_scale)
                self.scale_spin.blockSignals(False)
            
            if hasattr(self, 'offsetx_spin'):
                self.offsetx_spin.blockSignals(True)
                self.offsetx_spin.setValue(int(self.overlay_offset_x))
                self.offsetx_spin.blockSignals(False)
            
            if hasattr(self, 'offsety_spin'):
                self.offsety_spin.blockSignals(True)
                self.offsety_spin.setValue(int(self.overlay_offset_y))
                self.offsety_spin.blockSignals(False)
            
            if hasattr(self, 'overlay_alpha_slider'):
                self.overlay_alpha_slider.blockSignals(True)
                self.overlay_alpha_slider.setValue(int(self.overlay_alpha * 100))
                self.overlay_alpha_slider.blockSignals(False)
            
            if hasattr(self, 'blend_combo'):
                blend_index = self.blend_combo.findText(self.overlay_blend_mode)
                if blend_index >= 0:
                    self.blend_combo.blockSignals(True)
                    self.blend_combo.setCurrentIndex(blend_index)
                    self.blend_combo.blockSignals(False)
            
            # Apply ROI label settings
            roi_labels = settings_data.get("roi_label_settings", {})
            self.roi_label_settings.update(roi_labels)
            
            # Update ROI label checkboxes
            if hasattr(self, 'cb_label_name'):
                self.cb_label_name.setChecked(self.roi_label_settings.get("name", True))
            if hasattr(self, 'cb_label_eps'):
                self.cb_label_eps.setChecked(self.roi_label_settings.get("emissivity", True))
            if hasattr(self, 'cb_label_min'):
                self.cb_label_min.setChecked(self.roi_label_settings.get("min", True))
            if hasattr(self, 'cb_label_max'):
                self.cb_label_max.setChecked(self.roi_label_settings.get("max", True))
            if hasattr(self, 'cb_label_avg'):
                self.cb_label_avg.setChecked(self.roi_label_settings.get("avg", True))
            if hasattr(self, 'cb_label_med'):
                self.cb_label_med.setChecked(self.roi_label_settings.get("median", False))
            
            # Update image view with ROI label settings
            if hasattr(self, 'image_view'):
                self.image_view.set_roi_label_settings(self.roi_label_settings)
            
            # Import ROIs
            roi_data = settings_data.get("rois", [])
            if roi_data:
                self.roi_controller.import_roi_data(roi_data)
                
            # Update view with loaded settings
            if self.thermal_engine.temperature_data is not None:
                self.update_thermal_display()
                
        finally:
            # Re-enable auto-save
            self.settings_manager.set_auto_save_enabled(True)

    def _setup_menu_bar(self):
        """Setup the application menu bar."""
        menubar = self.menuBar()
        
        # File Menu
        file_menu = menubar.addMenu('&File')
        
        # Open action
        open_action = QAction('&Open Image...', self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.setStatusTip('Open a thermal image file')
        open_action.triggered.connect(self.open_image)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        # Exit action
        exit_action = QAction('E&xit', self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.setStatusTip('Exit application')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # View Menu
        view_menu = menubar.addMenu('&View')
        
        # Zoom actions
        zoom_in_action = QAction('Zoom &In', self)
        zoom_in_action.setShortcut(QKeySequence.ZoomIn)
        zoom_in_action.setStatusTip('Zoom in')
        zoom_in_action.triggered.connect(self.zoom_in)
        view_menu.addAction(zoom_in_action)
        
        zoom_out_action = QAction('Zoom &Out', self)
        zoom_out_action.setShortcut(QKeySequence.ZoomOut)
        zoom_out_action.setStatusTip('Zoom out')
        zoom_out_action.triggered.connect(self.zoom_out)
        view_menu.addAction(zoom_out_action)
        
        zoom_reset_action = QAction('&Reset Zoom', self)
        zoom_reset_action.setShortcut('Ctrl+0')
        zoom_reset_action.setStatusTip('Reset zoom to fit')
        zoom_reset_action.triggered.connect(self.zoom_reset)
        view_menu.addAction(zoom_reset_action)
        
        view_menu.addSeparator()
        
        # Overlay toggle
        overlay_action = QAction('Toggle &Overlay', self)
        overlay_action.setCheckable(True)
        overlay_action.setShortcut('Ctrl+O')
        overlay_action.setStatusTip('Toggle overlay mode')
        overlay_action.triggered.connect(self.on_overlay_toggled)
        view_menu.addAction(overlay_action)
        
        # Store overlay action for later use
        self.overlay_action = overlay_action
        
        # Tools Menu
        tools_menu = menubar.addMenu('&Tools')
        
        # ROI tools
        rect_roi_action = QAction('&Rectangle ROI', self)
        rect_roi_action.setShortcut('R')
        rect_roi_action.setStatusTip('Create rectangular ROI')
        rect_roi_action.triggered.connect(self.activate_rect_tool)
        tools_menu.addAction(rect_roi_action)
        
        spot_roi_action = QAction('&Spot ROI', self)
        spot_roi_action.setShortcut('S')
        spot_roi_action.setStatusTip('Create spot ROI')
        spot_roi_action.triggered.connect(self.activate_spot_tool)
        tools_menu.addAction(spot_roi_action)
        
        polygon_roi_action = QAction('&Polygon ROI', self)
        polygon_roi_action.setShortcut('P')
        polygon_roi_action.setStatusTip('Create polygon ROI')
        polygon_roi_action.triggered.connect(self.activate_polygon_tool)
        tools_menu.addAction(polygon_roi_action)
        
        tools_menu.addSeparator()
        
        # Clear ROIs
        clear_rois_action = QAction('&Clear All ROIs', self)
        clear_rois_action.setShortcut('Ctrl+Shift+C')
        clear_rois_action.setStatusTip('Clear all ROIs')
        clear_rois_action.triggered.connect(self.clear_all_rois)
        tools_menu.addAction(clear_rois_action)

    def _setup_toolbar(self):
        """Setup the main toolbar."""
        toolbar = QToolBar('Main Toolbar', self)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)
        
        # Open button
        open_action = QAction('📁 Open', self)
        open_action.setStatusTip('Open thermal image file')
        open_action.triggered.connect(self.open_image)
        toolbar.addAction(open_action)
        
        toolbar.addSeparator()
        
        # Zoom controls
        zoom_in_action = QAction('🔍+ Zoom In', self)
        zoom_in_action.setStatusTip('Zoom in')
        zoom_in_action.triggered.connect(self.zoom_in)
        toolbar.addAction(zoom_in_action)
        
        zoom_out_action = QAction('🔍- Zoom Out', self)
        zoom_out_action.setStatusTip('Zoom out')
        zoom_out_action.triggered.connect(self.zoom_out)
        toolbar.addAction(zoom_out_action)
        
        zoom_reset_action = QAction('🔍= Reset', self)
        zoom_reset_action.setStatusTip('Reset zoom to fit')
        zoom_reset_action.triggered.connect(self.zoom_reset)
        toolbar.addAction(zoom_reset_action)
        
        toolbar.addSeparator()
        
        # ROI tools
        rect_roi_action = QAction('⬜ Rectangle', self)
        rect_roi_action.setStatusTip('Create rectangular ROI')
        rect_roi_action.triggered.connect(self.activate_rect_tool)
        toolbar.addAction(rect_roi_action)
        
        spot_roi_action = QAction('🎯 Spot', self)
        spot_roi_action.setStatusTip('Create spot ROI')
        spot_roi_action.triggered.connect(self.activate_spot_tool)
        toolbar.addAction(spot_roi_action)
        
        polygon_roi_action = QAction('🔶 Polygon', self)
        polygon_roi_action.setStatusTip('Create polygon ROI')
        polygon_roi_action.triggered.connect(self.activate_polygon_tool)
        toolbar.addAction(polygon_roi_action)
        
        toolbar.addSeparator()
        
        # Overlay toggle
        overlay_toggle_action = QAction('🔄 Overlay', self)
        overlay_toggle_action.setCheckable(True)
        overlay_toggle_action.setStatusTip('Toggle overlay mode')
        overlay_toggle_action.triggered.connect(self.on_overlay_toggled)
        toolbar.addAction(overlay_toggle_action)
        
        # Store toolbar overlay action too
        self.toolbar_overlay_action = overlay_toggle_action

    def _setup_main_layout(self):
        """Setup the main application layout with image views and controls."""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # Main horizontal layout
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(12)
        
        # Create image area layout
        self.image_area_widget = QWidget()
        self.image_area_layout = QVBoxLayout(self.image_area_widget)
        self.image_area_layout.setContentsMargins(0, 0, 0, 0)
        self.image_area_layout.setSpacing(8)
        
        # Primary image view (thermal)
        self.image_view = ImageGraphicsView()
        self.image_view.setStyleSheet("border: 1px solid gray; background-color: #333;")
        
        # Connect existing signals
        self.image_view.mouse_moved_on_thermal.connect(self.on_thermal_mouse_move)
        
        # Connect new ROI creation signals
        self.image_view.rect_roi_drawn.connect(self.create_rect_roi)
        self.image_view.spot_roi_drawn.connect(self.create_spot_roi)
        self.image_view.polygon_roi_drawn.connect(self.create_polygon_roi)
        self.image_view.drawing_tool_deactivation_requested.connect(self.deactivate_drawing_tools)
        
        # Connect ROI modification signal
        self.image_view.roi_modified.connect(self.on_roi_modified)

        self.image_area_layout.addWidget(self.image_view, stretch=1)
        
        # Secondary image view (visible light)
        self.secondary_image_view = ImageGraphicsView()
        self.secondary_image_view.setStyleSheet("border: 1px solid gray; background-color: #222;")
        
        # Connect signals for secondary view
        self.secondary_image_view.drawing_tool_deactivation_requested.connect(self.deactivate_drawing_tools)
        self.secondary_image_view.set_allow_roi_drawing(False)
        
        self.image_area_layout.addWidget(self.secondary_image_view, stretch=1)
        
        # Add image area to main layout
        self.main_layout.addWidget(self.image_area_widget, stretch=3)
        
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
        self._setup_overlay_tab()  # Add this new tab
        self._setup_batch_export_tab()

    def _setup_overlay_tab(self):
        """Setup the overlay controls tab."""
        self.tab_overlay = QWidget()
        self.tab_overlay_layout = QVBoxLayout(self.tab_overlay)
        self.tab_overlay_layout.setContentsMargins(16, 16, 16, 16)
        self.tab_overlay_layout.setSpacing(12)
        
        # Overlay toggle group
        self.overlay_groupbox = QGroupBox("Overlay Mode")
        self.overlay_layout = QFormLayout(self.overlay_groupbox)
        
        # Overlay toggle checkbox
        self.overlay_checkbox = QCheckBox("Enable Overlay")
        self.overlay_checkbox.toggled.connect(self.on_overlay_toggled)
        self.overlay_layout.addRow("", self.overlay_checkbox)
        
        # Opacity slider
        self.overlay_alpha_label = QLabel("Opacity: 50%")
        self.overlay_alpha_slider = QSlider(Qt.Horizontal)
        self.overlay_alpha_slider.setMinimum(0)
        self.overlay_alpha_slider.setMaximum(100)
        self.overlay_alpha_slider.setValue(50)
        self.overlay_alpha_slider.valueChanged.connect(self.on_overlay_alpha_changed)
        self.overlay_alpha_slider.valueChanged.connect(
            lambda v: self.overlay_alpha_label.setText(f"Opacity: {v}%")
        )
        self.overlay_layout.addRow(self.overlay_alpha_label, self.overlay_alpha_slider)
        
        self.tab_overlay_layout.addWidget(self.overlay_groupbox)
        
        # Alignment controls group
        self.alignment_groupbox = QGroupBox("Alignment Controls")
        self.alignment_layout = QFormLayout(self.alignment_groupbox)
        
        # Scale control
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setMinimum(0.1)
        self.scale_spin.setMaximum(5.0)
        self.scale_spin.setSingleStep(0.01)
        self.scale_spin.setDecimals(3)
        self.scale_spin.setValue(1.0)
        self.scale_spin.valueChanged.connect(self.on_scale_spin_changed)
        self.alignment_layout.addRow("Scale Factor:", self.scale_spin)
        
        # X offset control
        self.offsetx_spin = QSpinBox()
        self.offsetx_spin.setMinimum(-1000)
        self.offsetx_spin.setMaximum(1000)
        self.offsetx_spin.setValue(0)
        self.offsetx_spin.valueChanged.connect(self.on_offsetx_changed)
        self.alignment_layout.addRow("X Offset (px):", self.offsetx_spin)
        
        # Y offset control
        self.offsety_spin = QSpinBox()
        self.offsety_spin.setMinimum(-1000)
        self.offsety_spin.setMaximum(1000)
        self.offsety_spin.setValue(0)
        self.offsety_spin.valueChanged.connect(self.on_offsety_changed)
        self.alignment_layout.addRow("Y Offset (px):", self.offsety_spin)
        
        # Reset alignment button
        self.reset_alignment_button = QPushButton("Reset to Metadata")
        self.reset_alignment_button.clicked.connect(self.on_reset_alignment)
        self.alignment_layout.addRow("", self.reset_alignment_button)
        
        self.tab_overlay_layout.addWidget(self.alignment_groupbox)
        
        # Blend mode group
        self.blend_groupbox = QGroupBox("Blend Mode")
        self.blend_layout = QFormLayout(self.blend_groupbox)
        
        # Blend mode combo
        self.blend_combo = QComboBox()
        blend_modes = ["Normal", "Multiply", "Screen", "Overlay", "Difference", "HardLight"]
        self.blend_combo.addItems(blend_modes)
        self.blend_combo.currentTextChanged.connect(self.on_blend_mode_changed)
        self.blend_layout.addRow("Blend Mode:", self.blend_combo)
        
        self.tab_overlay_layout.addWidget(self.blend_groupbox)
        
        # Add stretch to push everything to top
        self.tab_overlay_layout.addStretch()
        
        self.sidebar_tabs.addTab(self.tab_overlay, "Overlay")
        
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
        
        # Palette selection group
        self.palette_groupbox = QGroupBox("Color Palette")
        self.palette_layout = QFormLayout(self.palette_groupbox)
        
        # Palette combo box
        self.palette_combo = QComboBox()
        palette_names = list(PALETTE_MAP.keys())
        self.palette_combo.addItems(palette_names)
        self.palette_combo.setCurrentText("Iron")  # Set default
        self.palette_layout.addRow("Palette:", self.palette_combo)
        
        # Palette invert button
        self.invert_palette_button = QPushButton("Invert Palette")
        self.invert_palette_button.setCheckable(True)
        self.invert_palette_button.clicked.connect(self.on_invert_palette)
        self.palette_layout.addRow("", self.invert_palette_button)
        
        self.tab_params_layout.addWidget(self.palette_groupbox)
        
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
        """Initialize data storage variables."""
        # Thermal data storage
        self.thermal_data = None
        self.temperature_data = None
        self.metadata = None
        self.base_pixmap = None
        self.base_pixmap_visible = None
        
        # Palette settings (don't connect signals here - UI not ready yet)
        self.selected_palette = "Iron"
        self.palette_inverted = False
        
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
        
        # Temperature range
        self.temp_min = 0.0
        self.temp_max = 100.0

    def reset_application_state(self):
        """
        Reset the complete application state before loading a new image.
        
        This method clears all ROIs, resets thermal parameters to defaults,
        and restores UI controls to their initial state. It's called when
        loading a new thermal image to ensure clean state.
        """
        try:
            # Disable auto-save during reset
            if hasattr(self, 'settings_manager'):
                self.settings_manager.set_auto_save_enabled(False)
            
            print("Resetting application state...")
            
            # Clear all existing ROIs without confirmation
            if hasattr(self, 'roi_controller'):
                self.roi_controller.clear_all_rois()
            
            # Reset thermal engine
            if hasattr(self, 'thermal_engine'):
                self.thermal_engine.reset_data()
            
            # Reset UI variables
            self.base_pixmap = None
            self.base_pixmap_visible = None
            self.temp_min = 0.0
            self.temp_max = 100.0
            
            # Reset palette settings
            if hasattr(self, 'palette_combo'):
                self.palette_combo.setCurrentText("Iron")
            self.selected_palette = "Iron"
            self.palette_inverted = False
            
            # Reset overlay settings to defaults
            self.overlay_scale = 1.0
            self.overlay_offset_x = 0.0
            self.overlay_offset_y = 0.0
            self.overlay_alpha = 0.5
            self.overlay_blend_mode = "Normal"
            
            print("State reset completed")
            
        except Exception as e:
            print(f"Error during state reset: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Re-enable auto-save
            if hasattr(self, 'settings_manager'):
                self.settings_manager.set_auto_save_enabled(True)

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
        self.auto_save_settings()  # Era save_settings_to_json()
        
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
        # Sync visible image from thermal engine
        if hasattr(self, 'thermal_engine'):
            self.base_pixmap_visible = self.thermal_engine.base_pixmap_visible
        
        print(f"display_images called: overlay_mode={self.overlay_mode}, "
              f"visible_available={self.base_pixmap_visible is not None}")
        
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
        # Always sync from thermal engine first
        if hasattr(self, 'thermal_engine'):
            self.base_pixmap_visible = self.thermal_engine.base_pixmap_visible
        
        print(f"display_secondary_image called, pixmap available: {self.base_pixmap_visible is not None}")
        
        if self.base_pixmap_visible is not None:
            self.secondary_image_view.set_thermal_pixmap(self.base_pixmap_visible)
            print(f"Secondary view pixmap set, size: {self.base_pixmap_visible.size()}")
        else:
            self.secondary_image_view.set_thermal_pixmap(QPixmap())
            print("Secondary view cleared - no visible image available")

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
        """Handle overlay mode toggle.
        
        Args:
            checked (bool): Whether overlay mode is enabled.
        """
        self.overlay_mode = checked
        
        # Sync both menu and toolbar actions
        if hasattr(self, 'overlay_action'):
            self.overlay_action.setChecked(checked)
        if hasattr(self, 'toolbar_overlay_action'):
            self.toolbar_overlay_action.setChecked(checked)
        
        # Update overlay controls visibility
        self.set_overlay_controls_visible(checked)
        
        # Update image display
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
        if not hasattr(self, 'thermal_engine') or not self.thermal_engine.metadata:
            print("No metadata available for overlay reset")
            return
            
        # Get overlay parameters from thermal engine
        overlay_params = self.thermal_engine.get_overlay_parameters_from_metadata()
        
        self.overlay_scale = float(overlay_params.get("scale", 1.0))
        self.overlay_offset_x = float(overlay_params.get("offset_x", 0.0))
        self.overlay_offset_y = float(overlay_params.get("offset_y", 0.0))
        
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
            
        # Update display
        self.display_images()
        
        print(f"Overlay alignment reset to metadata values: scale={self.overlay_scale:.3f}, "
              f"offset=({self.overlay_offset_x:.1f}, {self.overlay_offset_y:.1f})")

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
        """Set visibility of overlay control widgets.
        
        Args:
            visible (bool): Whether overlay controls should be visible.
        """
        # Update menu action if it exists
        if hasattr(self, 'overlay_action') and self.overlay_action is not None:
            self.overlay_action.setChecked(visible)
        
        # Update toolbar action if it exists
        if hasattr(self, 'toolbar_overlay_action') and self.toolbar_overlay_action is not None:
            self.toolbar_overlay_action.setChecked(visible)
            
        # Update overlay checkbox in tab if it exists
        if hasattr(self, 'overlay_checkbox') and self.overlay_checkbox is not None:
            self.overlay_checkbox.blockSignals(True)
            self.overlay_checkbox.setChecked(visible)
            self.overlay_checkbox.blockSignals(False)
        
        # Enable/disable overlay controls based on mode
        overlay_controls = [
            'overlay_alpha_slider', 'overlay_alpha_label',
            'scale_spin', 'offsetx_spin', 'offsety_spin', 
            'reset_alignment_button', 'blend_combo'
        ]
        
        for control_name in overlay_controls:
            if hasattr(self, control_name):
                control = getattr(self, control_name)
                control.setEnabled(visible)

    def resizeEvent(self, event):
        """
        Handle window resize events.
        
        Args:
            event: Qt resize event.
        """
        super().resizeEvent(event)
        if (hasattr(self, 'secondary_image_view') and 
            hasattr(self, 'base_pixmap_visible') and 
            self.base_pixmap_visible is not None):
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
        
        This method delegates to the ROI controller to update all ROI statistics
        and then refreshes the UI components.
        """
        print("Updating ROI analysis...")
        
        # Use ROI controller to update all analyses
        self.roi_controller.update_all_analyses()
        
        # The controller will emit analysis_updated signal which triggers on_roi_analysis_updated
        print("ROI analysis update requested")

    def update_roi_table(self):
        """Update the ROI table with current data.
        
        This method refreshes the ROI analysis table with current ROI data and
        calculated temperature statistics.
        """
        print("Updating ROI table...")
        self._updating_roi_table = True
        
        blocker = None  # Initialize outside try block
        try:
            # Block signals during update to prevent recursion
            blocker = QSignalBlocker(self.roi_table)

            # Get all ROIs from controller
            all_rois = self.roi_controller.get_all_rois()
            
            # Clear and recreate table content
            self.roi_table.setRowCount(0)
            self.roi_table.clearContents()
            self.roi_table.setRowCount(len(all_rois))

            for row, roi in enumerate(all_rois):
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
                    palette = QApplication.palette()
                    disabled_color = palette.color(palette.ColorRole.Window)
                    item.setBackground(disabled_color)

                # Set items in table
                self.roi_table.setItem(row, 2, min_item)
                self.roi_table.setItem(row, 3, max_item)
                self.roi_table.setItem(row, 4, avg_item)
                self.roi_table.setItem(row, 5, median_item)

            print(f"ROI table updated with {len(all_rois)} rows")
            
        except Exception as e:
            print(f"Error updating ROI table: {e}")
        finally:
            if blocker is not None:
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
        all_rois = self.roi_controller.get_all_rois()
        
        if current_row >= 0 and current_row < len(all_rois):
            roi = all_rois[current_row]
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
        
        all_rois = self.roi_controller.get_all_rois()
        if row >= len(all_rois):
            return
            
        roi = all_rois[row]
        
        if col == 0:
            # Name column changed
            new_name = item.text().strip()
            if new_name:
                # Update via controller
                self.roi_controller.update_roi(roi.id, name=new_name)
                print(f"Updated ROI name to: {new_name}")
            else:
                item.setText(roi.name)  # Restore original name
                
        elif col == 1:
            # Emissivity column changed
            try:
                new_emissivity = float(item.text())
                if 0.0 <= new_emissivity <= 1.0:
                    # Update via controller
                    self.roi_controller.update_roi(roi.id, emissivity=new_emissivity)
                    print(f"Updated ROI emissivity to: {new_emissivity}")
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
                
        # Get all ROIs from controller
        all_rois = self.roi_controller.get_all_rois()
        
        # Collect ROI IDs to delete
        roi_ids_to_delete = []
        for row in selected_rows:
            if row < len(all_rois):
                roi_ids_to_delete.append(all_rois[row].id)
                
        # Delete ROIs using controller
        deleted_count = self.roi_controller.delete_rois(roi_ids_to_delete)
        print(f"Deleted {deleted_count} ROIs")

    def clear_all_rois(self, confirm=True):
        """
        Remove all ROIs from the analysis.
        
        Args:
            confirm (bool): Whether to show confirmation dialogue.
        """
        all_rois = self.roi_controller.get_all_rois()
        if not all_rois:
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
            # Use controller to clear all ROIs
            cleared_count = self.roi_controller.clear_all_rois()
            print(f"Cleared {cleared_count} ROIs")

    def activate_spot_tool(self):
        """Activate the spot ROI creation tool."""
        self.current_drawing_tool = "spot"
        # Set the drawing tool on the image view
        self.image_view.set_drawing_tool("spot")
        if hasattr(self, "image_view"):
            self.image_view.setCursor(Qt.CrossCursor)
        
        # Update button states
        self.btn_spot.setChecked(True)
        self.btn_rect.setChecked(False)
        self.btn_poly.setChecked(False)
        print("   • Left click to place spot")
        print("   • ESC: Cancel")

    def activate_rect_tool(self):
        """Activate the rectangular ROI creation tool."""
        self.current_drawing_tool = "rect"
        # Set the drawing tool on the image view
        self.image_view.set_drawing_tool("rect")
        if hasattr(self, "image_view"):
            self.image_view.setCursor(Qt.CrossCursor)
        
        # Update button states
        self.btn_rect.setChecked(True)
        self.btn_spot.setChecked(False)
        self.btn_poly.setChecked(False)
        print("   • Click and drag to draw rectangle")
        print("   • ESC: Cancel")

    def activate_polygon_tool(self):
        """Activate the polygon ROI creation tool."""
        self.current_drawing_tool = "polygon"
        # Set the drawing tool on the image view
        self.image_view.set_drawing_tool("polygon")
        if hasattr(self, "image_view"):
            self.image_view.setCursor(Qt.CrossCursor)
        
        # Update button states
        self.btn_poly.setChecked(True)
        self.btn_spot.setChecked(False)
        self.btn_rect.setChecked(False)
        print("   • Left click to add points")
        print("   • Right click or ENTER to complete")
        print("   • ESC: Cancel")

    def deactivate_drawing_tools(self):
        """Deactivate all ROI drawing tools."""
        self.current_drawing_tool = None
        # Clear the drawing tool on the image view
        self.image_view.set_drawing_tool(None)
        if hasattr(self, "image_view"):
            self.image_view.setCursor(Qt.ArrowCursor)
        
        # Update button states
        if hasattr(self, "btn_spot"):
            self.btn_spot.setChecked(False)
        if hasattr(self, "btn_rect"):
            self.btn_rect.setChecked(False)
        if hasattr(self, "btn_poly"):
            self.btn_poly.setChecked(False)

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
        self.auto_save_settings()

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
        
        # Update ImageGraphicsView with new settings
        self.image_view.set_roi_label_settings(self.roi_label_settings)
        
        # Refresh all ROI labels
        for item in self.roi_items.values():
            if hasattr(item, "refresh_label"):
                item.refresh_label()
        
        # Save settings
        self.auto_save_settings()  # Era save_settings_to_json()
    
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
        # Avoid connecting multiple times
        if hasattr(self, '_auto_save_connected') and self._auto_save_connected:
            return
            
        # Connect thermal parameter input signals
        for param_input in self.param_inputs.values():
            if hasattr(param_input, 'editingFinished'):
                param_input.editingFinished.connect(self.auto_save_settings)
                
        # Connect palette control signals
        if hasattr(self, 'palette_combo'):
            self.palette_combo.currentTextChanged.connect(self.auto_save_settings)
            
        # Connect overlay control signals
        if hasattr(self, 'scale_spin'):
            self.scale_spin.valueChanged.connect(self.auto_save_settings)
        if hasattr(self, 'offsetx_spin'):
            self.offsetx_spin.valueChanged.connect(self.auto_save_settings)
        if hasattr(self, 'offsety_spin'):
            self.offsety_spin.valueChanged.connect(self.auto_save_settings)
        if hasattr(self, 'overlay_alpha_slider'):
            self.overlay_alpha_slider.valueChanged.connect(self.auto_save_settings)
        if hasattr(self, 'blend_combo'):
            self.blend_combo.currentTextChanged.connect(self.auto_save_settings)
        
        self._auto_save_connected = True
        print("Auto-save signals connected")

    def _connect_ui_signals(self):
        """Connect UI signals after all components are created."""
        # Connect palette signals
        self.palette_combo.currentIndexChanged.connect(self.on_palette_changed)
        
        # Initialize ROI label settings in the view
        self.image_view.set_roi_label_settings(self.roi_label_settings)
        
        # Connect overlay checkbox to sync with menu/toolbar
        if hasattr(self, 'overlay_checkbox'):
            self.overlay_checkbox.toggled.connect(lambda checked: [
                self.overlay_action.setChecked(checked) if hasattr(self, 'overlay_action') else None,
                self.toolbar_overlay_action.setChecked(checked) if hasattr(self, 'toolbar_overlay_action') else None
            ])
        
        # Connect export button
        self.btn_export_current.clicked.connect(self.export_current_analysis)
        
        # Connect auto-save signals
        self.connect_auto_save_signals()
        
        # Make secondary view visible by default
        self.secondary_image_view.setVisible(True)

    def export_current_analysis(self):
        """
        Export current thermal analysis including images and data.
        
        This method opens a file dialog to let the user choose a base filename,
        then exports all analysis data including thermal images, visible image,
        overlay composition, and statistical data in CSV format.
        """
        if not hasattr(self, 'thermal_engine') or self.thermal_engine.thermal_data is None:
            QMessageBox.warning(self, "No Data", 
                              "No thermal image loaded. Please load an image first.")
            return
        
        # Open file dialog to get base filename
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Export Analysis", 
            "", 
            "Base filename (no extension) (*)"
        )
        
        if not file_path:
            return  # User cancelled
        
        # Remove extension if user provided one
        import os
        base_path = os.path.splitext(file_path)[0]
        
        try:
            # Progress tracking - now 6 steps instead of 4
            total_steps = 6
            current_step = 0
            
            # Create progress message box
            progress_msg = QMessageBox(self)
            progress_msg.setWindowTitle("Exporting Analysis")
            progress_msg.setText("Preparing export...")
            progress_msg.setStandardButtons(QMessageBox.NoButton)
            progress_msg.show()
            QApplication.processEvents()
            
            exported_files = []
            
            # 1. Export thermal image (clean, without ROIs)
            current_step += 1
            progress_msg.setText(f"Exporting thermal image... ({current_step}/{total_steps})")
            QApplication.processEvents()
            
            thermal_path = f"{base_path}_thermal.png"
            if self._export_thermal_image(thermal_path):
                exported_files.append(thermal_path)
                print(f"✅ Exported thermal image: {thermal_path}")
            
            # 2. Export thermal image with ROIs
            current_step += 1
            progress_msg.setText(f"Exporting thermal image with ROIs... ({current_step}/{total_steps})")
            QApplication.processEvents()
            
            thermal_roi_path = f"{base_path}_thermal_with_rois.png"
            if self._export_thermal_with_rois(thermal_roi_path):
                exported_files.append(thermal_roi_path)
                print(f"✅ Exported thermal image with ROIs: {thermal_roi_path}")
            
            # 3. Export visible image (if available)
            current_step += 1
            progress_msg.setText(f"Exporting visible image... ({current_step}/{total_steps})")
            QApplication.processEvents()
            
            visible_path = f"{base_path}_visible.png"
            if self._export_visible_image(visible_path):
                exported_files.append(visible_path)
                print(f"✅ Exported visible image: {visible_path}")
            
            # 4. Export overlay image (always try to create overlay if visible image exists)
            current_step += 1
            progress_msg.setText(f"Exporting overlay composition... ({current_step}/{total_steps})")
            QApplication.processEvents()
            
            overlay_path = f"{base_path}_overlay.png"
            if self._export_overlay_image(overlay_path):
                exported_files.append(overlay_path)
                print(f"✅ Exported overlay image: {overlay_path}")
            
            # 5. Export scene composition (current view as-is)
            current_step += 1
            progress_msg.setText(f"Exporting current view... ({current_step}/{total_steps})")
            QApplication.processEvents()
            
            scene_path = f"{base_path}_current_view.png"
            if self._export_current_scene(scene_path):
                exported_files.append(scene_path)
                print(f"✅ Exported current scene: {scene_path}")
            
            # 6. Export data CSV
            current_step += 1
            progress_msg.setText(f"Exporting analysis data... ({current_step}/{total_steps})")
            QApplication.processEvents()
            
            csv_path = f"{base_path}_data.csv"
            if self._export_analysis_csv(csv_path):
                exported_files.append(csv_path)
                print(f"✅ Exported analysis data: {csv_path}")
            
            # Close progress dialog
            progress_msg.close()
            
            # Show success message
            if exported_files:
                file_list = "\n".join([f"• {os.path.basename(f)}" for f in exported_files])
                QMessageBox.information(
                    self, 
                    "Export Completed", 
                    f"Analysis exported successfully!\n\nFiles created:\n{file_list}"
                )
            else:
                QMessageBox.warning(
                    self, 
                    "Export Failed", 
                    "No files were exported. Please check the data and try again."
                )
                
        except Exception as e:
            if 'progress_msg' in locals():
                progress_msg.close()
            QMessageBox.critical(
                self, 
                "Export Error", 
                f"An error occurred during export:\n{str(e)}"
            )
            print(f"Export error: {e}")
            import traceback
            traceback.print_exc()

    def _export_thermal_image(self, file_path: str) -> bool:
        """
        Export the current thermal image with applied palette and settings.
        
        Args:
            file_path (str): Path where to save the thermal image.
            
        Returns:
            bool: True if export was successful, False otherwise.
        """
        try:
            if not hasattr(self, 'thermal_engine'):
                return False
                
            return self.thermal_engine.export_thermal_image(
                file_path, self.selected_palette, self.palette_inverted
            )
        except Exception as e:
            print(f"Error exporting thermal image: {e}")
            return False

    def _export_visible_image(self, file_path: str) -> bool:
        """
        Export the visible light image if available.
        
        Args:
            file_path (str): Path where to save the visible image.
            
        Returns:
            bool: True if export was successful, False otherwise.
        """
        try:
            if not hasattr(self, 'thermal_engine'):
                return False
                
            return self.thermal_engine.export_visible_image(file_path)
        except Exception as e:
            print(f"Error exporting visible image: {e}")
            return False

    def _export_overlay_image(self, file_path: str) -> bool:
        """
        Export overlay composition, forcing overlay mode if both visible and thermal images are available.
        
        Args:
            file_path (str): Path where to save the overlay image.
            
        Returns:
            bool: True if export was successful, False otherwise.
        """
        try:
            if not hasattr(self, 'image_view'):
                return False
                
            # Check if we have BOTH visible and thermal images to create overlay
            has_visible = (hasattr(self, 'thermal_engine') and 
                          self.thermal_engine.base_pixmap_visible is not None and 
                          not self.thermal_engine.base_pixmap_visible.isNull())
            
            has_thermal = (hasattr(self, 'thermal_engine') and 
                          self.thermal_engine.base_pixmap is not None and 
                          not self.thermal_engine.base_pixmap.isNull())
            
            # Force overlay only if BOTH images are available
            force_overlay = has_visible and has_thermal
            
            if force_overlay:
                print("🎭 Forcing overlay mode for export (both visible and thermal images available)")
                
                # Ensure the visible image is loaded in the view before export
                # This is crucial when overlay mode has been disabled - the visible image
                # might not be loaded in the graphics view even if it exists in thermal_engine
                if (self.image_view._visible_item.pixmap().isNull() and 
                    self.thermal_engine.base_pixmap_visible is not None):
                    print("📷 Loading visible image into view for overlay export")
                    self.image_view.set_visible_pixmap(self.thermal_engine.base_pixmap_visible)
                
                # Apply current overlay settings before export
                # This ensures correct scale, offset, and alpha are applied
                print(f"🔧 Applying overlay settings for export:")
                print(f"  - Scale: {self.overlay_scale}")
                print(f"  - Offset: ({self.overlay_offset_x}, {self.overlay_offset_y})")
                print(f"  - Alpha: {self.overlay_alpha}")
                print(f"  - Blend mode: {self.overlay_blend_mode}")
                
                offset = QPointF(self.overlay_offset_x, self.overlay_offset_y)
                blend_mode = self.get_qt_composition_mode()
                
                # Temporarily apply overlay settings to the view
                self.image_view.update_overlay(
                    visible=True,
                    alpha=self.overlay_alpha,
                    scale=self.overlay_scale,
                    offset=offset,
                    blend_mode=blend_mode
                )
            
            else:
                print("⚠️ Cannot create true overlay - missing images:")
                print(f"  - Visible image: {'✓' if has_visible else '✗'}")
                print(f"  - Thermal image: {'✓' if has_thermal else '✗'}")
            
            return self.image_view.export_overlay_image(file_path, force_overlay=force_overlay)
        except Exception as e:
            print(f"Error exporting overlay image: {e}")
            return False

    def _export_thermal_with_rois(self, file_path: str) -> bool:
        """
        Export thermal image with ROIs drawn on top.
        
        Args:
            file_path (str): Path where to save the thermal image with ROIs.
            
        Returns:
            bool: True if export was successful, False otherwise.
        """
        try:
            if not hasattr(self, 'thermal_engine'):
                return False
            
            # Debug: check ROI items
            print(f"🔍 Export thermal with ROIs:")
            print(f"  📊 Total ROI items: {len(self.roi_items)}")
            for roi_id, roi_item in self.roi_items.items():
                try:
                    if hasattr(roi_item, 'model'):  # CORRECTED: use 'model' instead of 'roi_model'
                        roi_model = roi_item.model
                        print(f"    • {roi_id}: {roi_model.name} ({roi_model.__class__.__name__})")
                        print(f"      Position: ({roi_model.x:.1f}, {roi_model.y:.1f})")
                        if hasattr(roi_model, 'temp_mean') and roi_model.temp_mean is not None:
                            print(f"      Temp stats: {roi_model.temp_mean:.1f}°C avg")
                    else:
                        print(f"    • {roi_id}: No model found")
                except Exception as e:
                    print(f"    • {roi_id}: Error accessing ROI - {e}")
                
            return self.thermal_engine.export_thermal_with_rois(
                file_path, self.selected_palette, self.palette_inverted, self.roi_items
            )
        except Exception as e:
            print(f"Error exporting thermal image with ROIs: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _export_current_scene(self, file_path: str) -> bool:
        """
        Export the current scene exactly as displayed.
        
        Args:
            file_path (str): Path where to save the current scene.
            
        Returns:
            bool: True if export was successful, False otherwise.
        """
        try:
            if not hasattr(self, 'image_view'):
                return False
                
            return self.image_view.export_current_scene(file_path)
        except Exception as e:
            print(f"Error exporting current scene: {e}")
            return False

    def _export_analysis_csv(self, file_path: str) -> bool:
        """
        Export analysis data to CSV format including global parameters and ROI statistics.
        
        Args:
            file_path (str): Path where to save the CSV file.
            
        Returns:
            bool: True if export was successful, False otherwise.
        """
        try:
            import csv
            import os
            from datetime import datetime
            
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header with global parameters
                writer.writerow(["# Thermal Analysis Export"])
                writer.writerow(["# Generated on", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                writer.writerow([])
                
                # Original image information
                if hasattr(self, 'thermal_engine') and self.thermal_engine.current_image_path:
                    writer.writerow(["Original Image", os.path.basename(self.thermal_engine.current_image_path)])
                else:
                    writer.writerow(["Original Image", "Unknown"])
                
                # Global thermal parameters
                writer.writerow([])
                writer.writerow(["# Global Thermal Parameters"])
                thermal_params = self.get_current_thermal_parameters()
                for param, value in thermal_params.items():
                    writer.writerow([param, value])
                
                # Global temperature statistics
                writer.writerow([])
                writer.writerow(["# Global Temperature Statistics"])
                if hasattr(self, 'thermal_engine'):
                    global_stats = self.thermal_engine.get_global_statistics()
                    for stat, value in global_stats.items():
                        writer.writerow([stat, f"{value:.2f}" if value is not None else "N/A"])
                
                # Palette settings
                writer.writerow([])
                writer.writerow(["# Visualization Settings"])
                writer.writerow(["Color Palette", self.selected_palette])
                writer.writerow(["Palette Inverted", self.palette_inverted])
                writer.writerow(["Overlay Mode", self.overlay_mode])
                if self.overlay_mode:
                    writer.writerow(["Overlay Scale", f"{self.overlay_scale:.3f}"])
                    writer.writerow(["Overlay Offset X", f"{self.overlay_offset_x:.1f}"])
                    writer.writerow(["Overlay Offset Y", f"{self.overlay_offset_y:.1f}"])
                    writer.writerow(["Overlay Alpha", f"{self.overlay_alpha:.2f}"])
                    writer.writerow(["Overlay Blend Mode", self.overlay_blend_mode])
                
                # ROI Analysis Data
                writer.writerow([])
                writer.writerow(["# ROI Analysis Data"])
                
                if hasattr(self, 'roi_controller'):
                    roi_data = self.roi_controller.export_detailed_roi_data()
                    if roi_data:
                        # Write ROI table header
                        writer.writerow([
                            "roi_name", "roi_type", "emissivity", 
                            "temp_min_celsius", "temp_max_celsius", "temp_mean_celsius", 
                            "temp_median_celsius", "temp_std_dev_celsius", "pixel_count"
                        ])
                        
                        # Write ROI data rows
                        for roi in roi_data:
                            writer.writerow([
                                roi.get("name", ""),
                                roi.get("type", ""),
                                f"{roi.get('emissivity', 0.95):.3f}",
                                f"{roi.get('temp_min', 0):.2f}" if roi.get('temp_min') is not None else "N/A",
                                f"{roi.get('temp_max', 0):.2f}" if roi.get('temp_max') is not None else "N/A",
                                f"{roi.get('temp_mean', 0):.2f}" if roi.get('temp_mean') is not None else "N/A",
                                f"{roi.get('temp_median', 0):.2f}" if roi.get('temp_median') is not None else "N/A",
                                f"{roi.get('temp_std', 0):.2f}" if roi.get('temp_std') is not None else "N/A",
                                roi.get('pixel_count', 0)
                            ])
                    else:
                        writer.writerow(["# No ROIs defined"])
                else:
                    writer.writerow(["# ROI controller not available"])
                
            return True
            
        except Exception as e:
            print(f"Error exporting CSV: {e}")
            return False

    def on_roi_modified(self, roi_model):
        """Handle ROI modified event from both UI and controller."""
        print(f"🔄 ROI modified: {roi_model.name} (ID: {roi_model.id})")
        
        # IMPORTANTE: Ricalcola le statistiche di temperatura per questo ROI
        if hasattr(self, 'roi_controller') and hasattr(self, 'thermal_engine'):
            if self.thermal_engine.temperature_data is not None:
                print(f"  ➡️ Recalculating temperature statistics for {roi_model.name}")
                
                # Debug: check current ROI position
                if hasattr(roi_model, 'x') and hasattr(roi_model, 'y'):
                    print(f"    Position: ({roi_model.x:.1f}, {roi_model.y:.1f})")
                    if hasattr(roi_model, 'width') and hasattr(roi_model, 'height'):
                        print(f"    Size: {roi_model.width:.1f} x {roi_model.height:.1f}")
                
                # Find the ROI in controller and update it
                controller_roi = self.roi_controller.get_roi_by_id(roi_model.id)
                if controller_roi is not None:
                    if controller_roi is roi_model:
                        print("    ✅ Same object - updating directly")
                    else:
                        print("    ⚠️ Different object - syncing data")
                        # Sync the data from the UI model to controller model
                        if hasattr(roi_model, 'x'):
                            controller_roi.x = roi_model.x
                        if hasattr(roi_model, 'y'):
                            controller_roi.y = roi_model.y
                        if hasattr(roi_model, 'width'):
                            controller_roi.width = roi_model.width
                        if hasattr(roi_model, 'height'):
                            controller_roi.height = roi_model.height
                        if hasattr(roi_model, 'radius'):
                            controller_roi.radius = roi_model.radius
                        if hasattr(roi_model, 'points'):
                            controller_roi.points = roi_model.points
                    
                    # Now update statistics
                    self.roi_controller._update_roi_statistics(controller_roi)
                    
                    # Show debug info about calculated stats
                    if hasattr(controller_roi, 'temp_mean') and controller_roi.temp_mean is not None:
                        print(f"    📊 Stats: min={controller_roi.temp_min:.2f}°C, "
                              f"max={controller_roi.temp_max:.2f}°C, "
                              f"mean={controller_roi.temp_mean:.2f}°C")
                    else:
                        print("    ❌ No temperature statistics calculated")
                else:
                    print(f"    ❌ ROI {roi_model.id} not found in controller")
            else:
                print(f"  ⏸️ Skipping statistics (no thermal data)")
        else:
            print(f"  ❌ Missing controller or thermal engine")
        
        # Refresh visual label (ora con le nuove statistiche)
        item = self.roi_items.get(roi_model.id)
        if item and hasattr(item, "refresh_label"):
            item.refresh_label()

        # Update table (ora con i valori aggiornati)
        self.update_roi_table()
        
        # Delay auto-save to avoid spam during dragging
        if not hasattr(self, '_roi_save_timer'):
            from PySide6.QtCore import QTimer
            self._roi_save_timer = QTimer()
            self._roi_save_timer.setSingleShot(True)
            self._roi_save_timer.timeout.connect(self.auto_save_settings)
        
        # Restart timer (500ms delay)
        self._roi_save_timer.start(500)

    def reset_params_to_exif(self):
        """
        Reset all calculation parameters to values extracted from EXIF metadata.
        
        This method restores thermal calculation parameters to their original
        EXIF values when available, or to appropriate default values when
        EXIF data is missing. The UI is updated to reflect the source of
        each parameter value.
        """
        if not hasattr(self, 'thermal_engine') or not self.thermal_engine.metadata:
            self._apply_default_parameter_values()
            return
            
        # Get parameters from thermal engine
        parameters = self.thermal_engine.get_thermal_parameters_from_metadata()
        
        reset_count = 0
        default_count = 0
        
        # Default values for parameters not available in EXIF
        default_values = {
            "AtmosphericTemperature": 20.0,
            "AtmosphericTransmission": 0.95,
            "RelativeHumidity": 50.0,
            "ObjectDistance": 1.0,
            "Emissivity": 0.95
        }
        
        for key, line_edit in self.param_inputs.items():
            if key in parameters and parameters[key] is not None:
                # Use value from metadata
                value = parameters[key]
                if key in ["PlanckR1", "PlanckR2", "PlanckB", "PlanckF", "PlanckO"]:
                    line_edit.setText(f"{float(value):.12f}")
                elif key in ["Emissivity", "ReflectedApparentTemperature", "AtmosphericTransmission"]:
                    line_edit.setText(f"{float(value):.6f}")
                else:
                    line_edit.setText(f"{float(value):.4f}")
                
                line_edit.setStyleSheet("")
                line_edit.setToolTip(f"Value from EXIF metadata: {value}")
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

    def _apply_default_parameter_values(self):
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

    def populate_params(self):
        """
        Populate thermal calculation parameters from EXIF metadata.
        
        This method extracts thermal calculation parameters from the loaded
        image metadata and populates the UI input fields. For missing
        parameters, appropriate default values are used and highlighted.
        """
        if not hasattr(self, 'thermal_engine') or not self.thermal_engine.metadata:
            return
            
        # Get parameters from thermal engine
        parameters = self.thermal_engine.get_thermal_parameters_from_metadata()
        
        # Default values for missing parameters
        default_values = {
            "AtmosphericTemperature": 20.0,
            "AtmosphericTransmission": 0.95,
            "RelativeHumidity": 50.0,
            "ObjectDistance": 1.0,
            "Emissivity": 0.95
        }
        
        for key, line_edit in self.param_inputs.items():
            value = parameters.get(key)
            
            # Use default value if not found in metadata
            if value is None and key in default_values:
                value = default_values[key]
                line_edit.setStyleSheet("background-color: #fff3cd;")  # Yellow highlight
                line_edit.setToolTip(f"Default value used: {value}")
            elif value is not None:
                line_edit.setStyleSheet("")
                line_edit.setToolTip("")
            else:
                line_edit.setText("N/A")
                line_edit.setStyleSheet("background-color: #f8d7da;")  # Red highlight
                line_edit.setToolTip("Parameter not available in EXIF metadata")
                continue
                
            # Format numeric values appropriately
            if value is not None:
                if key in ["PlanckR1", "PlanckR2", "PlanckB", "PlanckF", "PlanckO"]:
                    line_edit.setText(f"{float(value):.12f}")  # High precision for Planck constants
                elif key in ["Emissivity", "ReflectedApparentTemperature", "AtmosphericTransmission"]:
                    line_edit.setText(f"{float(value):.6f}")   # Medium precision
                else:
                    line_edit.setText(f"{float(value):.4f}")   # Standard precision

    def update_analysis(self):
        """
        Legacy method - prefer recalculate_and_update_view().
        
        This method is maintained for backward compatibility but new code
        should use the more explicit recalculate_and_update_view() method.
        """
        self.recalculate_and_update_view()


    def create_colored_pixmap(self):
        """
        Create a colored pixmap from temperature data using the selected palette.
        
        This method delegates to the ThermalEngine and updates the UI display.
        """
        if not hasattr(self, 'thermal_engine'):
            return
            
        pixmap = self.thermal_engine.create_colored_pixmap(
            self.selected_palette, self.palette_inverted
        )
        
        if not pixmap.isNull():
            self.base_pixmap = pixmap
            self.display_thermal_image()

    def update_legend(self):
        """
        Update the color bar legend with current palette and temperature range.
        
        This method synchronizes the color bar legend widget with the current
        selected palette, inversion state, and calculated temperature range.
        """
        if not hasattr(self, 'thermal_engine') or self.thermal_engine.temperature_data is None:
            return
            
        self.colorbar.set_palette(self.selected_palette, self.palette_inverted)
        self.colorbar.set_range(self.thermal_engine.temp_min, self.thermal_engine.temp_max)

    def on_thermal_mouse_move(self, point):
        """
        Handle mouse movement over thermal image to display temperature tooltip.
        
        Args:
            point (QPointF): Mouse position in image coordinates.
        """
        if not hasattr(self, 'thermal_engine') or self.thermal_engine.temperature_data is None:
            self.temp_tooltip_label.setVisible(False)
            return
            
        img_h, img_w = self.thermal_engine.temperature_data.shape
        matrix_x = int(point.x())
        matrix_y = int(point.y())
        
        # Check if point is within image bounds
        if 0 <= matrix_x < img_w and 0 <= matrix_y < img_h:
            temperature = self.thermal_engine.get_temperature_at_point(matrix_x, matrix_y)
            if not np.isnan(temperature):
                try:
                    thermal_params = self.get_current_thermal_parameters()
                    emissivity = thermal_params.get("Emissivity", 0.95)
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

    def update_single_roi(self, roi_model):
        """
        Update statistics for a single ROI using the ROI controller.
        
        Args:
            roi_model: The ROI model to update.
        """
        if hasattr(self, 'roi_controller'):
            # Update via controller
            self.roi_controller._update_roi_statistics(roi_model)
            
            # Refresh visual label
            item = self.roi_items.get(roi_model.id)
            if item and hasattr(item, "refresh_label"):
                item.refresh_label()

            self.update_roi_table()
            self.auto_save_settings()
        else:
            print("ROI controller not available")

    def on_thermal_error(self, error_message: str):
        """Handle thermal engine errors."""
        print(f"Thermal engine error: {error_message}")
        QMessageBox.critical(self, "Thermal Engine Error", error_message)

    def on_roi_removed(self, roi_id: str):
        """Handle ROI removed event from ROIController."""
        print(f"ROI removed: {roi_id}")
        
        # Remove from scene
        if roi_id in self.roi_items:
            roi_item = self.roi_items[roi_id]
            self.image_view._scene.removeItem(roi_item)
            del self.roi_items[roi_id]
        
        # Update table
        self.update_roi_table()
        
        # Auto-save
        self.auto_save_settings()

    def on_rois_cleared(self):
        """Handle ROIs cleared event from ROIController."""
        print("All ROIs cleared")
        
        # Remove all items from scene
        for roi_item in self.roi_items.values():
            self.image_view._scene.removeItem(roi_item)
        
        # Clear UI collection
        self.roi_items.clear()
        
        # Update table
        self.update_roi_table()
        
        # Auto-save
        self.auto_save_settings()

    def on_roi_analysis_updated(self):
        """Handle ROI analysis updated event from ROIController."""
        print("ROI analysis updated")
        
        # Refresh all ROI labels
        for roi_model in self.roi_controller.get_all_rois():
            item = self.roi_items.get(roi_model.id)
            if item and hasattr(item, "refresh_label"):
                item.refresh_label()
        
        # Update table
        self.update_roi_table()

    def on_settings_saved(self, file_path: str):
        """Handle settings saved event from SettingsManager."""
        print(f"Settings saved: {file_path}")

    def on_settings_error(self, error_message: str):
        """Handle settings manager errors."""
        print(f"Settings error: {error_message}")
        # Don't show message box for settings errors to avoid interrupting user workflow

    def update_view_only(self):
        """
        Update only the visualisation using already calculated temperature data.
        
        This method should be used when only palette or colour inversion changes,
        as it doesn't recalculate temperatures but only updates the visual
        representation of existing data.
        """
        if not hasattr(self, 'thermal_engine') or self.thermal_engine.temperature_data is None:
            return
            
        print(">>> Updating visualisation only...")
        self.update_thermal_display()
        self.update_legend()
        self.display_images()