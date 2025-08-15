"""
ROI Controller Module

This module contains the ROIController class responsible for managing
Region of Interest (ROI) operations, statistics calculation, and coordination
with the thermal engine for temperature analysis.
"""

import numpy as np
from typing import List, Optional, Dict, Any
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor

from analysis.roi_models import RectROI, SpotROI, PolygonROI


class ROIController(QObject):
    """
    Controller for managing ROI operations and analysis.
    
    This class handles:
    - ROI creation, modification, and deletion
    - Temperature statistics calculation for ROIs
    - ROI validation and error handling
    - Coordination with ThermalEngine for data access
    """
    
    # Signals for UI updates
    roi_added = Signal(object)  # ROI model
    roi_removed = Signal(str)   # ROI ID
    roi_modified = Signal(object)  # ROI model
    rois_cleared = Signal()
    analysis_updated = Signal()
    
    def __init__(self, thermal_engine=None):
        """
        Initialize the ROI controller.
        
        Args:
            thermal_engine: ThermalEngine instance for data access.
        """
        super().__init__()
        self.thermal_engine = thermal_engine
        self.rois: List[Any] = []
        self._next_roi_id = 1
        
        # Default color scheme for ROIs
        self._color_hue_step = 55
        
        # Performance optimization: prevent spam during updates
        self._updating_statistics = False
        self._pending_updates = set()  # Track ROIs that need update

    def set_thermal_engine(self, thermal_engine):
        """
        Set the thermal engine reference.
        
        Args:
            thermal_engine: ThermalEngine instance.
        """
        self.thermal_engine = thermal_engine

    def create_rect_roi(self, x: float, y: float, width: float, height: float, 
                       name: str = None, emissivity: float = 0.95) -> RectROI:
        """
        Create a new rectangular ROI.
        
        Args:
            x (float): X coordinate of top-left corner.
            y (float): Y coordinate of top-left corner.
            width (float): Width of the rectangle.
            height (float): Height of the rectangle.
            name (str, optional): ROI name. Auto-generated if None.
            emissivity (float): Emissivity value for this ROI.
            
        Returns:
            RectROI: The created ROI model.
        """
        if name is None:
            name = f"ROI_{self._next_roi_id}"
            self._next_roi_id += 1
            
        roi_model = RectROI(x=x, y=y, width=width, height=height, name=name)
        roi_model.emissivity = emissivity
        roi_model.color = self._generate_roi_color()
        
        self.rois.append(roi_model)
        self._update_roi_statistics(roi_model)
        
        self.roi_added.emit(roi_model)
        return roi_model

    def create_spot_roi(self, x: float, y: float, radius: float, 
                       name: str = None, emissivity: float = 0.95) -> SpotROI:
        """
        Create a new spot (circular) ROI.
        
        Args:
            x (float): X coordinate of center.
            y (float): Y coordinate of center.
            radius (float): Radius of the circle.
            name (str, optional): ROI name. Auto-generated if None.
            emissivity (float): Emissivity value for this ROI.
            
        Returns:
            SpotROI: The created ROI model.
        """
        if name is None:
            name = f"Spot_{self._next_roi_id}"
            self._next_roi_id += 1
            
        roi_model = SpotROI(x=x, y=y, radius=radius, name=name)
        roi_model.emissivity = emissivity
        roi_model.color = self._generate_roi_color()
        
        self.rois.append(roi_model)
        self._update_roi_statistics(roi_model)
        
        self.roi_added.emit(roi_model)
        return roi_model

    def create_polygon_roi(self, points: List[tuple], name: str = None, 
                         emissivity: float = 0.95) -> PolygonROI:
        """
        Create a new polygon ROI.
        
        Args:
            points (List[tuple]): List of (x, y) coordinate tuples.
            name (str, optional): ROI name. Auto-generated if None.
            emissivity (float): Emissivity value for this ROI.
            
        Returns:
            PolygonROI: The created ROI model.
        """
        if name is None:
            name = f"Polygon_{self._next_roi_id}"
            self._next_roi_id += 1
            
        roi_model = PolygonROI(points=points, name=name)
        roi_model.emissivity = emissivity
        roi_model.color = self._generate_roi_color()
        
        self.rois.append(roi_model)
        self._update_roi_statistics(roi_model)
        
        self.roi_added.emit(roi_model)
        return roi_model

    def delete_roi(self, roi_id: Any) -> bool:
        """
        Delete an ROI by its ID.
        
        Args:
            roi_id (Any): ID of the ROI to delete (UUID object).
            
        Returns:
            bool: True if deletion was successful, False otherwise.
        """
        for i, roi in enumerate(self.rois):
            if roi.id == roi_id:
                removed_roi = self.rois.pop(i)
                self.roi_removed.emit(str(roi_id))
                print(f"Deleted ROI: {removed_roi.name}")
                return True
        return False

    def delete_rois(self, roi_ids: List[Any]) -> int:
        """
        Delete multiple ROIs by their IDs.
        
        Args:
            roi_ids (List[Any]): List of ROI IDs to delete (UUID objects).
            
        Returns:
            int: Number of ROIs successfully deleted.
        """
        deleted_count = 0
        # Sort by index in reverse order to avoid index shifting issues
        for roi_id in roi_ids:
            if self.delete_roi(roi_id):
                deleted_count += 1
        return deleted_count

    def clear_all_rois(self) -> int:
        """
        Clear all ROIs.
        
        Returns:
            int: Number of ROIs that were cleared.
        """
        count = len(self.rois)
        self.rois.clear()
        self._next_roi_id = 1
        self.rois_cleared.emit()
        print(f"Cleared {count} ROIs")
        return count

    def update_roi(self, roi_id: str, **kwargs) -> bool:
        """
        Update an ROI's properties.
        
        Args:
            roi_id (str): ID of the ROI to update.
            **kwargs: Properties to update (name, emissivity, etc.).
            
        Returns:
            bool: True if update was successful, False otherwise.
        """
        roi = self.get_roi_by_id(roi_id)
        if roi is None:
            return False
            
        # Update properties
        for key, value in kwargs.items():
            if hasattr(roi, key):
                setattr(roi, key, value)
                
        # Recalculate statistics if emissivity changed
        if 'emissivity' in kwargs:
            self._update_roi_statistics(roi)
            self.analysis_updated.emit()  # Emit to trigger UI refresh for statistics changes
            
        self.roi_modified.emit(roi)
        return True

    def update_roi_geometry(self, roi_id: str, geometry_data: dict) -> bool:
        """
        Update an ROI's geometry and recalculate statistics.
        
        This method is specifically designed to handle geometry updates from
        the UI (when ROIs are moved, resized, etc.) and ensures that temperature
        statistics are recalculated based on the new geometry.
        
        Args:
            roi_id (str): ID of the ROI to update.
            geometry_data (dict): Dictionary containing geometry data:
                - For RectROI: x, y, width, height
                - For SpotROI: x, y, radius  
                - For PolygonROI: points
                
        Returns:
            bool: True if update was successful, False otherwise.
        """
        roi = self.get_roi_by_id(roi_id)
        if roi is None:
            print(f"❌ ROI {roi_id} not found for geometry update")
            return False
            
        # Update geometry properties
        geometry_updated = False
        for key, value in geometry_data.items():
            if hasattr(roi, key):
                setattr(roi, key, value)
                geometry_updated = True
                
        if not geometry_updated:
            print(f"⚠️ No geometry properties updated for ROI {roi_id}")
            return False
            
        # Recalculate temperature statistics since geometry changed
        self._update_roi_statistics(roi)
        
        # Emit signals to notify UI of the update
        self.roi_modified.emit(roi)
        self.analysis_updated.emit()  # Also emit this to trigger UI refresh
        
        print(f"✅ Updated geometry for ROI {roi.name} (ID: {roi_id})")
        return True

    def get_roi_by_id(self, roi_id: str) -> Optional[Any]:
        """
        Get an ROI by its ID.
        
        Args:
            roi_id (str): ID of the ROI to find.
            
        Returns:
            ROI model or None if not found.
        """
        for roi in self.rois:
            if roi.id == roi_id:
                return roi
        return None

    def get_all_rois(self) -> List[Any]:
        """
        Get all ROIs.
        
        Returns:
            List[Any]: List of all ROI models.
        """
        return self.rois.copy()

    def update_all_analyses(self):
        """Update temperature statistics for all ROIs."""
        for roi in self.rois:
            self._update_roi_statistics(roi)
        self.analysis_updated.emit()

    def _update_roi_statistics(self, roi):
        """
        Update temperature statistics for a single ROI.
        
        Args:
            roi: ROI model to update.
        """
        # Prevent recursive updates or spam during batch operations
        if self._updating_statistics:
            self._pending_updates.add(roi.id)
            return
            
        if self.thermal_engine is None:
            print(f"⚠️ No thermal engine available for ROI {roi.name}")
            roi.temp_min = roi.temp_max = roi.temp_mean = None
            roi.temp_std = roi.temp_median = None
            return
            
        if self.thermal_engine.thermal_data is None:
            print(f"⚠️ No thermal data available for ROI {roi.name}")
            roi.temp_min = roi.temp_max = roi.temp_mean = None
            roi.temp_std = roi.temp_median = None
            return
            
        self._updating_statistics = True
        try:
            # Create mask for this ROI
            roi_mask = self._create_roi_mask(roi)
            if roi_mask is None:
                print(f"⚠️ Failed to create mask for ROI {roi.name}")
                roi.temp_min = roi.temp_max = roi.temp_mean = None
                roi.temp_std = roi.temp_median = None
                
            elif not np.any(roi_mask):
                print(f"⚠️ Empty mask for ROI {roi.name} - ROI might be outside image bounds")
                roi.temp_min = roi.temp_max = roi.temp_mean = None
                roi.temp_std = roi.temp_median = None
                
            else:
                # Get temperature values for ROI
                roi_emissivity = getattr(roi, 'emissivity', 0.95)
                temps = self.thermal_engine.compute_roi_temperatures(roi_mask, roi_emissivity)
                
                if temps.size > 0:
                    valid_temps = temps[~np.isnan(temps)]
                    if valid_temps.size > 0:
                        roi.temp_min = float(np.min(valid_temps))
                        roi.temp_max = float(np.max(valid_temps))
                        roi.temp_mean = float(np.mean(valid_temps))
                        roi.temp_std = float(np.std(valid_temps))
                        roi.temp_median = float(np.median(valid_temps))
                        # Statistics updated successfully (reduced logging for performance)
                    else:
                        print(f"⚠️ All temperature values are NaN for ROI {roi.name}")
                        roi.temp_min = roi.temp_max = roi.temp_mean = None
                        roi.temp_std = roi.temp_median = None
                else:
                    print(f"⚠️ No temperature values computed for ROI {roi.name}")
                    roi.temp_min = roi.temp_max = roi.temp_mean = None
                    roi.temp_std = roi.temp_median = None
                
        except Exception as e:
            print(f"❌ Error updating ROI statistics for {roi.name}: {e}")
            import traceback
            traceback.print_exc()
            roi.temp_min = roi.temp_max = roi.temp_mean = None
            roi.temp_std = roi.temp_median = None
        finally:
            self._updating_statistics = False
            
            # Process any pending updates that accumulated during this calculation
            if self._pending_updates:
                pending_roi_ids = self._pending_updates.copy()
                self._pending_updates.clear()
                
                # Schedule pending updates (debounced)
                for pending_roi_id in pending_roi_ids:
                    pending_roi = self.get_roi_by_id(pending_roi_id)
                    if pending_roi and pending_roi != roi:  # Avoid immediate re-calculation of same ROI
                        print(f"⏰ Processing deferred update for ROI {pending_roi.name}")
                        self._update_roi_statistics(pending_roi)

    def _create_roi_mask(self, roi) -> Optional[np.ndarray]:
        """
        Create a boolean mask for an ROI.
        
        Args:
            roi: ROI model.
            
        Returns:
            np.ndarray or None: Boolean mask indicating ROI pixels.
        """
        if self.thermal_engine.thermal_data is None:
            return None
            
        h, w = self.thermal_engine.thermal_data.shape
        mask = np.zeros((h, w), dtype=bool)
        
        try:
            if isinstance(roi, SpotROI):
                # Circular mask for spot ROI
                x1, y1, x2, y2 = roi.get_bounds()
                x1, y1 = max(0, int(x1)), max(0, int(y1))
                x2, y2 = min(w, int(x2)), min(h, int(y2))
                
                # Check if ROI is within image bounds
                if x1 >= w or y1 >= h or x2 <= 0 or y2 <= 0:
                    print(f"⚠️ SpotROI {roi.name} is outside image bounds: center=({roi.x}, {roi.y}), radius={roi.radius}, image_size=({w}, {h})")
                    return mask  # Return empty mask
                
                if x1 < x2 and y1 < y2:
                    y_indices, x_indices = np.ogrid[y1:y2, x1:x2]
                    circle_mask = ((x_indices - roi.x) ** 2 + (y_indices - roi.y) ** 2) <= (roi.radius ** 2)
                    mask[y1:y2, x1:x2] = circle_mask
                    
            elif isinstance(roi, PolygonROI):
                # Polygon mask - optimized version using vectorized operations
                x1, y1, x2, y2 = roi.get_bounds()
                x1, y1 = max(0, int(x1)), max(0, int(y1))
                x2, y2 = min(w, int(x2)), min(h, int(y2))
                
                # Check if ROI is within image bounds
                if x1 >= w or y1 >= h or x2 <= 0 or y2 <= 0:
                    print(f"⚠️ PolygonROI {roi.name} is outside image bounds: bounds=({x1}, {y1}, {x2}, {y2}), image_size=({w}, {h})")
                    return mask  # Return empty mask
                
                if x1 < x2 and y1 < y2:
                    # Create vectorized coordinate grids for the bounding box
                    y_coords, x_coords = np.mgrid[y1:y2, x1:x2]
                    
                    # Vectorized ray casting algorithm for polygon
                    mask_section = self._polygon_contains_points_vectorized(
                        roi.points, x_coords.flatten(), y_coords.flatten()
                    )
                    
                    # Reshape back to 2D and assign to mask
                    mask[y1:y2, x1:x2] = mask_section.reshape(y2-y1, x2-x1)
                                
            else:
                # Rectangular mask (default)
                x1 = max(0, int(np.floor(roi.x)))
                y1 = max(0, int(np.floor(roi.y)))
                x2 = min(w, int(np.ceil(roi.x + roi.width)))
                y2 = min(h, int(np.ceil(roi.y + roi.height)))
                
                # Check if ROI is within image bounds
                if x1 >= w or y1 >= h or x2 <= 0 or y2 <= 0:
                    print(f"⚠️ RectROI {roi.name} is outside image bounds: rect=({roi.x}, {roi.y}, {roi.width}, {roi.height}), image_size=({w}, {h})")
                    return mask  # Return empty mask
                
                if x1 < x2 and y1 < y2:
                    mask[y1:y2, x1:x2] = True
                    
            pixel_count = np.sum(mask)
            if pixel_count == 0:
                print(f"⚠️ ROI {roi.name} mask contains no pixels after bounds checking")
            # Reduced logging for performance - only log if pixel count is 0 or on error
                    
            return mask
            
        except Exception as e:
            print(f"❌ Error creating ROI mask for {roi.name}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _polygon_contains_points_vectorized(self, polygon_points, x_coords, y_coords):
        """
        Vectorized ray casting algorithm for polygon point-in-polygon test.
        
        Args:
            polygon_points: List of (x, y) tuples defining polygon vertices
            x_coords: Flattened array of x coordinates to test
            y_coords: Flattened array of y coordinates to test
            
        Returns:
            np.ndarray: Boolean array indicating which points are inside polygon
        """
        if len(polygon_points) < 3:
            return np.zeros_like(x_coords, dtype=bool)
        
        # Convert polygon points to numpy arrays for vectorized operations
        polygon_points = np.array(polygon_points)
        n_vertices = len(polygon_points)
        
        # Initialize result array
        inside = np.zeros_like(x_coords, dtype=bool)
        
        # Ray casting algorithm - vectorized version
        j = n_vertices - 1
        for i in range(n_vertices):
            xi, yi = polygon_points[i]
            xj, yj = polygon_points[j]
            
            # Vectorized conditions for ray casting
            condition1 = (yi > y_coords) != (yj > y_coords)
            
            # Avoid division by zero when yj == yi
            with np.errstate(divide='ignore', invalid='ignore'):
                condition2 = x_coords < (xj - xi) * (y_coords - yi) / (yj - yi) + xi
                # Handle division by zero case (horizontal line)
                condition2 = np.where(yj == yi, False, condition2)
            
            # Update inside array where both conditions are true
            inside = inside ^ (condition1 & condition2)
            j = i
            
        return inside

    def _generate_roi_color(self) -> QColor:
        """
        Generate a distinct color for a new ROI.
        
        Returns:
            QColor: Color for the ROI.
        """
        hue = (len(self.rois) * self._color_hue_step) % 360
        return QColor.fromHsv(hue, 220, 255)

    def export_roi_data(self) -> List[Dict[str, Any]]:
        """
        Export all ROI data for serialization.
        
        Returns:
            List[Dict[str, Any]]: List of ROI data dictionaries.
        """
        roi_data = []
        for roi in self.rois:
            data = {
                "type": roi.__class__.__name__,
                "name": roi.name,
                "emissivity": getattr(roi, 'emissivity', 0.95)
            }
            
            # Add geometry-specific data
            if hasattr(roi, 'x') and hasattr(roi, 'y'):
                data["x"] = roi.x
                data["y"] = roi.y
                
            if hasattr(roi, 'width') and hasattr(roi, 'height'):
                data["width"] = roi.width
                data["height"] = roi.height
            elif hasattr(roi, 'radius'):
                data["radius"] = roi.radius
            elif hasattr(roi, 'points'):
                data["points"] = roi.points
                
            roi_data.append(data)
            
        return roi_data

    def import_roi_data(self, roi_data_list: List[Dict[str, Any]]) -> int:
        """
        Import ROI data from serialized format.
        
        Args:
            roi_data_list (List[Dict[str, Any]]): List of ROI data dictionaries.
            
        Returns:
            int: Number of ROIs successfully imported.
        """
        imported_count = 0
        
        for roi_data in roi_data_list:
            try:
                roi_type = roi_data.get("type", "")
                roi_name = roi_data.get("name", f"ROI_{self._next_roi_id}")
                roi_emissivity = roi_data.get("emissivity", 0.95)
                
                if roi_type == "RectROI":
                    self.create_rect_roi(
                        x=roi_data.get("x", 0),
                        y=roi_data.get("y", 0),
                        width=roi_data.get("width", 50),
                        height=roi_data.get("height", 50),
                        name=roi_name,
                        emissivity=roi_emissivity
                    )
                    imported_count += 1
                    
                elif roi_type == "SpotROI":
                    self.create_spot_roi(
                        x=roi_data.get("x", 0),
                        y=roi_data.get("y", 0),
                        radius=roi_data.get("radius", 5),
                        name=roi_name,
                        emissivity=roi_emissivity
                    )
                    imported_count += 1
                    
                elif roi_type == "PolygonROI":
                    points = roi_data.get("points", [(0, 0), (50, 0), (50, 50), (0, 50)])
                    self.create_polygon_roi(
                        points=points,
                        name=roi_name,
                        emissivity=roi_emissivity
                    )
                    imported_count += 1
                    
            except Exception as e:
                print(f"Error importing ROI: {e}")
                
        return imported_count

    def export_detailed_roi_data(self) -> List[Dict[str, Any]]:
        """
        Export detailed ROI data including all calculated statistics.
        
        Returns:
            List[Dict[str, Any]]: List of detailed ROI data dictionaries.
        """
        detailed_data = []
        
        for roi in self.rois:
            try:
                # Get basic ROI data
                data = {
                    "name": roi.name,
                    "type": roi.__class__.__name__,
                    "emissivity": getattr(roi, 'emissivity', 0.95),
                    "temp_min": getattr(roi, 'temp_min', None),
                    "temp_max": getattr(roi, 'temp_max', None),
                    "temp_mean": getattr(roi, 'temp_mean', None),
                    "temp_median": getattr(roi, 'temp_median', None),
                    "temp_std": getattr(roi, 'temp_std', None),
                    "pixel_count": 0
                }
                
                # Calculate pixel count
                if self.thermal_engine and self.thermal_engine.thermal_data is not None:
                    roi_mask = self._create_roi_mask(roi)
                    if roi_mask is not None:
                        data["pixel_count"] = int(np.sum(roi_mask))
                
                detailed_data.append(data)
                
            except Exception as e:
                print(f"Error exporting ROI data for {roi.name}: {e}")
                # Add minimal data for failed ROI
                detailed_data.append({
                    "name": getattr(roi, 'name', 'Unknown'),
                    "type": roi.__class__.__name__,
                    "emissivity": getattr(roi, 'emissivity', 0.95),
                    "temp_min": None,
                    "temp_max": None,
                    "temp_mean": None,
                    "temp_median": None,
                    "temp_std": None,
                    "pixel_count": 0
                })
                
        return detailed_data
