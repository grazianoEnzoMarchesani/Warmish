"""
Graphics items for ROI visualization in QGraphicsView.

This module contains QGraphicsItem-based classes for visually representing
ROIs (Regions of Interest) in a QGraphicsScene.
"""

from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsItem, QGraphicsTextItem, QGraphicsEllipseItem, QGraphicsPolygonItem
from PySide6.QtGui import QPen, QBrush, QColor, QCursor, QPolygonF
from PySide6.QtCore import Qt, QRectF, QPointF
from analysis.roi_models import RectROI, SpotROI, PolygonROI


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
        self.setZValue(10)  # ROI always above images
        self.setAcceptHoverEvents(True)
        self._resizing = False
        self._resize_handle = None
        self._orig_rect = QRectF()
        self._orig_pos = QPointF()
        self._handle_size = 10  # pixels
        self.setPos(model.x, model.y)
        self._press_parent_pos = QPointF()
        
        # Enhanced visual feedback
        self._show_handles = False
        self._hovered_handle = None
        self._handle_items = {}  # Dictionary of visible handles
        
        # Initial color (from model if present)
        self._color = getattr(self.model, "color", QColor(255, 165, 0))
        self._apply_color(self._color)
        
        # Label: name + statistics; does not scale with zoom
        self.label = QGraphicsTextItem("", self)
        self.label.setDefaultTextColor(Qt.white)
        self.label.setZValue(self.zValue() + 1)
        self.label.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.refresh_label()
        self._update_label_pos()
    
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
    
    def _create_handle_items(self):
        """Create visible handles for resizing."""
        if self._handle_items:
            return  # Already created
        
        handle_centers = self._handle_centers()
        for handle_key, center in handle_centers.items():
            # Create a small rectangle for the handle
            handle_rect = QGraphicsRectItem(
                center.x() - self._handle_size/2, 
                center.y() - self._handle_size/2,
                self._handle_size, 
                self._handle_size, 
                self
            )
            
            # Handle style
            handle_pen = QPen(QColor(255, 255, 255), 1)
            handle_brush = QBrush(QColor(100, 150, 255, 180))  # Semi-transparent blue
            handle_rect.setPen(handle_pen)
            handle_rect.setBrush(handle_brush)
            handle_rect.setZValue(self.zValue() + 2)
            handle_rect.hide()  # Hidden by default
            
            self._handle_items[handle_key] = handle_rect
    
    def _update_handle_positions(self):
        """Update handle positions."""
        if not self._handle_items:
            return
            
        handle_centers = self._handle_centers()
        for handle_key, center in handle_centers.items():
            if handle_key in self._handle_items:
                handle_item = self._handle_items[handle_key]
                handle_item.setRect(
                    center.x() - self._handle_size/2, 
                    center.y() - self._handle_size/2,
                    self._handle_size, 
                    self._handle_size
                )
    
    def _show_hide_handles(self, show: bool):
        """Show or hide handles."""
        if show and not self._handle_items:
            self._create_handle_items()
        
        if self._handle_items:
            for handle_item in self._handle_items.values():
                handle_item.setVisible(show)
    
    def _highlight_handle(self, handle_key: str = None):
        """Highlight a specific handle or remove highlighting."""
        if not self._handle_items:
            return
            
        for key, handle_item in self._handle_items.items():
            if key == handle_key:
                # Highlight this handle
                highlight_brush = QBrush(QColor(255, 150, 0, 220))  # Bright orange
                handle_item.setBrush(highlight_brush)
            else:
                # Normal color
                normal_brush = QBrush(QColor(100, 150, 255, 180))
                handle_item.setBrush(normal_brush)

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
        self._update_label_pos()
        self._update_handle_positions()
    
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
        """
        Get the center positions of all resize handles.
        
        Returns:
            dict: Mapping of handle keys to QPointF positions
        """
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
        """
        Check if position is over a resize handle.
        
        Args:
            pos: Position to check in local coordinates
            
        Returns:
            str or None: Handle key if position is over a handle, None otherwise
        """
        s2 = self._handle_size / 2.0
        for key, c in self._handle_centers().items():
            if QRectF(c.x()-s2, c.y()-s2, self._handle_size, self._handle_size).contains(pos):
                return key
        return None

    def hoverEnterEvent(self, event):
        """Handle mouse enter event in ROI area."""
        self._show_handles = True
        self._show_hide_handles(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Handle mouse leave event from ROI area."""
        self._show_handles = False
        self._show_hide_handles(False)
        self._hovered_handle = None
        super().hoverLeaveEvent(event)

    def hoverMoveEvent(self, event):
        """Handle mouse move events within the ROI to show appropriate cursors."""
        h = self._handle_at(event.pos())
        cursors = {
            "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
            "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
            "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
            "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
            None: Qt.ArrowCursor,
        }
        self.setCursor(QCursor(cursors[h]))
        
        # Highlight the handle under the mouse
        if h != self._hovered_handle:
            self._hovered_handle = h
            self._highlight_handle(h)
        
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        """
        Handle mouse press events for resize and move operations.
        
        Args:
            event: Mouse press event containing button and position information
        """
        if event.button() == Qt.LeftButton:
            h = self._handle_at(event.pos())
            if h:  # Start resize operation
                self._resizing = True
                self._resize_handle = h
                self._orig_rect = QRectF(self.rect())
                self._orig_pos = QPointF(self.pos())
                self._press_parent_pos = self.mapToParent(event.pos())
                
                # Prepare geometry change to avoid trails
                self.prepareGeometryChange()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """
        Handle mouse move events for resizing operations.
        
        Args:
            event: Mouse move event containing position information
        """
        if self._resizing and self._resize_handle:
            # Prepare geometry change to avoid trails
            self.prepareGeometryChange()
            
            parent = self.parentItem()
            cur_parent = self.mapToParent(event.pos())
            dx = cur_parent.x() - self._press_parent_pos.x()
            dy = cur_parent.y() - self._press_parent_pos.y()

            min_w, min_h = 5.0, 5.0
            ox, oy = self._orig_pos.x(), self._orig_pos.y()
            ow, oh = self._orig_rect.width(), self._orig_rect.height()

            nx, ny, nw, nh = ox, oy, ow, oh

            # Handle horizontal resizing
            if self._resize_handle in ("tl", "l", "bl"):
                # Moving left: negative dx expands, positive dx shrinks
                max_dx_left = ow - min_w
                dx_clamped = max(-1e6, min(max_dx_left, dx))
                nx = ox + dx_clamped
                nw = max(min_w, ow - dx_clamped)
            elif self._resize_handle in ("tr", "r", "br"):
                nw = max(min_w, ow + dx)

            # Handle vertical resizing
            if self._resize_handle in ("tl", "t", "tr"):
                max_dy_top = oh - min_h
                dy_clamped = max(-1e6, min(max_dy_top, dy))
                ny = oy + dy_clamped
                nh = max(min_h, oh - dy_clamped)
            elif self._resize_handle in ("bl", "b", "br"):
                nh = max(min_h, oh + dy)

            # Keep within thermal image bounds (parent)
            if parent:
                pb = parent.boundingRect()  # Parent coordinates
                nx = max(pb.left(), min(nx, pb.right() - nw))
                ny = max(pb.top(),  min(ny, pb.bottom() - nh))

            # Apply changes
            self.setPos(QPointF(nx, ny))
            self.setRect(QRectF(0, 0, nw, nh))
            self._update_label_pos()
            self._update_handle_positions()

            # Sync model with live changes
            self.model.x = int(nx)
            self.model.y = int(ny)
            self.model.width = float(nw)
            self.model.height = float(nh)
            
            # Force update to avoid trails
            self.update()
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """
        Handle mouse release events.
        
        Args:
            event: Mouse release event containing button information
        """
        if self._resizing and event.button() == Qt.LeftButton:
            self._resizing = False
            self._resize_handle = None
            # Notify recalculation
            self._notify_model_changed()
            # Final update to clean any artifacts
            self.update()
            event.accept()
            return
        # If it was a simple move, recalculate here
        if event.button() == Qt.LeftButton:
            self._notify_model_changed()
        super().mouseReleaseEvent(event)

    def _notify_model_changed(self):
        """Update the model and request targeted recalculation."""
        self.model.x = int(self.pos().x())
        self.model.y = int(self.pos().y())
        self.model.width = float(self.rect().width())
        self.model.height = float(self.rect().height())
        
        # Use the new signal-based approach
        view_list = self.scene().views()
        if view_list:
            view = view_list[0]
            if hasattr(view, "notify_roi_modified"):
                view.notify_roi_modified(self.model)
    
    def _apply_color(self, color: QColor):
        """
        Apply color to the ROI item.
        
        Args:
            color: QColor to apply to the ROI
        """
        pen = QPen(color, 2)
        pen.setStyle(Qt.SolidLine)
        self.setPen(pen)
        fill = QColor(color)
        fill.setAlpha(40)
        self.setBrush(QBrush(fill))
    
    def set_color(self, color: QColor):
        """
        Set the color of the ROI item.
        
        Args:
            color: New color for the ROI
        """
        self._color = color
        setattr(self.model, "color", color)
        self._apply_color(color)
    
    def refresh_label(self):
        """Refresh the label text with current statistics."""
        m = self.model
        
        # Get settings from ImageGraphicsView instead of MainWindow
        settings = {
            "name": True, "emissivity": True, "min": True, "max": True, "avg": True, "median": False
        }
        views = self.scene().views()
        if views:
            view = views[0]
            if hasattr(view, "get_roi_label_settings"):
                settings = view.get_roi_label_settings()

        def fmt(v): return f"{v:.2f}" if (v is not None) else "N/A"
        parts1 = []
        if settings.get("name", True): parts1.append(m.name)
        if settings.get("emissivity", True): parts1.append(f"ε {getattr(m, 'emissivity', 0.95):.3f}")
        line1 = " | ".join(parts1)

        parts2 = []
        if settings.get("min", True): parts2.append(f"min {fmt(getattr(m, 'temp_min', None))}")
        if settings.get("max", True): parts2.append(f"max {fmt(getattr(m, 'temp_max', None))}")
        if settings.get("avg", True): parts2.append(f"mean {fmt(getattr(m, 'temp_mean', None))}")
        if settings.get("median", False): parts2.append(f"median {fmt(getattr(m, 'temp_median', None))}")
        line2 = " | ".join(parts2)

        text = line1 if line2 == "" else f"{line1}\n{line2}"
        self.label.setPlainText(text)
        self._update_label_pos()
    
    def _update_label_pos(self):
        """Update label position to top-left corner of rectangle with small offset."""
        self.label.setPos(self.rect().left() + 2, self.rect().top() - self.label.boundingRect().height() - 2)


class SpotROIItem(QGraphicsEllipseItem):
    """
    Graphical representation of a spot (circular) ROI for use in QGraphicsScene.
    
    This class provides visual representation and interactive capabilities
    for SpotROI model objects within a QGraphicsView/QGraphicsScene framework.
    """
    
    def __init__(self, model: SpotROI, parent=None):
        """
        Initialize the graphical spot ROI item.
        
        Args:
            model: SpotROI instance containing the ROI data and coordinates
            parent: Optional parent QGraphicsItem
        """
        # Initialize the parent QGraphicsEllipseItem with the geometry from the model
        diameter = model.radius * 2
        rect = QRectF(-model.radius, -model.radius, diameter, diameter)
        super().__init__(rect, parent)
        
        # Store reference to the model
        self.model = model
        
        # Set interaction flags
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        
        # Set visual appearance
        self._setup_appearance()
        self.setZValue(10)  # ROI always above images
        self.setAcceptHoverEvents(True)
        self._resizing = False
        self._handle_size = 8  # pixels
        self.setPos(model.x, model.y)
        self._press_parent_pos = QPointF()
        
        # Enhanced visual feedback
        self._show_handles = False
        self._hovered_handle = None
        self._handle_items = {}  # Dictionary of visible handles
        
        # Initial color (from model if present)
        self._color = getattr(self.model, "color", QColor(255, 165, 0))
        self._apply_color(self._color)
        
        # Label: name + statistics; does not scale with zoom
        self.label = QGraphicsTextItem("", self)
        self.label.setDefaultTextColor(Qt.white)
        self.label.setZValue(self.zValue() + 1)
        self.label.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.refresh_label()
        self._update_label_pos()
    
    def _setup_appearance(self):
        """Set up the visual appearance of the spot ROI item."""
        # Create orange pen for the border (2px thickness)
        pen = QPen(QColor(255, 165, 0), 2)  # Orange color
        pen.setStyle(Qt.SolidLine)
        self.setPen(pen)
        
        # Create semi-transparent orange brush for fill
        brush_color = QColor(255, 165, 0, 40)  # Orange with ~15% opacity (40/255)
        brush = QBrush(brush_color)
        self.setBrush(brush)
    
    def _create_handle_items(self):
        """Create visible handles for resizing."""
        if self._handle_items:
            return  # Already created
        
        handle_positions = self._get_resize_handles()
        for handle_key, center in handle_positions.items():
            # Create a small circle for the handle
            handle_ellipse = QGraphicsEllipseItem(
                center.x() - self._handle_size/2, 
                center.y() - self._handle_size/2,
                self._handle_size, 
                self._handle_size, 
                self
            )
            
            # Handle style
            handle_pen = QPen(QColor(255, 255, 255), 1)
            handle_brush = QBrush(QColor(100, 150, 255, 180))  # Semi-transparent blue
            handle_ellipse.setPen(handle_pen)
            handle_ellipse.setBrush(handle_brush)
            handle_ellipse.setZValue(self.zValue() + 2)
            handle_ellipse.hide()  # Hidden by default
            
            self._handle_items[handle_key] = handle_ellipse
    
    def _update_handle_positions(self):
        """Update handle positions."""
        if not self._handle_items:
            return
            
        handle_positions = self._get_resize_handles()
        for handle_key, center in handle_positions.items():
            if handle_key in self._handle_items:
                handle_item = self._handle_items[handle_key]
                handle_item.setRect(
                    center.x() - self._handle_size/2, 
                    center.y() - self._handle_size/2,
                    self._handle_size, 
                    self._handle_size
                )
    
    def _show_hide_handles(self, show: bool):
        """Show or hide handles."""
        if show and not self._handle_items:
            self._create_handle_items()
        
        if self._handle_items:
            for handle_item in self._handle_items.values():
                handle_item.setVisible(show)
    
    def _highlight_handle(self, handle_key: str = None):
        """Highlight a specific handle or remove highlighting."""
        if not self._handle_items:
            return
            
        for key, handle_item in self._handle_items.items():
            if key == handle_key:
                # Highlight this handle
                highlight_brush = QBrush(QColor(255, 150, 0, 220))  # Bright orange
                handle_item.setBrush(highlight_brush)
            else:
                # Normal color
                normal_brush = QBrush(QColor(100, 150, 255, 180))
                handle_item.setBrush(normal_brush)

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
            self.model.x = float(new_position.x())
            self.model.y = float(new_position.y())
        
        # Call parent implementation
        return super().itemChange(change, value)
    
    def update_from_model(self):
        """
        Update the graphical representation from the model data.
        
        This method can be called to refresh the item when the model
        has been modified externally.
        """
        # Update the circle geometry
        diameter = self.model.radius * 2
        self.setRect(QRectF(-self.model.radius, -self.model.radius, diameter, diameter))
        self.setPos(self.model.x, self.model.y)
        self._update_label_pos()
        self._update_handle_positions()
    
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

    def _get_resize_handles(self):
        """
        Get the positions of resize handles for the circle.
        
        Returns:
            dict: Mapping of handle keys to QPointF positions
        """
        r = self.model.radius
        return {
            "right": QPointF(r, 0),
            "bottom": QPointF(0, r),
            "left": QPointF(-r, 0),
            "top": QPointF(0, -r),
        }

    def _handle_at(self, pos: QPointF):
        """
        Check if position is near a resize handle.
        
        Args:
            pos: Position to check in local coordinates
            
        Returns:
            str or None: Handle key if position is over a handle, None otherwise
        """
        s2 = self._handle_size / 2.0
        for key, handle_pos in self._get_resize_handles().items():
            if QRectF(handle_pos.x()-s2, handle_pos.y()-s2, self._handle_size, self._handle_size).contains(pos):
                return key
        return None

    def hoverEnterEvent(self, event):
        """Handle mouse enter event in ROI area."""
        self._show_handles = True
        self._show_hide_handles(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Handle mouse leave event from ROI area."""
        self._show_handles = False
        self._show_hide_handles(False)
        self._hovered_handle = None
        super().hoverLeaveEvent(event)

    def hoverMoveEvent(self, event):
        """Handle hover events to show appropriate cursor for resize handles."""
        h = self._handle_at(event.pos())
        cursors = {
            "right": Qt.SizeHorCursor,
            "left": Qt.SizeHorCursor,
            "top": Qt.SizeVerCursor,
            "bottom": Qt.SizeVerCursor,
            None: Qt.ArrowCursor,
        }
        self.setCursor(QCursor(cursors[h]))
        
        # Highlight the handle under the mouse
        if h != self._hovered_handle:
            self._hovered_handle = h
            self._highlight_handle(h)
        
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        """
        Handle mouse press events for resize and move operations.
        
        Args:
            event: Mouse press event containing button and position information
        """
        if event.button() == Qt.LeftButton:
            h = self._handle_at(event.pos())
            if h:  # Start resize operation
                self._resizing = True
                self._resize_handle = h
                self._orig_radius = self.model.radius
                self._press_parent_pos = self.mapToParent(event.pos())
                
                # Prepare geometry change to avoid trails
                self.prepareGeometryChange()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """
        Handle mouse move events for resizing the circle.
        
        Args:
            event: Mouse move event containing position information
        """
        if self._resizing and self._resize_handle:
            # Prepare geometry change to avoid trails
            self.prepareGeometryChange()
            
            cur_parent = self.mapToParent(event.pos())
            dx = cur_parent.x() - self._press_parent_pos.x()
            dy = cur_parent.y() - self._press_parent_pos.y()

            min_radius = 2.0
            new_radius = self._orig_radius

            # Calculate new radius based on handle direction and movement
            if self._resize_handle == "right":
                # Dragging right increases, left decreases
                new_radius = max(min_radius, self._orig_radius + dx)
            elif self._resize_handle == "left":
                # Dragging left increases, right decreases
                new_radius = max(min_radius, self._orig_radius - dx)
            elif self._resize_handle == "bottom":
                # Dragging down increases, up decreases
                new_radius = max(min_radius, self._orig_radius + dy)
            elif self._resize_handle == "top":
                # Dragging up increases, down decreases
                new_radius = max(min_radius, self._orig_radius - dy)

            # Update the circle
            diameter = new_radius * 2
            self.setRect(QRectF(-new_radius, -new_radius, diameter, diameter))
            self._update_label_pos()
            self._update_handle_positions()

            # Sync model
            self.model.radius = float(new_radius)
            
            # Force update to avoid trails
            self.update()
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """
        Handle mouse release events.
        
        Args:
            event: Mouse release event containing button information
        """
        if self._resizing and event.button() == Qt.LeftButton:
            self._resizing = False
            self._resize_handle = None
            # Notify model changed
            self._notify_model_changed()
            # Final update to clean any artifacts
            self.update()
            event.accept()
            return
        # If it was a simple move, recalculate here
        if event.button() == Qt.LeftButton:
            self._notify_model_changed()
        super().mouseReleaseEvent(event)

    def _notify_model_changed(self):
        """Notify that the model has changed and needs recalculation."""
        # Update model position
        self.model.x = float(self.pos().x())
        self.model.y = float(self.pos().y())
        
        # Use the new signal-based approach
        view_list = self.scene().views()
        if view_list:
            view = view_list[0]
            if hasattr(view, "notify_roi_modified"):
                view.notify_roi_modified(self.model)
    
    def _apply_color(self, color: QColor):
        """
        Apply color to the spot ROI.
        
        Args:
            color: QColor to apply to the ROI
        """
        pen = QPen(color, 2)
        pen.setStyle(Qt.SolidLine)
        self.setPen(pen)
        fill = QColor(color)
        fill.setAlpha(40)
        self.setBrush(QBrush(fill))
    
    def set_color(self, color: QColor):
        """
        Set the color of the spot ROI.
        
        Args:
            color: New color for the ROI
        """
        self._color = color
        setattr(self.model, "color", color)
        self._apply_color(color)
    
    def refresh_label(self):
        """Refresh the label text with current statistics."""
        m = self.model
        
        # Get settings from ImageGraphicsView instead of MainWindow
        settings = {
            "name": True, "emissivity": True, "min": True, "max": True, "avg": True, "median": False
        }
        views = self.scene().views()
        if views:
            view = views[0]
            if hasattr(view, "get_roi_label_settings"):
                settings = view.get_roi_label_settings()

        def fmt(v): return f"{v:.2f}" if (v is not None) else "N/A"
        parts1 = []
        if settings.get("name", True): parts1.append(m.name)
        if settings.get("emissivity", True): parts1.append(f"ε {getattr(m, 'emissivity', 0.95):.3f}")
        line1 = " | ".join(parts1)

        parts2 = []
        if settings.get("min", True): parts2.append(f"min {fmt(getattr(m, 'temp_min', None))}")
        if settings.get("max", True): parts2.append(f"max {fmt(getattr(m, 'temp_max', None))}")
        if settings.get("avg", True): parts2.append(f"mean {fmt(getattr(m, 'temp_mean', None))}")
        if settings.get("median", False): parts2.append(f"median {fmt(getattr(m, 'temp_median', None))}")
        line2 = " | ".join(parts2)

        text = line1 if line2 == "" else f"{line1}\n{line2}"
        self.label.setPlainText(text)
        self._update_label_pos()
    
    def _update_label_pos(self):
        """Update the label position relative to the circle."""
        # Position label above the circle with small offset, similar to RectROI approach
        rect = self.rect()
        label_x = rect.left() + 2  # Small offset from left edge
        label_y = rect.top() - self.label.boundingRect().height() - 2
        self.label.setPos(label_x, label_y)


class PolygonROIItem(QGraphicsPolygonItem):
    """
    Graphical representation of a polygon ROI for use in QGraphicsScene.
    
    This class provides visual representation and interactive capabilities
    for PolygonROI model objects within a QGraphicsView/QGraphicsScene framework.
    """
    
    def __init__(self, model: PolygonROI, parent=None):
        """
        Initialize the graphical polygon ROI item.
        
        Args:
            model: PolygonROI instance containing the ROI data and coordinates
            parent: Optional parent QGraphicsItem
        """
        
        # Create QPolygonF from model points
        qt_polygon = QPolygonF()
        for x, y in model.points:
            qt_polygon.append(QPointF(x, y))
        
        super().__init__(qt_polygon, parent)
        
        # Store reference to the model
        self.model = model
        
        # Set interaction flags
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        
        # Set visual appearance
        self._setup_appearance()
        self.setZValue(10)  # ROI always above images
        self.setAcceptHoverEvents(True)
        
        # Editing state
        self._editing_vertices = False
        self._selected_vertex = -1
        self._vertex_radius = 5  # Radius of vertex circles
        
        # Enhanced visual feedback
        self._show_vertices = False
        self._hovered_vertex = -1
        self._vertex_items = []  # List of visible vertex handles
        
        # Initial color (from model if present)
        self._color = getattr(self.model, "color", QColor(255, 165, 0))
        self._apply_color(self._color)
        
        # Label: name + statistics; does not scale with zoom
        self.label = QGraphicsTextItem("", self)
        self.label.setDefaultTextColor(Qt.white)
        self.label.setZValue(self.zValue() + 1)
        self.label.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.refresh_label()
        self._update_label_pos()
    
    def _setup_appearance(self):
        """Set up the visual appearance of the polygon ROI item."""
        # Create orange pen for the border (2px thickness)
        pen = QPen(QColor(255, 165, 0), 2)  # Orange color
        pen.setStyle(Qt.SolidLine)
        self.setPen(pen)
        
        # Create semi-transparent orange brush for fill
        brush_color = QColor(255, 165, 0, 40)  # Orange with ~15% opacity (40/255)
        brush = QBrush(brush_color)
        self.setBrush(brush)
    
    def _create_vertex_items(self):
        """Create visible handles for vertices."""
        # Remove old handles if they exist
        for vertex_item in self._vertex_items:
            if vertex_item.scene():
                vertex_item.scene().removeItem(vertex_item)
        self._vertex_items.clear()
        
        polygon = self.polygon()
        for i in range(polygon.size()):
            vertex = polygon[i]
            # Create a small circle for the vertex
            vertex_ellipse = QGraphicsEllipseItem(
                vertex.x() - self._vertex_radius, 
                vertex.y() - self._vertex_radius,
                self._vertex_radius * 2, 
                self._vertex_radius * 2, 
                self
            )
            
            # Vertex style
            vertex_pen = QPen(QColor(255, 255, 255), 1)
            vertex_brush = QBrush(QColor(100, 150, 255, 180))  # Semi-transparent blue
            vertex_ellipse.setPen(vertex_pen)
            vertex_ellipse.setBrush(vertex_brush)
            vertex_ellipse.setZValue(self.zValue() + 2)
            vertex_ellipse.hide()  # Hidden by default
            
            self._vertex_items.append(vertex_ellipse)
    
    def _update_vertex_positions(self):
        """Update vertex positions."""
        polygon = self.polygon()
        for i, vertex_item in enumerate(self._vertex_items):
            if i < polygon.size():
                vertex = polygon[i]
                vertex_item.setRect(
                    vertex.x() - self._vertex_radius, 
                    vertex.y() - self._vertex_radius,
                    self._vertex_radius * 2, 
                    self._vertex_radius * 2
                )
    
    def _show_hide_vertices(self, show: bool):
        """Show or hide vertices."""
        if show:
            self._create_vertex_items()
        
        for vertex_item in self._vertex_items:
            vertex_item.setVisible(show)
    
    def _highlight_vertex(self, vertex_idx: int = -1):
        """Highlight a specific vertex or remove highlighting."""
        for i, vertex_item in enumerate(self._vertex_items):
            if i == vertex_idx:
                # Highlight this vertex
                highlight_brush = QBrush(QColor(255, 150, 0, 220))  # Bright orange
                vertex_item.setBrush(highlight_brush)
            else:
                # Normal color
                normal_brush = QBrush(QColor(100, 150, 255, 180))
                vertex_item.setBrush(normal_brush)

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
            offset = value
            # Update all points in the model
            original_polygon = self.polygon()
            for i, point in enumerate(self.model.points):
                new_point = original_polygon[i] + offset
                self.model.points[i] = (new_point.x(), new_point.y())
            
            # Notify about the change using the new signal-based approach
            view_list = self.scene().views()
            if view_list:
                view = view_list[0]
                if hasattr(view, "notify_roi_modified"):
                    view.notify_roi_modified(self.model)
        
        return super().itemChange(change, value)
    
    def update_from_model(self):
        """Update the graphical representation from the model data."""
        
        # Update the polygon geometry
        qt_polygon = QPolygonF()
        for x, y in self.model.points:
            qt_polygon.append(QPointF(x, y))
        self.setPolygon(qt_polygon)
        self._update_label_pos()
        self._update_vertex_positions()
    
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

    def _get_vertex_at(self, pos: QPointF):
        """
        Check if position is near a vertex.
        
        Args:
            pos: Position to check in local coordinates
            
        Returns:
            int: Vertex index if position is near a vertex, -1 otherwise
        """
        polygon = self.polygon()
        for i in range(polygon.size()):
            vertex = polygon[i]
            distance = ((pos.x() - vertex.x()) ** 2 + (pos.y() - vertex.y()) ** 2) ** 0.5
            if distance <= self._vertex_radius:
                return i
        return -1

    def hoverEnterEvent(self, event):
        """Handle mouse enter event in ROI area."""
        self._show_vertices = True
        self._show_hide_vertices(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Handle mouse leave event from ROI area."""
        self._show_vertices = False
        self._show_hide_vertices(False)
        self._hovered_vertex = -1
        super().hoverLeaveEvent(event)

    def hoverMoveEvent(self, event):
        """Handle hover events to show appropriate cursor for vertices."""
        vertex_idx = self._get_vertex_at(event.pos())
        if vertex_idx >= 0:
            self.setCursor(QCursor(Qt.SizeAllCursor))
        else:
            self.setCursor(QCursor(Qt.ArrowCursor))
        
        # Highlight the vertex under the mouse
        if vertex_idx != self._hovered_vertex:
            self._hovered_vertex = vertex_idx
            self._highlight_vertex(vertex_idx)
        
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        """
        Handle mouse press events for vertex editing and move operations.
        
        Args:
            event: Mouse press event containing button and position information
        """
        if event.button() == Qt.LeftButton:
            vertex_idx = self._get_vertex_at(event.pos())
            if vertex_idx >= 0:
                # Start vertex editing
                self._editing_vertices = True
                self._selected_vertex = vertex_idx
                
                # Prepare geometry change to avoid trails
                self.prepareGeometryChange()
                event.accept()
                return
        
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """
        Handle mouse move events for vertex editing.
        
        Args:
            event: Mouse move event containing position information
        """
        if self._editing_vertices and self._selected_vertex >= 0:
            # Prepare geometry change to avoid trails
            self.prepareGeometryChange()
            
            # Update the vertex position
            polygon = self.polygon()
            polygon[self._selected_vertex] = event.pos()
            self.setPolygon(polygon)
            
            # Update model
            self.model.points[self._selected_vertex] = (event.pos().x(), event.pos().y())
            self._update_label_pos()
            self._update_vertex_positions()
            
            # Force update to avoid trails
            self.update()
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """
        Handle mouse release events.
        
        Args:
            event: Mouse release event containing button information
        """
        if self._editing_vertices and event.button() == Qt.LeftButton:
            self._editing_vertices = False
            self._selected_vertex = -1
            # Notify model changed
            self._notify_model_changed()
            # Final update to clean any artifacts
            self.update()
            event.accept()
            return
        
        # If it was a simple move, recalculate here
        if event.button() == Qt.LeftButton:
            self._notify_model_changed()
        super().mouseReleaseEvent(event)

    def _notify_model_changed(self):
        """Notify that the model has changed and needs recalculation."""
        # Notify main window for recalculation
        view_list = self.scene().views()
        if view_list:
            view = view_list[0]
            if hasattr(view, "notify_roi_modified"):
                view.notify_roi_modified(self.model)
    
    def _apply_color(self, color: QColor):
        """
        Apply color to the polygon ROI.
        
        Args:
            color: QColor to apply to the ROI
        """
        pen = QPen(color, 2)
        pen.setStyle(Qt.SolidLine)
        self.setPen(pen)
        fill = QColor(color)
        fill.setAlpha(40)
        self.setBrush(QBrush(fill))
    
    def set_color(self, color: QColor):
        """
        Set the color of the polygon ROI.
        
        Args:
            color: New color for the ROI
        """
        self._color = color
        setattr(self.model, "color", color)
        self._apply_color(color)
    
    def refresh_label(self):
        """Refresh the label text with current statistics."""
        m = self.model
        
        # Get settings from ImageGraphicsView instead of MainWindow
        settings = {
            "name": True, "emissivity": True, "min": True, "max": True, "avg": True, "median": False
        }
        views = self.scene().views()
        if views:
            view = views[0]
            if hasattr(view, "get_roi_label_settings"):
                settings = view.get_roi_label_settings()

        def fmt(v): return f"{v:.2f}" if (v is not None) else "N/A"
        parts1 = []
        if settings.get("name", True): parts1.append(m.name)
        if settings.get("emissivity", True): parts1.append(f"ε {getattr(m, 'emissivity', 0.95):.3f}")
        line1 = " | ".join(parts1)

        parts2 = []
        if settings.get("min", True): parts2.append(f"min {fmt(getattr(m, 'temp_min', None))}")
        if settings.get("max", True): parts2.append(f"max {fmt(getattr(m, 'temp_max', None))}")
        if settings.get("avg", True): parts2.append(f"mean {fmt(getattr(m, 'temp_mean', None))}")
        if settings.get("median", False): parts2.append(f"median {fmt(getattr(m, 'temp_median', None))}")
        line2 = " | ".join(parts2)

        text = line1 if line2 == "" else f"{line1}\n{line2}"
        self.label.setPlainText(text)
        self._update_label_pos()
    
    def _update_label_pos(self):
        """Update the label position relative to the polygon."""
        # Position label above the polygon's bounding box, similar to RectROI approach
        bbox = self.polygon().boundingRect()
        label_x = bbox.left() + 2  # Small offset from left edge
        label_y = bbox.top() - self.label.boundingRect().height() - 2
        self.label.setPos(label_x, label_y)