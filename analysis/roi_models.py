# analysis/roi_models.py
import uuid
from typing import Optional


class RectROI:
    """
    Model class for rectangular Regions of Interest (ROI).
    
    Represents a rectangular area with position, dimensions, and metadata.
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
        
        # Statistics will be calculated when analyzing temperature data
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
    
    def calculate_statistics(self, temperature_data):
        """
        Calculate temperature statistics for this ROI area.
        
        Args:
            temperature_data: 2D numpy array of temperature values
        """
        import numpy as np
        
        # Get integer bounds for array indexing
        x1, y1 = int(self.x), int(self.y)
        x2, y2 = int(self.x + self.width), int(self.y + self.height)
        
        # Ensure bounds are within array limits
        height, width = temperature_data.shape
        x1, x2 = max(0, x1), min(width, x2)
        y1, y2 = max(0, y1), min(height, y2)
        
        if x1 >= x2 or y1 >= y2:
            # Invalid bounds
            self.temp_min = self.temp_max = self.temp_mean = self.temp_std = None
            return
        
        # Extract ROI region
        roi_temps = temperature_data[y1:y2, x1:x2]
        
        # Remove NaN values
        valid_temps = roi_temps[~np.isnan(roi_temps)]
        
        if len(valid_temps) == 0:
            self.temp_min = self.temp_max = self.temp_mean = self.temp_std = None
        else:
            self.temp_min = float(np.min(valid_temps))
            self.temp_max = float(np.max(valid_temps))
            self.temp_mean = float(np.mean(valid_temps))
            self.temp_std = float(np.std(valid_temps))
    
    def __str__(self):
        return f"RectROI(name='{self.name}', x={self.x}, y={self.y}, w={self.width}, h={self.height})"

class SpotROI:
    """
    Punto/cerchio ROI con centro (x,y) e raggio in pixel termici.
    """
    def __init__(self, x: float, y: float, radius: float = 5.0, name: str = ""):
        import uuid
        from typing import Optional
        self.id = uuid.uuid4()
        self.x = x
        self.y = y
        self.radius = radius
        self.name = name if name else f"Spot_{str(self.id)[:8]}"
        
        # Statistics will be calculated when analyzing temperature data
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
        import math
        distance = math.sqrt((x - self.x) ** 2 + (y - self.y) ** 2)
        return distance <= self.radius
    
    def calculate_statistics(self, temperature_data):
        """
        Calculate temperature statistics for this circular ROI area.
        
        Args:
            temperature_data: 2D numpy array of temperature values
        """
        import numpy as np
        
        # Get the bounds of the circle
        x1, y1, x2, y2 = self.get_bounds()
        
        # Get integer bounds for array indexing
        x1, y1 = int(x1), int(y1)
        x2, y2 = int(x2), int(y2)
        
        # Ensure bounds are within array limits
        height, width = temperature_data.shape
        x1, x2 = max(0, x1), min(width, x2)
        y1, y2 = max(0, y1), min(height, y2)
        
        if x1 >= x2 or y1 >= y2:
            # Invalid bounds
            self.temp_min = self.temp_max = self.temp_mean = self.temp_std = self.temp_median = None
            return
        
        # Create a mask for the circular area
        y_indices, x_indices = np.ogrid[y1:y2, x1:x2]
        mask = ((x_indices - self.x) ** 2 + (y_indices - self.y) ** 2) <= (self.radius ** 2)
        
        # Extract temperatures within the circular ROI
        roi_temps = temperature_data[y1:y2, x1:x2]
        circular_temps = roi_temps[mask]
        
        # Remove NaN values
        valid_temps = circular_temps[~np.isnan(circular_temps)]
        
        if len(valid_temps) == 0:
            self.temp_min = self.temp_max = self.temp_mean = self.temp_std = self.temp_median = None
        else:
            self.temp_min = float(np.min(valid_temps))
            self.temp_max = float(np.max(valid_temps))
            self.temp_mean = float(np.mean(valid_temps))
            self.temp_std = float(np.std(valid_temps))
            self.temp_median = float(np.median(valid_temps))

    def __str__(self):
        return f"SpotROI(name='{self.name}', x={self.x}, y={self.y}, r={self.radius})"

class PolygonROI:
    """
    Model class for polygonal Regions of Interest (ROI).
    
    Represents a polygonal area defined by a list of vertices.
    """
    
    def __init__(self, points: list, name: str = ""):
        """
        Initialize a polygonal ROI.
        
        Args:
            points: List of (x, y) tuples defining the polygon vertices
            name: Optional name for the ROI
        """
        self.id = uuid.uuid4()
        self.points = points if points else []  # Lista di tuple (x, y)
        self.name = name if name else f"Polygon_{str(self.id)[:8]}"
        
        # Statistics will be calculated when analyzing temperature data
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
    
    def calculate_statistics(self, temperature_data):
        """
        Calculate temperature statistics for this polygonal ROI area.
        
        Args:
            temperature_data: 2D numpy array of temperature values
        """
        import numpy as np
        
        if len(self.points) < 3:
            self.temp_min = self.temp_max = self.temp_mean = self.temp_std = self.temp_median = None
            return
        
        # Get the bounds of the polygon
        x1, y1, x2, y2 = self.get_bounds()
        
        # Get integer bounds for array indexing
        x1, y1 = int(x1), int(y1)
        x2, y2 = int(x2), int(y2)
        
        # Ensure bounds are within array limits
        height, width = temperature_data.shape
        x1, x2 = max(0, x1), min(width, x2)
        y1, y2 = max(0, y1), min(height, y2)
        
        if x1 >= x2 or y1 >= y2:
            self.temp_min = self.temp_max = self.temp_mean = self.temp_std = self.temp_median = None
            return
        
        # Create a mask for the polygonal area
        y_indices, x_indices = np.meshgrid(np.arange(y1, y2), np.arange(x1, x2), indexing='ij')
        
        # Check each pixel if it's inside the polygon
        mask = np.zeros((y2 - y1, x2 - x1), dtype=bool)
        for i in range(y2 - y1):
            for j in range(x2 - x1):
                mask[i, j] = self.contains_point(x1 + j, y1 + i)
        
        # Extract temperatures within the polygonal ROI
        roi_temps = temperature_data[y1:y2, x1:x2]
        polygon_temps = roi_temps[mask]
        
        # Remove NaN values
        valid_temps = polygon_temps[~np.isnan(polygon_temps)]
        
        if len(valid_temps) == 0:
            self.temp_min = self.temp_max = self.temp_mean = self.temp_std = self.temp_median = None
        else:
            self.temp_min = float(np.min(valid_temps))
            self.temp_max = float(np.max(valid_temps))
            self.temp_mean = float(np.mean(valid_temps))
            self.temp_std = float(np.std(valid_temps))
            self.temp_median = float(np.median(valid_temps))
    
    def add_point(self, x: float, y: float):
        """Add a point to the polygon."""
        self.points.append((x, y))
    
    def close_polygon(self):
        """Ensure the polygon is closed (first point = last point)."""
        if len(self.points) >= 3 and self.points[0] != self.points[-1]:
            self.points.append(self.points[0])
    
    def __str__(self):
        return f"PolygonROI(name='{self.name}', points={len(self.points)})"