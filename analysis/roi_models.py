# analysis/roi_models.py
import uuid
import math
from typing import Optional, Union
import numpy as np


class StatisticsCalculator:
    """
    Utility class for calculating temperature statistics for ROI regions.
    
    This class implements the Separation of Concerns principle by separating
    statistical calculations from ROI model data. It can calculate statistics
    for any ROI type (RectROI, SpotROI, PolygonROI) using polymorphism.
    """
    
    @staticmethod
    def calculate_statistics(roi: Union['RectROI', 'SpotROI', 'PolygonROI'], 
                           temperature_data: np.ndarray) -> dict:
        """
        Calculate temperature statistics for any ROI type.
        
        Args:
            roi: ROI model instance (RectROI, SpotROI, or PolygonROI)
            temperature_data: 2D numpy array of temperature values
            
        Returns:
            dict: Dictionary containing calculated statistics
                 Keys: 'min', 'max', 'mean', 'std', 'median' (median only for SpotROI and PolygonROI)
        """
        # Dispatch to specific calculation method based on ROI type
        if isinstance(roi, RectROI):
            return StatisticsCalculator._calculate_rect_statistics(roi, temperature_data)
        elif isinstance(roi, SpotROI):
            return StatisticsCalculator._calculate_spot_statistics(roi, temperature_data)
        elif isinstance(roi, PolygonROI):
            return StatisticsCalculator._calculate_polygon_statistics(roi, temperature_data)
        else:
            raise ValueError(f"Unsupported ROI type: {type(roi)}")
    
    @staticmethod
    def _calculate_rect_statistics(roi: 'RectROI', temperature_data: np.ndarray) -> dict:
        """Calculate statistics for rectangular ROI."""
        # Get integer bounds for array indexing
        x1, y1 = int(roi.x), int(roi.y)
        x2, y2 = int(roi.x + roi.width), int(roi.y + roi.height)
        
        # Ensure bounds are within array limits
        height, width = temperature_data.shape
        x1, x2 = max(0, x1), min(width, x2)
        y1, y2 = max(0, y1), min(height, y2)
        
        if x1 >= x2 or y1 >= y2:
            # Invalid bounds
            return {'min': None, 'max': None, 'mean': None, 'std': None}
        
        # Extract ROI region
        roi_temps = temperature_data[y1:y2, x1:x2]
        
        # Remove NaN values
        valid_temps = roi_temps[~np.isnan(roi_temps)]
        
        if len(valid_temps) == 0:
            return {'min': None, 'max': None, 'mean': None, 'std': None}
        else:
            return {
                'min': float(np.min(valid_temps)),
                'max': float(np.max(valid_temps)),
                'mean': float(np.mean(valid_temps)),
                'std': float(np.std(valid_temps))
            }
    
    @staticmethod
    def _calculate_spot_statistics(roi: 'SpotROI', temperature_data: np.ndarray) -> dict:
        """Calculate statistics for circular (spot) ROI."""
        # Get the bounds of the circle
        x1, y1, x2, y2 = roi.get_bounds()
        
        # Get integer bounds for array indexing
        x1, y1 = int(x1), int(y1)
        x2, y2 = int(x2), int(y2)
        
        # Ensure bounds are within array limits
        height, width = temperature_data.shape
        x1, x2 = max(0, x1), min(width, x2)
        y1, y2 = max(0, y1), min(height, y2)
        
        if x1 >= x2 or y1 >= y2:
            # Invalid bounds
            return {'min': None, 'max': None, 'mean': None, 'std': None, 'median': None}
        
        # Create a mask for the circular area
        y_indices, x_indices = np.ogrid[y1:y2, x1:x2]
        mask = ((x_indices - roi.x) ** 2 + (y_indices - roi.y) ** 2) <= (roi.radius ** 2)
        
        # Extract temperatures within the circular ROI
        roi_temps = temperature_data[y1:y2, x1:x2]
        circular_temps = roi_temps[mask]
        
        # Remove NaN values
        valid_temps = circular_temps[~np.isnan(circular_temps)]
        
        if len(valid_temps) == 0:
            return {'min': None, 'max': None, 'mean': None, 'std': None, 'median': None}
        else:
            return {
                'min': float(np.min(valid_temps)),
                'max': float(np.max(valid_temps)),
                'mean': float(np.mean(valid_temps)),
                'std': float(np.std(valid_temps)),
                'median': float(np.median(valid_temps))
            }
    
    @staticmethod
    def _calculate_polygon_statistics(roi: 'PolygonROI', temperature_data: np.ndarray) -> dict:
        """Calculate statistics for polygonal ROI."""
        if len(roi.points) < 3:
            return {'min': None, 'max': None, 'mean': None, 'std': None, 'median': None}
        
        # Get the bounds of the polygon
        x1, y1, x2, y2 = roi.get_bounds()
        
        # Get integer bounds for array indexing
        x1, y1 = int(x1), int(y1)
        x2, y2 = int(x2), int(y2)
        
        # Ensure bounds are within array limits
        height, width = temperature_data.shape
        x1, x2 = max(0, x1), min(width, x2)
        y1, y2 = max(0, y1), min(height, y2)
        
        if x1 >= x2 or y1 >= y2:
            return {'min': None, 'max': None, 'mean': None, 'std': None, 'median': None}
        
        # Create a mask for the polygonal area
        y_indices, x_indices = np.meshgrid(np.arange(y1, y2), np.arange(x1, x2), indexing='ij')
        
        # Check each pixel if it's inside the polygon
        mask = np.zeros((y2 - y1, x2 - x1), dtype=bool)
        for i in range(y2 - y1):
            for j in range(x2 - x1):
                mask[i, j] = roi.contains_point(x1 + j, y1 + i)
        
        # Extract temperatures within the polygonal ROI
        roi_temps = temperature_data[y1:y2, x1:x2]
        polygon_temps = roi_temps[mask]
        
        # Remove NaN values
        valid_temps = polygon_temps[~np.isnan(polygon_temps)]
        
        if len(valid_temps) == 0:
            return {'min': None, 'max': None, 'mean': None, 'std': None, 'median': None}
        else:
            return {
                'min': float(np.min(valid_temps)),
                'max': float(np.max(valid_temps)),
                'mean': float(np.mean(valid_temps)),
                'std': float(np.std(valid_temps)),
                'median': float(np.median(valid_temps))
            }


