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