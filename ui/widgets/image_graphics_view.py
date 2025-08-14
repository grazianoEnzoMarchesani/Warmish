from typing import Optional
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QWidget, QStyleOptionGraphicsItem, QGraphicsPolygonItem
from PySide6.QtCore import Qt, QPointF, Signal, QRectF
from PySide6.QtGui import QPixmap, QPainter, QWheelEvent, QMouseEvent, QTransform, QPen, QBrush, QColor, QPolygonF


class BlendablePixmapItem(QGraphicsPixmapItem):
    """Custom QGraphicsPixmapItem that supports blend modes.
    
    Extends the standard QGraphicsPixmapItem to allow different composition
    modes when rendering, enabling visual effects like overlay blending.
    """
    
    def __init__(self, parent=None):
        """Initialize the blendable pixmap item.
        
        Args:
            parent: Parent graphics item, defaults to None.
        """
        super().__init__(parent)
        self._blend_mode = QPainter.CompositionMode_SourceOver
        
    def set_blend_mode(self, mode: QPainter.CompositionMode):
        """Set the blend mode for this item.
        
        Args:
            mode (QPainter.CompositionMode): The composition mode to use for blending.
        """
        self._blend_mode = mode
        self.update()
    
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        """Override the paint method to apply the custom blend mode.
        
        Args:
            painter (QPainter): The painter to use for rendering.
            option (QStyleOptionGraphicsItem): Style options for the item.
            widget: The widget being painted on, defaults to None.
        """
        if self.pixmap().isNull():
            return
            
        # Store current state to restore after custom blending
        old_composition_mode = painter.compositionMode()
        
        # Apply the custom blend mode
        painter.setCompositionMode(self._blend_mode)
        
        # Call parent paint with custom mode
        super().paint(painter, option, widget)
        
        # Restore original painter state
        painter.setCompositionMode(old_composition_mode)