class RectROI:
    """
    Model class for rectangular Regions of Interest (ROI).
    
    Represents a rectangular area with position, dimensions, and metadata.
    Contains only data and simple geometric operations. Statistical calculations
    are handled by the StatisticsCalculator class.
    """
    
    def __init__(self, x: float, y: float, width: float, height: float, name: str = ""):
        """
        Initialize a rectangular ROI.
        
        Args:
            x: X coordinate of the top-left corner
            y: Y coordinate of the top-left corner  
            width: Width of the rectangle
            height: Height of the rectangle
            name: Optional name for the ROI
        """
        self.id = uuid.uuid4()
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.name = name if name else f"ROI_{str(self.id)[:8]}"
        
        # Statistics will be calculated and stored by StatisticsCalculator
        self.temp_min: Optional[float] = None
        self.temp_max: Optional[float] = None
        self.temp_mean: Optional[float] = None
        self.temp_std: Optional[float] = None
    
    def get_bounds(self):
        """
        Get the bounding coordinates of the ROI.
        
        Returns:
            tuple: (x1, y1, x2, y2) where (x1,y1) is top-left and (x2,y2) is bottom-right
        """
        return (self.x, self.y, self.x + self.width, self.y + self.height)
    
    def contains_point(self, x: float, y: float) -> bool:
        """
        Check if a point is inside this ROI.
        
        Args:
            x: X coordinate
            y: Y coordinate
            
        Returns:
            bool: True if point is inside the ROI
        """
        return (self.x <= x <= self.x + self.width and 
                self.y <= y <= self.y + self.height)
    
    def __str__(self):
        return f"RectROI(name='{self.name}', x={self.x}, y={self.y}, w={self.width}, h={self.height})"


