"""
Graphics items for ROI visualization in QGraphicsView.

This module contains QGraphicsItem-based classes for visually representing
ROIs (Regions of Interest) in a QGraphicsScene.
"""

from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsItem
from PySide6.QtGui import QPen, QBrush, QColor
from PySide6.QtCore import Qt, QRectF
from analysis.roi_models import RectROI


class RectROIItem(QGraphicsRectItem):
    """
    Graphical representation of a rectangular ROI for use in QGraphicsScene.
    
    This class provides visual representation and interactive capabilities
    for RectROI model objects within a QGraphicsView/QGraphicsScene framework.
    """
    
    def __init__(self, model: RectROI, parent=None):
        """
        Initialize the graphical ROI item.
        
        Args:
            model: RectROI instance containing the ROI data and coordinates
            parent: Optional parent QGraphicsItem
        """
        # Initialize the parent QGraphicsRectItem with the geometry from the model
        rect = QRectF(0, 0, model.width, model.height)
        super().__init__(rect, parent)
        
        # Store reference to the model
        self.model = model
        
        # Set interaction flags
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        
        # Set visual appearance
        self._setup_appearance()
        self.setZValue(10)  # ROI sempre sopra le immagini
        self.setPos(model.x, model.y)
    
    def _setup_appearance(self):
        """Set up the visual appearance of the ROI item."""
        # Create orange pen for the border (2px thickness)
        pen = QPen(QColor(255, 165, 0), 2)  # Orange color
        pen.setStyle(Qt.SolidLine)
        self.setPen(pen)
        
        # Create semi-transparent orange brush for fill
        brush_color = QColor(255, 165, 0, 40)  # Orange with ~15% opacity (40/255)
        brush = QBrush(brush_color)
        self.setBrush(brush)
    
    def itemChange(self, change, value):
        """
        Handle item changes, specifically position changes to sync with model.
        
        Args:
            change: Type of change (QGraphicsItem.GraphicsItemChange)
            value: New value associated with the change
            
        Returns:
            The processed value (usually unchanged)
        """
        if change == QGraphicsItem.ItemPositionHasChanged:
            # Update the model coordinates when the item is moved
            new_position = value
            self.model.x = int(new_position.x())
            self.model.y = int(new_position.y())
        
        # Call parent implementation
        return super().itemChange(change, value)
    
    def update_from_model(self):
        """
        Update the graphical representation from the model data.
        
        This method can be called to refresh the item when the model
        has been modified externally.
        """
        # Update the rectangle geometry
        self.setRect(QRectF(0, 0, self.model.width, self.model.height))
        self.setPos(self.model.x, self.model.y)
    
    def get_model_id(self):
        """
        Get the unique ID of the associated model.
        
        Returns:
            UUID: The unique identifier of the ROI model
        """
        return self.model.id
    
    def get_model_name(self):
        """
        Get the name of the associated model.
        
        Returns:
            str: The name of the ROI model
        """
        return self.model.name