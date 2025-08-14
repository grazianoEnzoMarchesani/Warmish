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
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import QObject, Signal

from constants import PALETTE_MAP
import matplotlib.cm as cm


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
            
            # Extract EXIF metadata using exiftool
            with exiftool.ExifTool() as et:
                json_string = et.execute(b"-json", file_path.encode())
                self.metadata = json.loads(json_string)[0]
                
            # Extract raw thermal data
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
            command_rgb = ["exiftool", "-b", "-EmbeddedImage", file_path]
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
