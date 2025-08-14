"""
Core Module

This package contains the core business logic classes for the thermal analysis application:
- ThermalEngine: Handles thermal data processing and temperature calculations
- ROIController: Manages Region of Interest operations and analysis
- SettingsManager: Handles application settings persistence
"""

from .thermal_engine import ThermalEngine
from .roi_controller import ROIController
from .settings_manager import SettingsManager

__all__ = ['ThermalEngine', 'ROIController', 'SettingsManager']
