"""
Settings Manager Module

This module contains the SettingsManager class responsible for handling
application settings persistence, including thermal parameters, ROI definitions,
palette settings, and overlay configurations.
"""

import json
import os
from typing import Dict, Any, Optional
from PySide6.QtCore import QObject, Signal


class SettingsManager(QObject):
    """
    Manager for application settings persistence.
    
    This class handles:
    - Saving and loading application settings to/from JSON files
    - Managing thermal calculation parameters
    - Persisting ROI definitions and configurations
    - Handling palette and overlay settings
    - Providing default values and validation
    """
    
    # Signals for settings events
    settings_loaded = Signal(dict)
    settings_saved = Signal(str)  # File path
    error_occurred = Signal(str)
    
    def __init__(self):
        """Initialize the settings manager with default configurations."""
        super().__init__()
        
        self.current_image_path = None
        self._ignore_auto_save = False
        
        # Default settings structure
        self.default_settings = {
            "version": "1.0",
            "thermal_parameters": {
                "Emissivity": 0.95,
                "AtmosphericTemperature": 20.0,
                "AtmosphericTransmission": 0.95,
                "RelativeHumidity": 50.0,
                "ObjectDistance": 1.0,
                "ReflectedApparentTemperature": 20.0
            },
            "palette": "Iron",
            "palette_inverted": False,
            "temp_range_settings": {
                "mode": "autorange",
                "manual_min": 0.0,
                "manual_max": 100.0
            },
            "overlay_settings": {
                "scale": 1.0,
                "offset_x": 0,
                "offset_y": 0,
                "opacity": 50,
                "blend_mode": "Normal"
            },
            "roi_label_settings": {
                "name": True,
                "emissivity": True,
                "min": True,
                "max": True,
                "avg": True,
                "median": False
            },
            "rois": []
        }

    def set_current_image_path(self, image_path: str):
        """
        Set the current image path for settings association.
        
        Args:
            image_path (str): Path to the current thermal image.
        """
        self.current_image_path = image_path

    def get_json_file_path(self) -> Optional[str]:
        """
        Get the JSON file path associated with the current image.
        
        Returns:
            str or None: Path to the JSON settings file.
        """
        if not self.current_image_path:
            return None
        
        base_path = os.path.splitext(self.current_image_path)[0]
        return f"{base_path}.json"

    def save_settings(self, thermal_parameters: Dict[str, Any] = None,
                     palette_settings: Dict[str, Any] = None,
                     overlay_settings: Dict[str, Any] = None,
                     roi_data: list = None,
                     roi_label_settings: Dict[str, bool] = None,
                     temp_range_settings: Dict[str, Any] = None) -> bool:
        """
        Save current settings to JSON file.
        
        Args:
            thermal_parameters (dict, optional): Thermal calculation parameters.
            palette_settings (dict, optional): Palette configuration.
            overlay_settings (dict, optional): Overlay alignment settings.
            roi_data (list, optional): ROI definitions.
            roi_label_settings (dict, optional): ROI label display settings.
            temp_range_settings (dict, optional): Temperature range settings.
            
        Returns:
            bool: True if saving was successful, False otherwise.
        """
        if not self.current_image_path or self._ignore_auto_save:
            return False
        
        json_path = self.get_json_file_path()
        if not json_path:
            return False
        
        try:
            # Start with default settings structure
            settings_data = self.default_settings.copy()
            
            # Update with provided parameters
            if thermal_parameters:
                # Only save user-modifiable thermal parameters
                user_params = {}
                saveable_params = [
                    "Emissivity", "AtmosphericTemperature", 
                    "AtmosphericTransmission", "RelativeHumidity",
                    "ObjectDistance", "ReflectedApparentTemperature"
                ]
                
                for param in saveable_params:
                    if param in thermal_parameters:
                        try:
                            user_params[param] = float(thermal_parameters[param])
                        except (ValueError, TypeError):
                            pass  # Skip invalid values
                            
                settings_data["thermal_parameters"] = user_params
                
            if palette_settings:
                settings_data["palette"] = palette_settings.get("palette", "Iron")
                settings_data["palette_inverted"] = palette_settings.get("inverted", False)
                
            if overlay_settings:
                settings_data["overlay_settings"] = {
                    "scale": overlay_settings.get("scale", 1.0),
                    "offset_x": overlay_settings.get("offset_x", 0),
                    "offset_y": overlay_settings.get("offset_y", 0),
                    "opacity": overlay_settings.get("opacity", 50),
                    "blend_mode": overlay_settings.get("blend_mode", "Normal")
                }
                
            if roi_data:
                settings_data["rois"] = roi_data
                
            if roi_label_settings:
                settings_data["roi_label_settings"] = roi_label_settings
                
            if temp_range_settings:
                settings_data["temp_range_settings"] = {
                    "mode": temp_range_settings.get("mode", "autorange"),
                    "manual_min": temp_range_settings.get("manual_min", 0.0),
                    "manual_max": temp_range_settings.get("manual_max", 100.0)
                }
                
            # Ensure directory exists and save to file
            os.makedirs(os.path.dirname(json_path), exist_ok=True)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(settings_data, f, indent=2, ensure_ascii=False)
            
            print(f"Settings saved to: {json_path}")
            self.settings_saved.emit(json_path)
            return True
            
        except Exception as e:
            error_msg = f"Error saving settings: {e}"
            print(error_msg)
            self.error_occurred.emit(error_msg)
            return False

    def load_settings(self) -> Optional[Dict[str, Any]]:
        """
        Load settings from JSON file if it exists.
        
        Returns:
            dict or None: Loaded settings data, or None if file doesn't exist.
        """
        if not self.current_image_path:
            return None
        
        json_path = self.get_json_file_path()
        if not json_path or not os.path.exists(json_path):
            return None
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                settings_data = json.load(f)
            
            print(f"Settings loaded from: {json_path}")
            
            # Validate and merge with defaults
            validated_settings = self._validate_settings(settings_data)
            
            self.settings_loaded.emit(validated_settings)
            return validated_settings
            
        except Exception as e:
            error_msg = f"Error loading settings: {e}"
            print(error_msg)
            self.error_occurred.emit(error_msg)
            return None

    def _validate_settings(self, settings_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate loaded settings and merge with defaults.
        
        Args:
            settings_data (dict): Raw settings data from file.
            
        Returns:
            dict: Validated settings with defaults for missing values.
        """
        validated = self.default_settings.copy()
        
        # Validate thermal parameters
        if "thermal_parameters" in settings_data:
            thermal_params = settings_data["thermal_parameters"]
            for key, default_value in validated["thermal_parameters"].items():
                if key in thermal_params:
                    try:
                        validated["thermal_parameters"][key] = float(thermal_params[key])
                    except (ValueError, TypeError):
                        pass  # Keep default value
                        
        # Validate palette settings
        if "palette" in settings_data:
            validated["palette"] = str(settings_data["palette"])
            
        if "palette_inverted" in settings_data:
            validated["palette_inverted"] = bool(settings_data["palette_inverted"])
            
        # Validate overlay settings
        if "overlay_settings" in settings_data:
            overlay = settings_data["overlay_settings"]
            if isinstance(overlay, dict):
                for key, default_value in validated["overlay_settings"].items():
                    if key in overlay:
                        try:
                            if key in ["offset_x", "offset_y", "opacity"]:
                                validated["overlay_settings"][key] = int(overlay[key])
                            elif key == "scale":
                                validated["overlay_settings"][key] = float(overlay[key])
                            else:
                                validated["overlay_settings"][key] = str(overlay[key])
                        except (ValueError, TypeError):
                            pass  # Keep default value
                            
        # Validate ROI label settings
        if "roi_label_settings" in settings_data:
            roi_labels = settings_data["roi_label_settings"]
            if isinstance(roi_labels, dict):
                for key in validated["roi_label_settings"]:
                    if key in roi_labels:
                        validated["roi_label_settings"][key] = bool(roi_labels[key])
                        
        # Validate ROI data
        if "rois" in settings_data and isinstance(settings_data["rois"], list):
            validated["rois"] = settings_data["rois"]
            
        return validated

    def get_default_settings(self) -> Dict[str, Any]:
        """
        Get a copy of the default settings.
        
        Returns:
            dict: Default settings structure.
        """
        return self.default_settings.copy()

    def set_auto_save_enabled(self, enabled: bool):
        """
        Enable or disable automatic saving.
        
        Args:
            enabled (bool): Whether auto-save should be enabled.
        """
        self._ignore_auto_save = not enabled

    def is_auto_save_enabled(self) -> bool:
        """
        Check if auto-save is currently enabled.
        
        Returns:
            bool: True if auto-save is enabled, False otherwise.
        """
        return not self._ignore_auto_save

    def create_backup(self, suffix: str = "_backup") -> Optional[str]:
        """
        Create a backup of the current settings file.
        
        Args:
            suffix (str): Suffix to append to the backup filename.
            
        Returns:
            str or None: Path to the backup file, or None if failed.
        """
        json_path = self.get_json_file_path()
        if not json_path or not os.path.exists(json_path):
            return None
            
        try:
            backup_path = json_path.replace('.json', f'{suffix}.json')
            
            with open(json_path, 'r', encoding='utf-8') as src:
                content = src.read()
                
            with open(backup_path, 'w', encoding='utf-8') as dst:
                dst.write(content)
                
            print(f"Backup created: {backup_path}")
            return backup_path
            
        except Exception as e:
            error_msg = f"Error creating backup: {e}"
            print(error_msg)
            self.error_occurred.emit(error_msg)
            return None

    def delete_settings_file(self) -> bool:
        """
        Delete the settings file for the current image.
        
        Returns:
            bool: True if deletion was successful, False otherwise.
        """
        json_path = self.get_json_file_path()
        if not json_path or not os.path.exists(json_path):
            return False
            
        try:
            os.remove(json_path)
            print(f"Settings file deleted: {json_path}")
            return True
            
        except Exception as e:
            error_msg = f"Error deleting settings file: {e}"
            print(error_msg)
            self.error_occurred.emit(error_msg)
            return False
