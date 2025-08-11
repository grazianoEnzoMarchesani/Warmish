"""
Graphics items for ROI visualization in QGraphicsView.

This module contains QGraphicsItem-based classes for visually representing
ROIs (Regions of Interest) in a QGraphicsScene.
"""

from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsItem
from PySide6.QtGui import QPen, QBrush, QColor, QCursor
from PySide6.QtCore import Qt, QRectF, QPointF
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
        self.setAcceptHoverEvents(True)
        self._resizing = False
        self._resize_handle = None
        self._orig_rect = QRectF()
        self._orig_pos = QPointF()
        self._handle_size = 10  # px
        self.setPos(model.x, model.y)
        self._press_parent_pos = QPointF()
    
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

    def _handle_centers(self):
        r = self.rect()
        cx, cy, w, h = r.left(), r.top(), r.width(), r.height()
        return {
            "tl": QPointF(0, 0),
            "t":  QPointF(w/2, 0),
            "tr": QPointF(w, 0),
            "r":  QPointF(w, h/2),
            "br": QPointF(w, h),
            "b":  QPointF(w/2, h),
            "bl": QPointF(0, h),
            "l":  QPointF(0, h/2),
        }

    def _handle_at(self, pos: QPointF):
        s2 = self._handle_size / 2.0
        for key, c in self._handle_centers().items():
            if QRectF(c.x()-s2, c.y()-s2, self._handle_size, self._handle_size).contains(pos):
                return key
        return None

    def hoverMoveEvent(self, event):
        h = self._handle_at(event.pos())
        cursors = {
            "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
            "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
            "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
            "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
            None: Qt.ArrowCursor,
        }
        self.setCursor(QCursor(cursors[h]))
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            h = self._handle_at(event.pos())
            if h:  # start resize
                self._resizing = True
                self._resize_handle = h
                self._orig_rect = QRectF(self.rect())
                self._orig_pos = QPointF(self.pos())
                self._press_parent_pos = self.mapToParent(event.pos())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing and self._resize_handle:
            parent = self.parentItem()
            cur_parent = self.mapToParent(event.pos())
            dx = cur_parent.x() - self._press_parent_pos.x()
            dy = cur_parent.y() - self._press_parent_pos.y()

            min_w, min_h = 5.0, 5.0
            ox, oy = self._orig_pos.x(), self._orig_pos.y()
            ow, oh = self._orig_rect.width(), self._orig_rect.height()

            nx, ny, nw, nh = ox, oy, ow, oh

            # Orizzontale
            if self._resize_handle in ("tl", "l", "bl"):
                # spostando a sinistra: dx < 0 allarga, dx > 0 restringe
                max_dx_left = ow - min_w
                dx_clamped = max(-1e6, min(max_dx_left, dx))
                nx = ox + dx_clamped
                nw = max(min_w, ow - dx_clamped)
            elif self._resize_handle in ("tr", "r", "br"):
                nw = max(min_w, ow + dx)

            # Verticale
            if self._resize_handle in ("tl", "t", "tr"):
                max_dy_top = oh - min_h
                dy_clamped = max(-1e6, min(max_dy_top, dy))
                ny = oy + dy_clamped
                nh = max(min_h, oh - dy_clamped)
            elif self._resize_handle in ("bl", "b", "br"):
                nh = max(min_h, oh + dy)

            # Mantieni dentro l'immagine termica (parent)
            if parent:
                pb = parent.boundingRect()  # coordinate del parent
                nx = max(pb.left(), min(nx, pb.right() - nw))
                ny = max(pb.top(),  min(ny, pb.bottom() - nh))

            # Applica
            self.setPos(QPointF(nx, ny))
            self.setRect(QRectF(0, 0, nw, nh))

            # Sync modello live
            self.model.x = int(nx)
            self.model.y = int(ny)
            self.model.width = float(nw)
            self.model.height = float(nh)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing and event.button() == Qt.LeftButton:
            self._resizing = False
            self._resize_handle = None
            # Notifica ricalcolo
            self._notify_model_changed()
            event.accept()
            return
        # se era un semplice move, ricalcola qui
        if event.button() == Qt.LeftButton:
            self._notify_model_changed()
        super().mouseReleaseEvent(event)

    def _notify_model_changed(self):
        # aggiorna il modello e chiedi ricalcolo mirato
        self.model.x = int(self.pos().x())
        self.model.y = int(self.pos().y())
        self.model.width = float(self.rect().width())
        self.model.height = float(self.rect().height())
        view_list = self.scene().views()
        if view_list:
            view = view_list[0]
            if hasattr(view, "_main_window") and hasattr(view._main_window, "update_single_roi"):
                view._main_window.update_single_roi(self.model)