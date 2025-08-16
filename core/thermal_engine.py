"""
Thermal Engine Module

This module contains the ThermalEngine class responsible for handling thermal data
processing, temperature calculations, and image management. It separates the core
thermal analysis logic from the UI components.
"""

import io
import json
import subprocess
import numpy as np
from PIL import Image
import exiftool
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QBrush, QColor, QPolygonF, QFont
from PySide6.QtCore import QObject, Signal, Qt, QPointF, QRectF, QRect

from constants import PALETTE_MAP
import matplotlib.cm as cm

# ==============================================================================
# MODIFICA 1: Aggiunta degli import necessari e della funzione di supporto
# ==============================================================================
import sys
import os

def resource_path(relative_path):
    """ Ottiene il percorso assoluto della risorsa, funziona sia in dev che con PyInstaller """
    try:
        # PyInstaller crea una cartella temporanea e ci salva il percorso in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Se non siamo in un pacchetto, usiamo il percorso del file corrente
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)
# ==============================================================================
# Fine Modifica 1
# ==============================================================================


class ThermalEngine(QObject):
    """
    Core engine for thermal data processing and temperature calculations.
    
    This class handles:
    - Loading thermal images and extracting metadata
    - Processing raw thermal data 
    - Converting raw values to calibrated temperatures
    - Applying environmental corrections
    - Creating colored visualizations from temperature data
    """
    
    # Signals for notifying UI components
    data_loaded = Signal()
    temperatures_calculated = Signal()
    error_occurred = Signal(str)
    
    def __init__(self):
        """Initialize the thermal engine with default values."""
        super().__init__()
        
        # Core thermal data
        self.thermal_data = None
        self.temperature_data = None
        self.metadata = None
        self.base_pixmap = None
        self.base_pixmap_visible = None
        
        # Temperature range
        self.temp_min = 0.0
        self.temp_max = 100.0
        
        # Current file path
        self.current_image_path = None
        
        # Default thermal parameters
        self.default_parameters = {
            "Emissivity": 0.95,
            "ObjectDistance": 1.0,
            "ReflectedApparentTemperature": 20.0,
            "AtmosphericTemperature": 20.0,
            "AtmosphericTransmission": 0.95,
            "RelativeHumidity": 50.0,
        }

    def load_thermal_image(self, file_path: str) -> bool:
        """
        Load a FLIR thermal image and extract all necessary data.
        
        Args:
            file_path (str): Path to the thermal image file.
            
        Returns:
            bool: True if loading was successful, False otherwise.
        """
        try:
            self.current_image_path = file_path
            
            # ==============================================================================
            # MODIFICA 2: Usa resource_path per trovare exiftool
            # Essendo su macOS, il nome dell'eseguibile è "exiftool".
            # Il codice è scritto per funzionare anche su Windows ("exiftool.exe").
            # ==============================================================================
            exiftool_executable = resource_path("exiftool_bin" if sys.platform != "win32" else "exiftool.exe")

            # Extract EXIF metadata using exiftool
            with exiftool.ExifTool(executable=exiftool_executable) as et:
                json_string = et.execute(b"-json", file_path.encode())
                self.metadata = json.loads(json_string)[0]
                
            # Extract raw thermal data
            command = [exiftool_executable, "-b", "-RawThermalImage", file_path]
            # ==============================================================================
            # Fine Modifica 2
            # ==============================================================================
            result = subprocess.run(command, capture_output=True, check=True)
            raw_thermal_bytes = result.stdout
            
            if not raw_thermal_bytes:
                raise ValueError("Binary thermal data not extracted.")

            # Process thermal data based on image type
            image_type = self.metadata.get("APP1:RawThermalImageType", "Unknown")
            if image_type == "PNG":
                # PNG format thermal data
                self.thermal_data = np.array(Image.open(io.BytesIO(raw_thermal_bytes)))
                self.thermal_data.byteswap(inplace=True)
            else:
                # Raw binary thermal data
                width = self.metadata.get('APP1:RawThermalImageWidth')
                height = self.metadata.get('APP1:RawThermalImageHeight')
                if not width or not height:
                    raise ValueError("Image dimensions not found.")
                self.thermal_data = np.frombuffer(
                    raw_thermal_bytes, dtype=np.uint16
                ).reshape((height, width))

            # Extract visible light image if available
            self._extract_visible_image(file_path)
            
            self.data_loaded.emit()
            return True
            
        except Exception as e:
            self.error_occurred.emit(f"Unable to process file: {e}")
            return False

    def _extract_visible_image(self, file_path: str):
        """
        Extract visible light image from the thermal file.
        
        Args:
            file_path (str): Path to the thermal image file.
        """
        try:
            # ==============================================================================
            # MODIFICA 3: Usa resource_path anche qui per coerenza
            # ==============================================================================
            exiftool_executable = resource_path("exiftool_bin" if sys.platform != "win32" else "exiftool.exe")
            command_rgb = [exiftool_executable, "-b", "-EmbeddedImage", file_path]
            # ==============================================================================
            # Fine Modifica 3
            # ==============================================================================
            result_rgb = subprocess.run(command_rgb, capture_output=True, check=True)
            rgb_bytes = result_rgb.stdout
            
            if rgb_bytes:
                # Process visible light image
                image_rgb = Image.open(io.BytesIO(rgb_bytes))
                image_rgb = image_rgb.convert("RGB")
                
                # Convert to QPixmap for display
                data = image_rgb.tobytes("raw", "RGB")
                qimage = QImage(data, image_rgb.width, image_rgb.height, 
                              image_rgb.width * 3, QImage.Format_RGB888)
                self.base_pixmap_visible = QPixmap.fromImage(qimage)
            else:
                self.base_pixmap_visible = None
                
        except Exception as e:
            print(f"Error loading visible image: {e}")
            self.base_pixmap_visible = None

    def calculate_temperatures(self, thermal_parameters: dict) -> bool:
        """
        Calculate temperature matrix from raw thermal data using Planck equation.
        
        Args:
            thermal_parameters (dict): Dictionary containing thermal calculation parameters.
            
        Returns:
            bool: True if calculation was successful, False otherwise.
        """
        if self.thermal_data is None:
            return False
            
        try:
            # Extract emissivity
            emissivity = thermal_parameters.get("Emissivity", 0.95)
            
            # Calculate temperatures using Planck equation
            temp_celsius = self._calculate_temperatures_from_raw(
                self.thermal_data, emissivity, thermal_parameters
            )
            
            # Apply environmental corrections
            self.temperature_data = self._apply_environmental_correction(
                temp_celsius, thermal_parameters
            )
            
            # Calculate temperature range
            self._update_temperature_range()
            
            self.temperatures_calculated.emit()
            return True
            
        except Exception as e:
            self.error_occurred.emit(f"Error calculating temperatures: {e}")
            return False

    def _calculate_temperatures_from_raw(self, raw_data: np.ndarray, 
                                       emissivity: float, 
                                       parameters: dict) -> np.ndarray:
        """
        Core Planck equation implementation for temperature calculation.
        
        Args:
            raw_data (np.ndarray): Raw thermal data from sensor.
            emissivity (float): Emissivity value for the calculation.
            parameters (dict): Thermal calculation parameters.
            
        Returns:
            np.ndarray: Calculated temperatures in Celsius.
        """
        try:
            # Extract Planck parameters
            refl_temp_C = parameters.get("ReflectedApparentTemperature", 20.0)
            R1 = parameters.get("PlanckR1")
            R2 = parameters.get("PlanckR2") 
            B = parameters.get("PlanckB")
            F = parameters.get("PlanckF")
            O = parameters.get("PlanckO")
            
            # Validate Planck parameters
            if any(param is None for param in [R1, R2, B, F, O]):
                # Extract from metadata if not provided
                R1 = float(self.metadata.get("APP1:PlanckR1", R1 or 0))
                R2 = float(self.metadata.get("APP1:PlanckR2", R2 or 0))
                B = float(self.metadata.get("APP1:PlanckB", B or 0))
                F = float(self.metadata.get("APP1:PlanckF", F or 0))
                O = float(self.metadata.get("APP1:PlanckO", O or 0))
            
            refl_temp_K = refl_temp_C + 273.15
            
            # Calculate reflected temperature component
            raw_refl = R1 / (R2 * (np.exp(B / refl_temp_K) - F)) - O
            
            # Apply emissivity correction
            raw_obj = (raw_data - (1 - emissivity) * raw_refl) / max(emissivity, 1e-6)
            
            # Apply Planck equation
            log_arg = R1 / (R2 * (raw_obj + O)) + F
            temp_K = np.full(log_arg.shape, np.nan, dtype=np.float64)
            valid_indices = log_arg > 0
            temp_K[valid_indices] = B / np.log(log_arg[valid_indices])
            
            # Convert to Celsius
            return temp_K - 273.15
            
        except Exception as e:
            print(f"Error in Planck calculation: {e}")
            return np.full(raw_data.shape, np.nan, dtype=np.float64)

    def _apply_environmental_correction(self, temp_data: np.ndarray, 
                                      parameters: dict) -> np.ndarray:
        """
        Apply environmental corrections to improve temperature accuracy.
        
        Args:
            temp_data (np.ndarray): Raw temperature data in Celsius.
            parameters (dict): Environmental parameters.
            
        Returns:
            np.ndarray: Environmentally corrected temperature data.
        """
        try:
            if temp_data is None or np.all(np.isnan(temp_data)):
                return temp_data
                
            # Extract environmental parameters
            atmospheric_temp = parameters.get("AtmosphericTemperature", 20.0)
            atmospheric_transmission = parameters.get("AtmosphericTransmission", 0.95)
            relative_humidity = parameters.get("RelativeHumidity", 50.0)
            
            # Calculate corrections
            temp_correction = (atmospheric_temp - 20.0) * 0.0005
            transmission_correction = (1.0 - atmospheric_transmission) * 0.002
            humidity_correction = (relative_humidity - 50.0) * 0.00002
            
            total_correction = temp_correction + transmission_correction + humidity_correction
            return temp_data + total_correction
            
        except Exception as e:
            print(f"Warning: Environmental correction not applied - {e}")
            return temp_data

    def _update_temperature_range(self):
        """Update the temperature range from current temperature data."""
        if self.temperature_data is not None:
            finite_data = self.temperature_data[np.isfinite(self.temperature_data)]
            if len(finite_data) > 0:
                self.temp_min = float(np.min(finite_data))
                self.temp_max = float(np.max(finite_data))
            else:
                self.temp_min, self.temp_max = 0, 100
        else:
            self.temp_min, self.temp_max = 0, 100

    def create_colored_pixmap(self, palette_name: str = "Iron", 
                            inverted: bool = False) -> QPixmap:
        """
        Create a colored pixmap from temperature data using the specified palette.
        
        Args:
            palette_name (str): Name of the color palette to use.
            inverted (bool): Whether to invert the palette.
            
        Returns:
            QPixmap: Colored thermal image as QPixmap.
        """
        if self.temperature_data is None:
            return QPixmap()
            
        # Normalize temperature data to 0-1 range
        temp_range = self.temp_max - self.temp_min
        if temp_range == 0:
            temp_range = 1
        
        norm_data = (self.temperature_data - self.temp_min) / temp_range
        norm_data = np.nan_to_num(norm_data)
        
        # Apply color mapping
        cmap = PALETTE_MAP.get(palette_name, cm.inferno)
        if inverted:
            norm_data = 1.0 - norm_data
            
        colored_data = cmap(norm_data)
        
        # Convert to 8-bit RGB
        image_8bit = (colored_data[:, :, :3] * 255).astype(np.uint8)
        
        # Create QPixmap
        height, width, _ = image_8bit.shape
        q_image = QImage(image_8bit.data, width, height, width * 3, QImage.Format_RGB888)
        self.base_pixmap = QPixmap.fromImage(q_image)
        
        return self.base_pixmap

    def get_temperature_at_point(self, x: int, y: int) -> float:
        """
        Get temperature value at a specific pixel coordinate.
        
        Args:
            x (int): X coordinate.
            y (int): Y coordinate.
            
        Returns:
            float: Temperature value in Celsius, or NaN if invalid.
        """
        if (self.temperature_data is None or 
            x < 0 or y < 0 or 
            y >= self.temperature_data.shape[0] or 
            x >= self.temperature_data.shape[1]):
            return float('nan')
        
        return self.temperature_data[y, x]

    def get_thermal_parameters_from_metadata(self) -> dict:
        """
        Extract thermal parameters from loaded metadata.
        
        Returns:
            dict: Dictionary of thermal parameters with default fallbacks.
        """
        if not self.metadata:
            return self.default_parameters.copy()
            
        parameters = {}
        
        # Extract parameters with fallbacks
        for key, default_value in self.default_parameters.items():
            metadata_value = self.metadata.get(f"APP1:{key}", 
                                             self.metadata.get(key))
            if metadata_value is not None and metadata_value != "N/A":
                try:
                    parameters[key] = float(metadata_value)
                except (ValueError, TypeError):
                    parameters[key] = default_value
            else:
                parameters[key] = default_value
        
        # Extract Planck constants
        planck_params = ["PlanckR1", "PlanckR2", "PlanckB", "PlanckF", "PlanckO"]
        for param in planck_params:
            metadata_value = self.metadata.get(f"APP1:{param}")
            if metadata_value is not None:
                try:
                    parameters[param] = float(metadata_value)
                except (ValueError, TypeError):
                    parameters[param] = None
            else:
                parameters[param] = None
                
        return parameters

    def get_overlay_parameters_from_metadata(self) -> dict:
        """
        Extract overlay alignment parameters from metadata.
        
        Returns:
            dict: Dictionary containing overlay parameters.
        """
        if not self.metadata:
            return {"scale": 1.0, "offset_x": 0.0, "offset_y": 0.0}
            
        try:
            scale = 1.0 / float(self.metadata.get("APP1:Real2IR", 1.0))
        except Exception:
            scale = 1.0
            
        try:
            offset_x = float(self.metadata.get("APP1:OffsetX", 0.0))
        except Exception:
            offset_x = 0.0
            
        try:
            offset_y = float(self.metadata.get("APP1:OffsetY", 0.0))
        except Exception:
            offset_y = 0.0
            
        return {
            "scale": scale,
            "offset_x": offset_x,
            "offset_y": offset_y
        }

    def compute_roi_temperatures(self, roi_mask: np.ndarray, 
                               roi_emissivity: float = None) -> np.ndarray:
        """
        Compute temperature values for pixels within an ROI mask.
        
        Args:
            roi_mask (np.ndarray): Boolean mask indicating ROI pixels.
            roi_emissivity (float, optional): ROI-specific emissivity. 
                                            If None, uses existing temperature data.
            
        Returns:
            np.ndarray: Temperature values for ROI pixels.
        """
        if self.thermal_data is None:
            return np.array([])
            
        if roi_emissivity is not None:
            # Recalculate temperatures with ROI-specific emissivity
            thermal_roi = self.thermal_data[roi_mask].astype(np.float64)
            
            # Get current thermal parameters but override emissivity
            params = self.get_thermal_parameters_from_metadata()
            params["Emissivity"] = roi_emissivity
            
            # Calculate temperatures for ROI pixels only
            temp_celsius = self._calculate_temperatures_from_raw(
                thermal_roi, roi_emissivity, params
            )
            return self._apply_environmental_correction(temp_celsius, params)
        else:
            # Use existing temperature data
            if self.temperature_data is None:
                return np.array([])
            return self.temperature_data[roi_mask]

    def reset_data(self):
        """Reset all thermal data and clear the engine state."""
        self.thermal_data = None
        self.temperature_data = None
        self.metadata = None
        self.base_pixmap = None
        self.base_pixmap_visible = None
        self.temp_min = 0.0
        self.temp_max = 100.0
        self.current_image_path = None

    def _create_legend_pixmap(self, palette_name: str, inverted: bool, 
                            target_height: int, scale_factor: float = 1.0,
                            current_thermal_params: dict = None) -> QPixmap:
        """
        Create a legend pixmap with current temperature range and palette.
        
        Args:
            palette_name (str): Name of the color palette.
            inverted (bool): Whether to invert the palette.
            target_height (int): Target height for the legend to match image height.
            scale_factor (float): Scale factor for legend size.
            current_thermal_params (dict, optional): Current thermal parameters from UI.
            
        Returns:
            QPixmap: Rendered legend as pixmap with title.
        """
        try:
            print(f"🎨 Creating legend pixmap: palette={palette_name}, inverted={inverted}, scale={scale_factor}")
            print(f"  - Temperature range: {self.temp_min:.1f}°C to {self.temp_max:.1f}°C")
            print(f"  - Target height: {target_height}px")
            
            # Get emissivity value - use current params if provided, otherwise fallback to metadata
            if current_thermal_params and "Emissivity" in current_thermal_params:
                emissivity = current_thermal_params["Emissivity"]
                print(f"  - Using current UI emissivity: {emissivity:.3f}")
            else:
                thermal_params = self.get_thermal_parameters_from_metadata()
                emissivity = thermal_params.get("Emissivity", 0.95)
                print(f"  - Using metadata emissivity: {emissivity:.3f}")
            
            # Import ColorBarLegend locally to avoid circular imports
            from ui.widgets.color_bar_legend import ColorBarLegend
            from PySide6.QtCore import QPoint
            from PySide6.QtGui import QColor
            
            # Create a temporary legend widget
            legend = ColorBarLegend()
            legend.set_palette(palette_name, inverted)
            legend.set_range(self.temp_min, self.temp_max)
            legend.set_unit("°C")
            legend.set_precision(1)
            legend.set_show_units_on_ticks(True)
            # Force black text for exported images to ensure readability
            legend.set_forced_text_color(QColor(0, 0, 0))
            
            # Calculate title dimensions
            title_text = f"Temperature °C | ε {emissivity:.3f}"
            title_font_size = int(14 * scale_factor)  # Increased from 10
            title_height = int(35 * scale_factor)     # Increased from 25
            title_margin = int(8 * scale_factor)      # Increased from 5
            
            # Calculate required width for title text
            title_font = QFont()
            title_font.setPointSizeF(title_font_size)
            title_font.setBold(True)
            title_font.setFamily("Arial")
            
            from PySide6.QtGui import QFontMetrics
            title_metrics = QFontMetrics(title_font)
            title_text_width = title_metrics.horizontalAdvance(title_text)
            title_required_width = title_text_width + int(20 * scale_factor)  # Add padding
            
            # Calculate legend size - use target height minus space for title
            legend_width = int(90 * scale_factor)
            available_legend_height = target_height - title_height - title_margin
            legend_height = max(available_legend_height, int(100 * scale_factor))  # Minimum height
            
            # Use the larger width between title and legend
            final_width = max(title_required_width, legend_width)
            
            print(f"  - Legend size: {legend_width}x{legend_height}")
            print(f"  - Title: '{title_text}' (height: {title_height}px)")
            print(f"  - Title required width: {title_required_width}px")
            print(f"  - Final width: {final_width}px")
            
            # Adjust font size for scaled legend
            font = legend.font()
            font.setPointSizeF(9.0 * scale_factor)
            legend.setFont(font)
            
            # Set legend size and make it visible for proper rendering
            legend.setFixedSize(legend_width, legend_height)
            legend.show()  # Important: make widget visible for rendering
            
            # Process events to ensure the widget is properly rendered
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            
            # Create legend pixmap
            legend_pixmap = QPixmap(legend_width, legend_height)
            legend_pixmap.fill(Qt.transparent)  # Transparent background
            
            # Render the legend widget directly to the pixmap
            legend.render(legend_pixmap)
            
            # Hide the temporary widget
            legend.hide()
            legend.deleteLater()
            
            # Create final pixmap with title and legend
            final_height = title_height + title_margin + legend_height
            final_pixmap = QPixmap(final_width, final_height)
            final_pixmap.fill(Qt.transparent)
            
            # Paint title and legend
            painter = QPainter(final_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.TextAntialiasing)
            
            # Keep transparent background for PNG exports - no background or border for title
            
            # Draw title text with good contrast on transparent background
            painter.setFont(title_font)
            # Use dark text with white outline for better visibility on any background
            painter.setPen(QColor(255, 255, 255))  # White outline
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx != 0 or dy != 0:
                        title_rect_outline = QRect(dx, dy, final_width, title_height)
                        painter.drawText(title_rect_outline, Qt.AlignCenter, title_text)
            
            painter.setPen(QColor(0, 0, 0))  # Black text on top
            
            title_rect = QRect(0, 0, final_width, title_height)
            painter.drawText(title_rect, Qt.AlignCenter, title_text)
            
            # Draw legend below title (centered if final_width > legend_width)
            legend_y = title_height + title_margin
            legend_x = (final_width - legend_width) // 2  # Center the legend horizontally
            painter.drawPixmap(legend_x, legend_y, legend_pixmap)
            
            painter.end()
            
            print(f"✅ Legend pixmap with title created: {final_pixmap.width()}x{final_pixmap.height()}")
            print(f"  - Title position: (0, 0) - size: {final_width}x{title_height}")
            print(f"  - Legend position: ({legend_x}, {legend_y}) - size: {legend_width}x{legend_height}")
            
            return final_pixmap
            
        except Exception as e:
            print(f"❌ Error creating legend pixmap: {e}")
            import traceback
            traceback.print_exc()
            return QPixmap()

    def _combine_image_with_legend(self, image_pixmap: QPixmap, palette_name: str, 
                                  inverted: bool, scale_factor: float = 1.0,
                                  current_thermal_params: dict = None) -> QPixmap:
        """
        Combine thermal image with legend on the right side.
        
        Args:
            image_pixmap (QPixmap): The thermal image pixmap.
            palette_name (str): Color palette name.
            inverted (bool): Whether palette is inverted.
            scale_factor (float): Scale factor for sizing.
            current_thermal_params (dict, optional): Current thermal parameters from UI.
            
        Returns:
            QPixmap: Combined image with legend on the right.
        """
        try:
            print(f"🔗 Combining image with legend...")
            print(f"  - Image size: {image_pixmap.width()}x{image_pixmap.height()}")
            
            if image_pixmap.isNull():
                print("❌ Image pixmap is null")
                return QPixmap()
            
            # Create legend pixmap with the exact height of the thermal image
            legend_pixmap = self._create_legend_pixmap(palette_name, inverted, 
                                                     image_pixmap.height(), scale_factor,
                                                     current_thermal_params)
            
            if legend_pixmap.isNull():
                print("⚠️ Could not create legend, returning original image")
                return image_pixmap
            
            print(f"  - Legend size: {legend_pixmap.width()}x{legend_pixmap.height()}")
            
            # Calculate spacing and total dimensions
            spacing = int(20 * scale_factor)  # Space between image and legend
            total_width = image_pixmap.width() + spacing + legend_pixmap.width()
            total_height = image_pixmap.height()  # Use image height since legend matches it
            
            print(f"  - Final size: {total_width}x{total_height} (spacing: {spacing}px)")
            
            # Create combined pixmap with transparent background
            combined_pixmap = QPixmap(total_width, total_height)
            combined_pixmap.fill(Qt.transparent)  # Transparent background
            
            # Paint image and legend
            painter = QPainter(combined_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Draw thermal image on the left
            painter.drawPixmap(0, 0, image_pixmap)
            
            # Draw legend on the right (no vertical centering needed since heights match)
            legend_x = image_pixmap.width() + spacing
            legend_y = 0  # Top-aligned since heights are the same
            painter.drawPixmap(legend_x, legend_y, legend_pixmap)
            
            painter.end()
            
            print(f"✅ Combined image with legend: {total_width}x{total_height}")
            print(f"  - Image position: (0, 0)")
            print(f"  - Legend position: ({legend_x}, {legend_y})")
            
            return combined_pixmap
            
        except Exception as e:
            print(f"❌ Error combining image with legend: {e}")
            import traceback
            traceback.print_exc()
            return image_pixmap

    def export_thermal_image(self, file_path: str, palette_name: str = "Iron", 
                       inverted: bool = False, scale_factor: float = 2.0,
                       include_legend: bool = True, 
                       current_thermal_params: dict = None) -> bool:
        """
        Export the thermal image with specified palette settings.
        
        Args:
            file_path (str): Path where to save the image.
            palette_name (str): Color palette to use.
            inverted (bool): Whether to invert the palette.
            scale_factor (float): Scale factor for export resolution (default 2.0 for high quality).
            include_legend (bool): Whether to include the color legend (default True).
            current_thermal_params (dict, optional): Current thermal parameters from UI.
            
        Returns:
            bool: True if export was successful, False otherwise.
        """
        try:
            # Create colored pixmap with specified settings
            pixmap = self.create_colored_pixmap(palette_name, inverted)
            
            if pixmap.isNull():
                print("Error: Cannot create thermal pixmap for export")
                return False
            
            # Apply scale factor for higher resolution export
            if scale_factor != 1.0:
                original_size = pixmap.size()
                scaled_width = int(original_size.width() * scale_factor)
                scaled_height = int(original_size.height() * scale_factor)
                
                print(f"🔍 Scaling thermal image from {original_size.width()}x{original_size.height()} to {scaled_width}x{scaled_height} (scale: {scale_factor}x)")
                
                # Scale the pixmap using smooth transformation
                pixmap = pixmap.scaled(scaled_width, scaled_height, 
                                     Qt.KeepAspectRatio, 
                                     Qt.SmoothTransformation)
            
            # Add legend if requested
            if include_legend:
                pixmap = self._combine_image_with_legend(pixmap, palette_name, inverted, scale_factor, current_thermal_params)
            
            # Save the pixmap
            success = pixmap.save(file_path, "PNG")
            
            if success:
                print(f"✅ Thermal image exported successfully: {file_path}")
                print(f"  - Final resolution: {pixmap.width()}x{pixmap.height()}")
                if include_legend:
                    print(f"  - Legend included: Yes")
            else:
                print(f"❌ Failed to save thermal image: {file_path}")
                
            return success
            
        except Exception as e:
            print(f"❌ Error exporting thermal image: {e}")
            import traceback
            traceback.print_exc()
            return False

    def export_visible_image(self, file_path: str) -> bool:
        """
        Export the visible light image if available.
        
        Args:
            file_path (str): Path where to save the image.
            
        Returns:
            bool: True if export was successful, False otherwise.
        """
        try:
            if self.base_pixmap_visible is None or self.base_pixmap_visible.isNull():
                print("No visible light image available for export")
                return False
            
            # Save the visible image pixmap
            success = self.base_pixmap_visible.save(file_path, "PNG")
            
            if success:
                print(f"Visible image exported successfully: {file_path}")
            else:
                print(f"Failed to save visible image: {file_path}")
                
            return success
            
        except Exception as e:
            print(f"Error exporting visible image: {e}")
            return False

    def get_global_statistics(self) -> dict:
        """
        Get global temperature statistics for the entire thermal image.
        
        Returns:
            dict: Dictionary containing global temperature statistics.
        """
        stats = {
            "global_temp_min_celsius": None,
            "global_temp_max_celsius": None,
            "global_temp_mean_celsius": None,
            "global_temp_median_celsius": None,
            "global_temp_std_dev_celsius": None,
            "total_pixel_count": 0
        }
        
        try:
            if self.temperature_data is not None:
                # Get all finite temperature values
                finite_temps = self.temperature_data[np.isfinite(self.temperature_data)]
                
                if len(finite_temps) > 0:
                    stats["global_temp_min_celsius"] = float(np.min(finite_temps))
                    stats["global_temp_max_celsius"] = float(np.max(finite_temps))
                    stats["global_temp_mean_celsius"] = float(np.mean(finite_temps))
                    stats["global_temp_median_celsius"] = float(np.median(finite_temps))
                    stats["global_temp_std_dev_celsius"] = float(np.std(finite_temps))
                    stats["total_pixel_count"] = len(finite_temps)
                    
        except Exception as e:
            print(f"Error calculating global statistics: {e}")
            
        return stats

    def export_thermal_with_rois(self, file_path: str, palette_name: str = "Iron", 
                               inverted: bool = False, roi_items: dict = None, 
                               scale_factor: float = 2.0, include_legend: bool = True,
                               current_thermal_params: dict = None) -> bool:
        """
        Export thermal image with ROIs drawn on top.
        
        Args:
            file_path (str): Path where to save the thermal image with ROIs.
            palette_name (str): Color palette to use.
            inverted (bool): Whether to invert the palette.
            roi_items (dict): Dictionary of ROI items to draw.
            scale_factor (float): Scale factor for export resolution.
            include_legend (bool): Whether to include the color legend.
            current_thermal_params (dict, optional): Current thermal parameters from UI.
            
        Returns:
            bool: True if export was successful, False otherwise.
        """
        try:
            # Create base thermal pixmap
            thermal_pixmap = self.create_colored_pixmap(palette_name, inverted)
            
            if thermal_pixmap.isNull():
                print("Error: Cannot create thermal pixmap for ROI export")
                return False
            
            print(f"🎨 Created thermal pixmap: {thermal_pixmap.width()}x{thermal_pixmap.height()}")
            
            # Apply scale factor for higher resolution export
            if scale_factor != 1.0:
                original_size = thermal_pixmap.size()
                scaled_width = int(original_size.width() * scale_factor)
                scaled_height = int(original_size.height() * scale_factor)
                
                print(f"🔍 Scaling thermal image from {original_size.width()}x{original_size.height()} to {scaled_width}x{scaled_height} (scale: {scale_factor}x)")
                
                # Scale the pixmap using smooth transformation
                thermal_pixmap = thermal_pixmap.scaled(scaled_width, scaled_height, 
                                                     Qt.KeepAspectRatio, 
                                                     Qt.SmoothTransformation)
                
                print(f"🎨 Scaled thermal pixmap: {thermal_pixmap.width()}x{thermal_pixmap.height()}")
            
            # Check if we have ROIs to draw
            if not roi_items:
                print("⚠️ No ROI items provided, saving plain thermal image")
                # Still add legend if requested
                if include_legend:
                    thermal_pixmap = self._combine_image_with_legend(thermal_pixmap, palette_name, inverted, scale_factor, current_thermal_params)
                return thermal_pixmap.save(file_path, "PNG")
            
            print(f"📊 Drawing {len(roi_items)} ROIs on thermal image")
            
            # Create a painter to draw ROIs on top
            painter = QPainter(thermal_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            
            roi_count = 0
            # Draw each ROI
            for roi_id, roi_item in roi_items.items():
                try:
                    # Access ROI model
                    if hasattr(roi_item, 'model'):
                        roi_model = roi_item.model
                        print(f"  🔸 Drawing ROI: {roi_model.name} ({roi_model.__class__.__name__})")
                    else:
                        print(f"⚠️ Cannot find model in ROI item {roi_id}")
                        continue
                    
                    # Set pen for ROI outline (scale thickness with image)
                    pen_width = max(1, int(3 * scale_factor))
                    pen = QPen(roi_model.color, pen_width)
                    painter.setPen(pen)
                    
                    # Set brush for ROI fill (semi-transparent)
                    brush_color = QColor(roi_model.color)
                    brush_color.setAlpha(80)
                    painter.setBrush(QBrush(brush_color))
                    
                    # Scale ROI coordinates
                    def scale_coord(coord):
                        return coord * scale_factor
                    
                    # Draw based on ROI type
                    if hasattr(roi_model, 'width') and hasattr(roi_model, 'height'):
                        # Rectangular ROI
                        rect = QRectF(scale_coord(roi_model.x), scale_coord(roi_model.y), 
                                    scale_coord(roi_model.width), scale_coord(roi_model.height))
                        painter.drawRect(rect)
                        print(f"    📐 Drew rectangle: x={rect.x():.1f}, y={rect.y():.1f}, w={rect.width():.1f}, h={rect.height():.1f}")
                        
                        # Position label above rectangle (scaled)
                        metrics = painter.fontMetrics()
                        label_height = metrics.height() * 2  # Two lines
                        label_x = scale_coord(roi_model.x) + 2
                        label_y = scale_coord(roi_model.y) - label_height - 2
                        self._draw_roi_label_at_position(painter, roi_model, label_x, label_y)
                        
                    elif hasattr(roi_model, 'radius'):
                        # Spot (circular) ROI
                        center_x, center_y = scale_coord(roi_model.x), scale_coord(roi_model.y)
                        radius = scale_coord(roi_model.radius)
                        # Draw ellipse using bounding rectangle
                        rect = QRectF(center_x - radius, center_y - radius, 
                                    radius * 2, radius * 2)
                        painter.drawEllipse(rect)
                        print(f"    🎯 Drew circle: center=({center_x:.1f}, {center_y:.1f}), radius={radius:.1f}")
                        
                        # Position label above circle (scaled)
                        metrics = painter.fontMetrics()
                        label_height = metrics.height() * 2  # Two lines
                        label_x = center_x - radius + 2
                        label_y = center_y - radius - label_height - 2
                        self._draw_roi_label_at_position(painter, roi_model, label_x, label_y)
                        
                    elif hasattr(roi_model, 'points'):
                        # Polygon ROI
                        if len(roi_model.points) >= 3:
                            polygon = QPolygonF()
                            for x, y in roi_model.points:
                                polygon.append(QPointF(scale_coord(x), scale_coord(y)))
                            painter.drawPolygon(polygon)
                            print(f"    🔷 Drew polygon with {len(roi_model.points)} points")
                            
                            # Position label above polygon bounding box (scaled)
                            if roi_model.points:
                                bbox = polygon.boundingRect()
                                metrics = painter.fontMetrics()
                                label_height = metrics.height() * 2  # Two lines
                                label_x = bbox.left() + 2
                                label_y = bbox.top() - label_height - 2
                                self._draw_roi_label_at_position(painter, roi_model, label_x, label_y)
                        else:
                            print(f"    ⚠️ Polygon has only {len(roi_model.points)} points, skipping")
                    
                    roi_count += 1
                    
                except Exception as e:
                    roi_name = "Unknown"
                    try:
                        if hasattr(roi_item, 'model'):
                            roi_name = roi_item.model.name
                    except:
                        pass
                    print(f"❌ Error drawing ROI {roi_name}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            painter.end()
            
            print(f"✅ Successfully drew {roi_count} ROIs")
            
            # Add legend if requested
            if include_legend:
                thermal_pixmap = self._combine_image_with_legend(thermal_pixmap, palette_name, inverted, scale_factor, current_thermal_params)
            
            # Save the result
            success = thermal_pixmap.save(file_path, "PNG")
            
            if success:
                print(f"💾 Thermal image with ROIs exported successfully: {file_path}")
                print(f"  - Final resolution: {thermal_pixmap.width()}x{thermal_pixmap.height()}")
                if include_legend:
                    print(f"  - Legend included: Yes")
            else:
                print(f"❌ Failed to save thermal image with ROIs: {file_path}")
                
            return success
            
        except Exception as e:
            print(f"❌ Error exporting thermal image with ROIs: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _draw_roi_label_at_position(self, painter: QPainter, roi_model, label_x: float, label_y: float):
        """
        Draw ROI label with statistics at a specific position.
        Uses the same format and styling as the normal scene labels.
        
        Args:
            painter (QPainter): Painter to use for drawing.
            roi_model: ROI model with statistics.
            label_x (float): X position for the label.
            label_y (float): Y position for the label.
        """
        try:
            # Use the same format as refresh_label() in roi_items.py
            def fmt(v): 
                return f"{v:.2f}" if (v is not None) else "N/A"
            
            # First line: name | emissivity
            parts1 = []
            parts1.append(roi_model.name)
            parts1.append(f"ε {getattr(roi_model, 'emissivity', 0.95):.3f}")
            line1 = " | ".join(parts1)

            # Second line: min | max | mean statistics
            parts2 = []
            parts2.append(f"min {fmt(getattr(roi_model, 'temp_min', None))}")
            parts2.append(f"max {fmt(getattr(roi_model, 'temp_max', None))}")
            parts2.append(f"mean {fmt(getattr(roi_model, 'temp_mean', None))}")
            line2 = " | ".join(parts2)

            label_text = f"{line1}\n{line2}"
            
            # Use larger font for better visibility in export
            font = painter.font()
            font.setPointSize(14)  # Increased from 10 to 14 for better visibility
            font.setBold(False)   
            painter.setFont(font)
            
            # Calculate text dimensions
            metrics = painter.fontMetrics()
            lines = label_text.split('\n')
            max_width = max(metrics.horizontalAdvance(line) for line in lines)
            line_height = metrics.height()
            total_height = line_height * len(lines)
            
            # Draw background rectangle with 25% opacity black and minimal padding
            padding_left = 0.5    # Reduced for tighter fit
            padding_right = 0     # No padding on right
            padding_vertical = 0.5  # Reduced for tighter fit
            
            background_rect = QRectF(
                label_x - padding_left,
                label_y - padding_vertical,
                max_width + padding_left + padding_right,
                total_height + 2 * padding_vertical
            )
            
            # Set brush for background rectangle (black with 25% opacity)
            background_color = QColor(0, 0, 0, 64)  # Black with 25% opacity (64/255 ≈ 25%)
            painter.setBrush(QBrush(background_color))
            painter.setPen(QPen(Qt.NoPen))  # No border for background
            painter.drawRect(background_rect)
            
            # Draw text with white color for maximum contrast
            painter.setPen(QPen(Qt.white))
            for i, line in enumerate(lines):
                text_y = label_y + (i + 1) * line_height - 3
                painter.drawText(QPointF(label_x, text_y), line)
                
            print(f"    🏷️ Drew label for {roi_model.name} at ({label_x:.1f}, {label_y:.1f})")
                
        except Exception as e:
            print(f"❌ Error drawing ROI label: {e}")

    def _draw_roi_label(self, painter: QPainter, roi_model):
        """
        Legacy method - now delegates to _draw_roi_label_at_position.
        """
        try:
            # Determine position based on ROI type
            if hasattr(roi_model, 'x') and hasattr(roi_model, 'y'):
                # Rectangular or Spot ROI
                label_x = roi_model.x + 10
                label_y = roi_model.y + 15
            elif hasattr(roi_model, 'points') and roi_model.points:
                # Polygon ROI - use first point
                first_point = roi_model.points[0]
                label_x = first_point[0] + 10
                label_y = first_point[1] + 15
            else:
                return  # Can't position label
            
            self._draw_roi_label_at_position(painter, roi_model, label_x, label_y)
                
        except Exception as e:
            print(f"❌ Error drawing ROI label (legacy): {e}")