class SpotROI:
    """
    Point/circle ROI with center (x,y) and radius in thermal pixels.
    
    Represents a circular area with position, radius, and metadata for
    thermal analysis of spot measurements. Contains only data and simple
    geometric operations. Statistical calculations are handled by the 
    StatisticsCalculator class.
    """
    
    def __init__(self, x: float, y: float, radius: float = 5.0, name: str = ""):
        """
        Initialize a spot (circular) ROI.
        
        Args:
            x: X coordinate of the center
            y: Y coordinate of the center
            radius: Radius of the circle in thermal pixels
            name: Optional name for the ROI
        """
        self.id = uuid.uuid4()
        self.x = x
        self.y = y
        self.radius = radius
        self.name = name if name else f"Spot_{str(self.id)[:8]}"
        
        # Statistics will be calculated and stored by StatisticsCalculator
        self.temp_min: Optional[float] = None
        self.temp_max: Optional[float] = None
        self.temp_mean: Optional[float] = None
        self.temp_std: Optional[float] = None
        self.temp_median: Optional[float] = None

    def get_bounds(self):
        """
        Get the bounding coordinates of the circular ROI.
        
        Returns:
            tuple: (x1, y1, x2, y2) where (x1,y1) is top-left and (x2,y2) is bottom-right of bounding box
        """
        return (self.x - self.radius, self.y - self.radius, 
                self.x + self.radius, self.y + self.radius)
    
    def contains_point(self, x: float, y: float) -> bool:
        """
        Check if a point is inside this circular ROI.
        
        Args:
            x: X coordinate
            y: Y coordinate
            
        Returns:
            bool: True if point is inside the circular ROI
        """
        distance = math.sqrt((x - self.x) ** 2 + (y - self.y) ** 2)
        return distance <= self.radius

    def __str__(self):
        return f"SpotROI(name='{self.name}', x={self.x}, y={self.y}, r={self.radius})"


class PolygonROI:
    """
    Model class for polygonal Regions of Interest (ROI).
    
    Represents a polygonal area defined by a list of vertices.
    Contains only data and simple geometric operations. Statistical 
    calculations are handled by the StatisticsCalculator class.
    """
    
    def __init__(self, points: list, name: str = ""):
        """
        Initialize a polygonal ROI.
        
        Args:
            points: List of (x, y) tuples defining the polygon vertices
            name: Optional name for the ROI
        """
        self.id = uuid.uuid4()
        self.points = points if points else []  # List of (x, y) tuples
        self.name = name if name else f"Polygon_{str(self.id)[:8]}"
        
        # Statistics will be calculated and stored by StatisticsCalculator
        self.temp_min: Optional[float] = None
        self.temp_max: Optional[float] = None
        self.temp_mean: Optional[float] = None
        self.temp_std: Optional[float] = None
        self.temp_median: Optional[float] = None
    
    def get_bounds(self):
        """
        Get the bounding coordinates of the polygon.
        
        Returns:
            tuple: (x1, y1, x2, y2) where (x1,y1) is top-left and (x2,y2) is bottom-right
        """
        if not self.points:
            return (0, 0, 0, 0)
        
        x_coords = [p[0] for p in self.points]
        y_coords = [p[1] for p in self.points]
        
        return (min(x_coords), min(y_coords), max(x_coords), max(y_coords))
    
    def contains_point(self, x: float, y: float) -> bool:
        """
        Check if a point is inside this polygon using ray casting algorithm.
        
        Args:
            x: X coordinate
            y: Y coordinate
            
        Returns:
            bool: True if point is inside the polygon
        """
        if len(self.points) < 3:
            return False
        
        # Ray casting algorithm
        inside = False
        j = len(self.points) - 1
        
        for i in range(len(self.points)):
            xi, yi = self.points[i]
            xj, yj = self.points[j]
            
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        
        return inside
    
    def add_point(self, x: float, y: float):
        """Add a point to the polygon."""
        self.points.append((x, y))
    
    def close_polygon(self):
        """Ensure the polygon is closed (first point = last point)."""
        if len(self.points) >= 3 and self.points[0] != self.points[-1]:
            self.points.append(self.points[0])
    
    def __str__(self):
        return f"PolygonROI(name='{self.name}', points={len(self.points)})"