class ImageGraphicsView(QGraphicsView):
    """Custom graphics view for displaying and managing thermal images.
    
    Provides functionality for viewing thermal images with zoom, pan, and overlay
    capabilities. Supports drawing different types of ROI (Region of Interest)
    including rectangles, spots, and polygons.
    
    Signals:
        mouse_moved_on_thermal (QPointF): Emitted when mouse moves over thermal image.
        view_transformed (float, QPointF, tuple): Emitted when view changes (zoom, pan).
        rect_roi_drawn (QRectF): Emitted when a rectangular ROI is completed.
        spot_roi_drawn (QPointF, float): Emitted when a spot ROI is created.
        polygon_roi_drawn (list): Emitted when a polygon ROI is completed.
        drawing_tool_deactivation_requested (): Emitted when drawing tools should be deactivated.
        roi_modified (object): Emitted when an existing ROI is moved or resized.
    """
    
    # Signals for thermal image interaction
    mouse_moved_on_thermal = Signal(QPointF)
    view_transformed = Signal(float, QPointF, tuple)  # zoom_factor, pan_offset, pixmap_size
    
    # ROI creation signals - replace direct MainWindow coupling
    rect_roi_drawn = Signal(QRectF)  # thermal image coordinates
    spot_roi_drawn = Signal(QPointF, float)  # center point, radius in thermal pixels
    polygon_roi_drawn = Signal(list)  # list of (x, y) points in thermal coordinates
    drawing_tool_deactivation_requested = Signal()
    
    # ROI modification signal - emitted when existing ROI is changed
    roi_modified = Signal(object)  # ROI model that was modified

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize the image graphics view.
        
        Args:
            parent (QWidget, optional): Parent widget, defaults to None.
        """
        super().__init__(parent)
        
        # Configure view settings for optimal image display
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # Initialize scene
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        
        # Graphics items for images (order matters: visible below, thermal above)
        self._thermal_item = BlendablePixmapItem()
        self._visible_item = QGraphicsPixmapItem()
        
        self._scene.addItem(self._visible_item)
        self._scene.addItem(self._thermal_item)
        
        # Overlay configuration
        self._overlay_mode = False
        self._overlay_alpha = 0.5
        self._overlay_scale = 1.0
        self._overlay_offset = QPointF(0, 0)
        self._blend_mode = QPainter.CompositionMode_SourceOver
        
        # Zoom and pan state
        self._zoom_factor = 1.0
        self._min_zoom = 0.1
        self._max_zoom = 10.0
        self._pan_active = False
        
        # Prevent synchronization loops between multiple views
        self._is_sync_source = True
        
        # Enable mouse tracking for temperature tooltips
        self.setMouseTracking(True)
        
        # ROI drawing state - decoupled from MainWindow
        self._current_drawing_tool = None  # "rect", "spot", "polygon", or None
        self._roi_drawing = False
        self._roi_start_pos = None
        self._temp_roi_item = None
        self._allow_roi_drawing = True
        
        # Polygon drawing state
        self._polygon_drawing = False
        self._current_polygon_points = []
        self._temp_polygon_item = None
        
        # Enable keyboard input for polygon completion shortcuts
        self.setFocusPolicy(Qt.StrongFocus)

        # ROI label settings - will be updated by MainWindow
        self._roi_label_settings = {
            "name": True,
            "emissivity": True,
            "min": True,
            "max": True,
            "avg": True,
            "median": False,
        }

    def set_allow_roi_drawing(self, allowed: bool):
        """Enable or disable ROI drawing capability.
        
        Args:
            allowed (bool): Whether to allow ROI drawing.
        """
        self._allow_roi_drawing = allowed

    def set_drawing_tool(self, tool: Optional[str]):
        """Set the current drawing tool.
        
        Args:
            tool (str, optional): The drawing tool to activate ("rect", "spot", "polygon") 
                                or None to deactivate drawing.
        """
        self._current_drawing_tool = tool
        
        # Cancel any ongoing polygon drawing when switching tools
        if tool != "polygon" and self._polygon_drawing:
            self._cancel_polygon_drawing()

    def get_drawing_tool(self) -> Optional[str]:
        """Get the current drawing tool.
        
        Returns:
            str or None: The current drawing tool or None if no tool is active.
        """
        return self._current_drawing_tool

    def set_thermal_pixmap(self, pixmap: QPixmap):
        """Set the thermal image pixmap.
        
        Args:
            pixmap (QPixmap): The thermal image to display.
        """
        if pixmap is None or pixmap.isNull():
            self._thermal_item.setPixmap(QPixmap())
            return
            
        self._thermal_item.setPixmap(pixmap)
        
        # Auto-fit when setting new image, unless in overlay mode
        if not self._overlay_mode:
            self._fit_thermal_in_view()
        else:
            self._update_overlay_positioning()
    
    def set_visible_pixmap(self, pixmap: QPixmap):
        """Set the visible light image pixmap.
        
        Args:
            pixmap (QPixmap): The visible light image to display.
        """
        if pixmap is None or pixmap.isNull():
            self._visible_item.setPixmap(QPixmap())
            self._visible_item.setVisible(False)
            return
            
        self._visible_item.setPixmap(pixmap)
        # Don't automatically set visible here, update_overlay handles it
        
        # If in overlay mode, update positioning
        if self._overlay_mode:
            self._update_overlay_positioning()

    def update_overlay(self, visible: bool, alpha: float = 0.5, scale: float = 1.0, 
                      offset: QPointF = QPointF(0, 0), blend_mode: QPainter.CompositionMode = None):
        """Update overlay settings for image composition.
        
        Args:
            visible (bool): Whether overlay mode is enabled.
            alpha (float): Opacity of the thermal overlay (0.0-1.0).
            scale (float): Scale factor for the thermal image relative to visible (0.1-5.0).
            offset (QPointF): Pixel offset for thermal image positioning.
            blend_mode (QPainter.CompositionMode, optional): Composition mode for blending.
        """
        self._overlay_mode = visible
        self._overlay_alpha = max(0.0, min(1.0, alpha))
        self._overlay_scale = max(0.1, min(5.0, scale))
        self._overlay_offset = offset
        
        if blend_mode is not None:
            self._blend_mode = blend_mode
            # Apply blend mode to thermal item
            self._thermal_item.set_blend_mode(blend_mode)
        
        if self._overlay_mode:
            # In overlay mode, show both images if available
            self._visible_item.setVisible(not self._visible_item.pixmap().isNull())
            self._thermal_item.setVisible(not self._thermal_item.pixmap().isNull())
            self._thermal_item.setOpacity(self._overlay_alpha)
            
            # Ensure correct Z-order (visible below, thermal above)
            self._visible_item.setZValue(0)
            self._thermal_item.setZValue(1)
            
            self._update_overlay_positioning()
        else:
            # In normal mode, show only thermal image
            self._visible_item.setVisible(False)
            self._thermal_item.setVisible(not self._thermal_item.pixmap().isNull())
            self._thermal_item.setOpacity(1.0)
            # Restore normal blend mode when not in overlay
            self._thermal_item.set_blend_mode(QPainter.CompositionMode_SourceOver)
            self._fit_thermal_in_view()

    def _fit_thermal_in_view(self):
        """Fit thermal image to view when not in overlay mode."""
        if self._thermal_item.pixmap().isNull():
            return
        
        # Reset item transformation
        self._thermal_item.setTransform(QTransform())
        
        # Center thermal image in scene
        thermal_rect = self._thermal_item.boundingRect()
        self._thermal_item.setPos(-thermal_rect.width()/2, -thermal_rect.height()/2)
        
        # Reset view and fit image
        self.resetTransform()
        self.fitInView(self._thermal_item, Qt.KeepAspectRatio)
        self._zoom_factor = self.transform().m11()
    
    def _update_overlay_positioning(self):
        """Update image positioning in overlay mode."""
        if not self._overlay_mode:
            return
        
        # Reset transformations
        self._visible_item.setTransform(QTransform())
        self._thermal_item.setTransform(QTransform())
        
        # Position visible image at scene center
        if not self._visible_item.pixmap().isNull():
            visible_rect = self._visible_item.boundingRect()
            self._visible_item.setPos(-visible_rect.width()/2, -visible_rect.height()/2)
            
            # Reset view and fit visible image
            self.resetTransform()
            self.fitInView(self._visible_item, Qt.KeepAspectRatio)
            self._zoom_factor = self.transform().m11()
        
        # Position and scale thermal image relative to visible
        if not self._thermal_item.pixmap().isNull():
            if not self._visible_item.pixmap().isNull():
                # Calculate relative scale based on actual image dimensions
                thermal_pixmap = self._thermal_item.pixmap()
                visible_pixmap = self._visible_item.pixmap()
                
                # Original dimensions
                thermal_width = thermal_pixmap.width()
                thermal_height = thermal_pixmap.height()
                visible_width = visible_pixmap.width()
                visible_height = visible_pixmap.height()
                
                # Calculate "natural" scale ratio if images were same size
                natural_scale_x = visible_width / thermal_width if thermal_width > 0 else 1.0
                natural_scale_y = visible_height / thermal_height if thermal_height > 0 else 1.0
                natural_scale = min(natural_scale_x, natural_scale_y)
                
                # Apply user scale multiplied by natural scale
                final_scale = self._overlay_scale * natural_scale
                
                # Apply transformation
                transform = QTransform()
                transform.scale(final_scale, final_scale)
                self._thermal_item.setTransform(transform)
                
                # Calculate offsets in scene coordinates
                thermal_rect = self._thermal_item.boundingRect()
                scaled_thermal_rect = transform.mapRect(thermal_rect)
                
                # Offsets are provided in original visible image pixels
                # Must convert to scene coordinates
                visible_rect = self._visible_item.boundingRect()
                
                # Calculate ratio between scene item size and original image
                scale_x = visible_rect.width() / visible_width
                scale_y = visible_rect.height() / visible_height
                
                # Convert offsets from visible image pixels to scene coordinates
                offset_x_scene = self._overlay_offset.x() * scale_x
                offset_y_scene = self._overlay_offset.y() * scale_y
                
                # Position thermal image centered plus offset
                pos_x = -scaled_thermal_rect.width()/2 + offset_x_scene
                pos_y = -scaled_thermal_rect.height()/2 + offset_y_scene
                
                self._thermal_item.setPos(pos_x, pos_y)
            else:
                # If no visible image, center thermal
                transform = QTransform()
                transform.scale(self._overlay_scale, self._overlay_scale)
                self._thermal_item.setTransform(transform)
                
                thermal_rect = self._thermal_item.boundingRect()
                scaled_thermal_rect = transform.mapRect(thermal_rect)
                self._thermal_item.setPos(-scaled_thermal_rect.width()/2, -scaled_thermal_rect.height()/2)
                
                # If no visible, fit on scaled thermal
                self.resetTransform()
                self.fitInView(self._thermal_item, Qt.KeepAspectRatio)
                self._zoom_factor = self.transform().m11()
    
    def zoom_in(self, factor: float = 1.2):
        """Zoom in with specified factor.
        
        Args:
            factor (float): Zoom multiplication factor.
        """
        new_zoom = self._zoom_factor * factor
        if new_zoom <= self._max_zoom:
            self.scale(factor, factor)
            self._zoom_factor = new_zoom
    
    def zoom_out(self, factor: float = 1.2):
        """Zoom out with specified factor.
        
        Args:
            factor (float): Zoom division factor.
        """
        new_zoom = self._zoom_factor / factor
        if new_zoom >= self._min_zoom:
            self.scale(1/factor, 1/factor)
            self._zoom_factor = new_zoom
    
    def reset_zoom(self):
        """Reset zoom and pan to default state."""
        self.resetTransform()
        self._zoom_factor = 1.0
        
        if self._overlay_mode:
            self._update_overlay_positioning()
        else:
            self._fit_thermal_in_view()
    
    def sync_transform(self, zoom_factor: float, pan_offset: QPointF, source_pixmap_size: tuple = None):
        """Synchronize this view with another, maintaining equal relative zoom.
        
        Args:
            zoom_factor (float): Source view's zoom factor.
            pan_offset (QPointF): Source view's pan offset.
            source_pixmap_size (tuple, optional): Source pixmap dimensions (width, height).
        """
        self._is_sync_source = False  # Prevent loops
        
        # Instead of directly applying other view's zoom_factor,
        # calculate the "relative zoom level" of other view and apply it here
        
        if source_pixmap_size is not None and not self._thermal_item.pixmap().isNull():
            source_w, source_h = source_pixmap_size
            current_pixmap = self._thermal_item.pixmap()
            current_w, current_h = current_pixmap.width(), current_pixmap.height()
            
            # Calculate "natural" base zoom for each image
            # This is the zoom that makes images appear same size
            natural_zoom_source = 1.0  # Source view is reference
            natural_zoom_current = min(source_w / current_w, source_h / current_h) if current_w > 0 and current_h > 0 else 1.0
            
            # Target zoom for this view should be:
            # natural zoom multiplied by source's relative zoom level
            source_relative_zoom = zoom_factor / natural_zoom_source  # Source's relative zoom level
            target_zoom = natural_zoom_current * source_relative_zoom
            
            # Apply target zoom
            scale_factor = target_zoom / self._zoom_factor
            if abs(scale_factor - 1.0) > 0.001:  # Avoid micro-adjustments
                self.scale(scale_factor, scale_factor)
                self._zoom_factor = target_zoom
        else:
            # Fallback: apply zoom factor directly (original behavior)
            scale_factor = zoom_factor / self._zoom_factor
            if abs(scale_factor - 1.0) > 0.001:
                self.scale(scale_factor, scale_factor)
                self._zoom_factor = zoom_factor
            
        # Apply pan
        current_transform = self.transform()
        new_transform = QTransform(current_transform)
        new_transform.setMatrix(
            new_transform.m11(), new_transform.m12(), new_transform.m13(),
            new_transform.m21(), new_transform.m22(), new_transform.m23(),
            pan_offset.x(), pan_offset.y(), new_transform.m33()
        )
        self.setTransform(new_transform)
        
        self._is_sync_source = True

    def get_current_pixmap_size(self) -> tuple:
        """Get current pixmap dimensions.
        
        Returns:
            tuple: Pixmap dimensions (width, height).
        """
        if not self._thermal_item.pixmap().isNull():
            pixmap = self._thermal_item.pixmap()
            return (pixmap.width(), pixmap.height())
        return (1, 1)  # Fallback to avoid division by zero

    def wheelEvent(self, event: QWheelEvent):
        """Handle mouse wheel events for zooming and panning.
        
        Args:
            event (QWheelEvent): The wheel event.
        """
        if event.modifiers() == Qt.ControlModifier:
            # Zoom with Ctrl + wheel
            angle_delta = event.angleDelta().y()
            factor = 1.2 if angle_delta > 0 else 1/1.2
            
            if angle_delta > 0:
                self.zoom_in(factor)
            else:
                self.zoom_out(factor)
            
            # Emit transformation signal with size information
            if self._is_sync_source:
                pixmap_size = self.get_current_pixmap_size()
                self.view_transformed.emit(self._zoom_factor, self.get_pan_offset(), pixmap_size)
            
            event.accept()
        else:
            # Pan with simple wheel
            super().wheelEvent(event)
            if self._is_sync_source:
                pixmap_size = self.get_current_pixmap_size()
                self.view_transformed.emit(self._zoom_factor, self.get_pan_offset(), pixmap_size)

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press events for ROI drawing and navigation.
        
        Args:
            event (QMouseEvent): The mouse press event.
        """
        # Check if we're in ROI drawing mode
        if (self._current_drawing_tool == "rect" and 
            self._allow_roi_drawing and                 
            event.button() == Qt.LeftButton):
            
            # Start ROI drawing
            self._start_roi_drawing(event)
            return  # Don't call super() to prevent other mouse handling
        
        # Check if we're in spot ROI mode
        if (self._current_drawing_tool == "spot" and 
            self._allow_roi_drawing and
            event.button() == Qt.LeftButton):
            
            # Create spot ROI directly
            self._create_spot_from_click(event)
            return
        
        # Check if we're in polygon ROI mode
        if (self._current_drawing_tool == "polygon" and 
            self._allow_roi_drawing):
            
            if event.button() == Qt.LeftButton:
                # Add point to polygon
                self._add_polygon_point(event)
                return
            elif event.button() == Qt.RightButton and self._polygon_drawing:
                # Finish polygon with right click
                self._finish_polygon_drawing()
                return
        
        # Handle middle button for panning
        if event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self._pan_active = True
        
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse movement for temperature tooltips, pan sync, and ROI drawing.
        
        Args:
            event (QMouseEvent): The mouse move event.
        """
        
        # Handle ROI drawing
        if self._roi_drawing:
            self._update_roi_drawing(event)
        
        # Continue with existing functionality
        super().mouseMoveEvent(event)
        
        # Emit signal if pan has changed
        if self._pan_active and self._is_sync_source:
            pixmap_size = self.get_current_pixmap_size()
            self.view_transformed.emit(self._zoom_factor, self.get_pan_offset(), pixmap_size)
        
        # Calculate coordinates on thermal map
        if not self._thermal_item.pixmap().isNull():
            scene_pos = self.mapToScene(event.pos())
            thermal_pos = self._thermal_item.mapFromScene(scene_pos)
            
            # Convert to original image coordinates
            thermal_rect = self._thermal_item.boundingRect()
            if thermal_rect.contains(thermal_pos):
                # Emit signal with coordinates relative to image
                self.mouse_moved_on_thermal.emit(thermal_pos)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release events.
        
        Args:
            event (QMouseEvent): The mouse release event.
        """
        
        # Handle ROI drawing completion
        if (self._roi_drawing and event.button() == Qt.LeftButton):
            self._finish_roi_drawing(event)
            return  # Don't call super() to prevent other mouse handling
            
        # Handle middle button for panning
        if event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.RubberBandDrag)
            self._pan_active = False
        
        super().mouseReleaseEvent(event)

    def _start_roi_drawing(self, event: QMouseEvent):
        """Start drawing a rectangular ROI.
        
        Args:
            event (QMouseEvent): The mouse press event that started the drawing.
        """
        scene_pos = self.mapToScene(event.pos())
        self._roi_start_pos = scene_pos
        self._roi_drawing = True
        
        # Create temporary ROI item for visual feedback
        temp_rect = QRectF(scene_pos.x(), scene_pos.y(), 1, 1)
        self._temp_roi_item = self._scene.addRect(
            temp_rect,
            QPen(QColor(255, 165, 0), 2),  # Orange pen
            QBrush(QColor(255, 165, 0, 40))  # Semi-transparent orange
        )
        self._temp_roi_item.setZValue(10)  # Temporary rectangle on top
        print(f"Started ROI drawing at: {scene_pos}")

    def _update_roi_drawing(self, event: QMouseEvent):
        """Update ROI drawing during mouse movement.
        
        Args:
            event (QMouseEvent): The mouse move event.
        """
        if not self._roi_drawing or self._temp_roi_item is None:
            return
            
        current_pos = self.mapToScene(event.pos())
        
        # Calculate rectangle dimensions
        x = min(self._roi_start_pos.x(), current_pos.x())
        y = min(self._roi_start_pos.y(), current_pos.y())
        width = abs(current_pos.x() - self._roi_start_pos.x())
        height = abs(current_pos.y() - self._roi_start_pos.y())
        
        # Update temporary rectangle
        new_rect = QRectF(x, y, width, height)
        self._temp_roi_item.setRect(new_rect)

    def _finish_roi_drawing(self, event: QMouseEvent):
        """Complete ROI drawing.
        
        Args:
            event (QMouseEvent): The mouse release event that finished the drawing.
        """
        if not self._roi_drawing or self._temp_roi_item is None:
            return
            
        # Get final rectangle
        final_rect = self._temp_roi_item.rect()
        
        # Remove temporary item
        self._scene.removeItem(self._temp_roi_item)
        self._temp_roi_item = None
        
        # Reset drawing state
        self._roi_drawing = False
        self._roi_start_pos = None
        
        # Create ROI if rectangle is large enough
        if final_rect.width() > 5 and final_rect.height() > 5:
            self._emit_rect_roi_signal(final_rect)
        
        # Request drawing tool deactivation
        self.drawing_tool_deactivation_requested.emit()
        
        print(f"Finished ROI drawing with rect: {final_rect}")

    def _emit_rect_roi_signal(self, rect: QRectF):
        """Emit signal for rectangular ROI creation.
        
        Args:
            rect (QRectF): The rectangle in scene coordinates.
        """
        # Map rectangle vertices from SCENE -> thermal item local coordinates (thermal pixels)
        tl_img = self._thermal_item.mapFromScene(rect.topLeft())
        br_img = self._thermal_item.mapFromScene(rect.bottomRight())

        x = min(tl_img.x(), br_img.x())
        y = min(tl_img.y(), br_img.y())
        w = abs(br_img.x() - tl_img.x())
        h = abs(br_img.y() - tl_img.y())

        # Create thermal image coordinate rectangle
        thermal_rect = QRectF(x, y, w, h)
        
        # Emit signal with thermal image coordinates
        self.rect_roi_drawn.emit(thermal_rect)
        
        print(f"Emitted rect ROI signal: {thermal_rect}")

    def _create_spot_from_click(self, event: QMouseEvent):
        """Emit signal for spot ROI creation.
        
        Args:
            event (QMouseEvent): The mouse click event.
        """
        # Convert click position to scene coordinates
        scene_pos = self.mapToScene(event.pos())
        
        # Map from scene to thermal image coordinates
        thermal_pos = self._thermal_item.mapFromScene(scene_pos)
        
        # Default radius in thermal pixels
        default_radius = 10.0
        
        # Emit signal with thermal image coordinates
        self.spot_roi_drawn.emit(thermal_pos, default_radius)
        
        # Request drawing tool deactivation
        self.drawing_tool_deactivation_requested.emit()
        
        print(f"Emitted spot ROI signal at: {thermal_pos.x():.1f}, {thermal_pos.y():.1f}")

    def _add_polygon_point(self, event: QMouseEvent):
        """Add a point to the polygon being constructed.
        
        Args:
            event (QMouseEvent): The mouse click event.
        """
        # Convert click position to scene coordinates
        scene_pos = self.mapToScene(event.pos())
        
        # Map from scene to thermal image coordinates
        thermal_pos = self._thermal_item.mapFromScene(scene_pos)
        
        # Add point to list
        self._current_polygon_points.append((thermal_pos.x(), thermal_pos.y()))
        
        # If first point, start drawing
        if not self._polygon_drawing:
            self._polygon_drawing = True
            self._temp_polygon_item = QGraphicsPolygonItem()
            self._temp_polygon_item.setPen(QPen(QColor(255, 165, 0, 150), 2, Qt.DashLine))
            self._temp_polygon_item.setBrush(QBrush(QColor(255, 165, 0, 30)))
            # Set parent item instead of setParent()
            self._temp_polygon_item.setParentItem(self._thermal_item)
            
            # Show instructions to user
            print("🔵 Polygon started! Left click to add points, ENTER/DOUBLE-CLICK to complete, ESC to cancel")
        
        # Update temporary polygon
        self._update_temp_polygon()
        
        print(f"Added polygon point: {thermal_pos.x():.1f}, {thermal_pos.y():.1f} (total: {len(self._current_polygon_points)})")

    def _update_temp_polygon(self):
        """Update temporary polygon during drawing."""
        if self._temp_polygon_item and len(self._current_polygon_points) >= 2:
            
            qt_polygon = QPolygonF()
            for x, y in self._current_polygon_points:
                qt_polygon.append(QPointF(x, y))
            
            self._temp_polygon_item.setPolygon(qt_polygon)

    def _finish_polygon_drawing(self):
        """Complete polygon drawing."""
        if len(self._current_polygon_points) < 3:
            print("⚠️  Polygon must have at least 3 points")
            return
        
        print("✅ Polygon completed!")
        
        # Emit signal for polygon ROI creation
        self._emit_polygon_roi_signal(self._current_polygon_points.copy())
        
        # Reset state and clean temporary polygon
        self._cancel_polygon_drawing()
        
        # Request drawing tool deactivation
        self.drawing_tool_deactivation_requested.emit()

    def _cancel_polygon_drawing(self):
        """Cancel polygon drawing and clean state."""
        # Remove temporary polygon
        if self._temp_polygon_item:
            # If it has parent, parent will automatically remove from scene
            if self._temp_polygon_item.parentItem():
                self._temp_polygon_item.setParentItem(None)
            self._temp_polygon_item = None
        
        # Reset state
        self._polygon_drawing = False
        self._current_polygon_points = []

    def _emit_polygon_roi_signal(self, points):
        """Emit signal for polygon ROI creation.
        
        Args:
            points (list): List of (x, y) coordinate tuples in thermal image space.
        """
        # Close polygon if necessary
        if points[0] != points[-1]:
            points.append(points[0])
        
        # Emit signal with thermal image coordinates
        self.polygon_roi_drawn.emit(points)
        
        print(f"Emitted polygon ROI signal with {len(points)} points")

    def get_zoom_factor(self) -> float:
        """Get current zoom factor.
        
        Returns:
            float: Current zoom factor.
        """
        return self._zoom_factor
    
    def get_overlay_settings(self) -> dict:
        """Get current overlay settings.
        
        Returns:
            dict: Dictionary containing overlay configuration.
        """
        return {
            'mode': self._overlay_mode,
            'alpha': self._overlay_alpha,
            'scale': self._overlay_scale,
            'offset': self._overlay_offset,
            'blend_mode': self._blend_mode
        }

    def get_scale_info(self) -> dict:
        """Get detailed scale information for debugging.
        
        Returns:
            dict: Dictionary containing scale and transform details.
        """
        info = {
            'overlay_scale': self._overlay_scale,
            'view_transform': self.transform().m11(),
            'zoom_factor': self._zoom_factor,
            'overlay_offset': (self._overlay_offset.x(), self._overlay_offset.y())
        }
        
        if not self._thermal_item.pixmap().isNull() and not self._visible_item.pixmap().isNull():
            thermal_pixmap = self._thermal_item.pixmap()
            visible_pixmap = self._visible_item.pixmap()
            
            visible_rect = self._visible_item.boundingRect()
            
            info.update({
                'thermal_size': (thermal_pixmap.width(), thermal_pixmap.height()),
                'visible_size': (visible_pixmap.width(), visible_pixmap.height()),
                'visible_rect_size': (visible_rect.width(), visible_rect.height()),
                'natural_scale_x': visible_pixmap.width() / thermal_pixmap.width(),
                'natural_scale_y': visible_pixmap.height() / thermal_pixmap.height(),
            })
            
            natural_scale = min(info['natural_scale_x'], info['natural_scale_y'])
            info['natural_scale'] = natural_scale
            info['final_scale'] = self._overlay_scale * natural_scale
            
            # Calculate converted offsets
            scale_x = visible_rect.width() / visible_pixmap.width()
            scale_y = visible_rect.height() / visible_pixmap.height()
            offset_x_scene = self._overlay_offset.x() * scale_x
            offset_y_scene = self._overlay_offset.y() * scale_y
            
            info.update({
                'offset_scale_x': scale_x,
                'offset_scale_y': scale_y,
                'offset_scene': (offset_x_scene, offset_y_scene)
            })
            
        return info

    def get_pan_offset(self) -> QPointF:
        """Get current pan offset.
        
        Returns:
            QPointF: Current pan offset.
        """
        transform = self.transform()
        return QPointF(transform.dx(), transform.dy())

    def keyPressEvent(self, event):
        """Handle key press events.
        
        Args:
            event: The key press event.
        """
        # ENTER completes polygon
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if (self._current_drawing_tool == "polygon" and 
                self._polygon_drawing):
                
                self._finish_polygon_drawing()
                event.accept()
                return
        
        # ESC stops ROI drawing mode
        if event.key() == Qt.Key_Escape:
            if self._current_drawing_tool is not None:
                
                # If we were drawing a polygon, clean up
                if self._polygon_drawing:
                    print("❌ Polygon drawing cancelled")
                    self._cancel_polygon_drawing()
                
                # Request drawing tool deactivation
                self.drawing_tool_deactivation_requested.emit()
                event.accept()
                return
        
        super().keyPressEvent(event)
        
    def notify_roi_modified(self, roi_model):
        """Notify that a ROI has been modified.
        
        This method is called by ROI items when they are moved or resized.
        
        Args:
            roi_model: The ROI model that was modified.
        """
        self.roi_modified.emit(roi_model)
        
    def set_roi_label_settings(self, settings: dict):
        """Set the ROI label display settings.
        
        Args:
            settings (dict): Dictionary with label visibility settings.
        """
        self._roi_label_settings = settings

    def get_roi_label_settings(self) -> dict:
        """Get the current ROI label display settings.
        
        Returns:
            dict: Dictionary with label visibility settings.
        """
        return self._roi_label_settings
        