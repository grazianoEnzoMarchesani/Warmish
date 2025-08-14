# analysis/roi_models.py
import uuid
import math
from typing import Optional




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