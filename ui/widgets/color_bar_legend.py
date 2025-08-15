"""Color bar legend widget for thermal imaging applications.

This module provides a customizable color bar legend widget that displays
temperature scales with configurable palettes, orientations, and tick marks.
"""

from PySide6.QtWidgets import QWidget, QSizePolicy as QSP
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap, QImage, QColor, QPen, QFontMetrics
import numpy as np
import matplotlib.cm as cm

from constants import PALETTE_MAP


class ColorBarLegend(QWidget):
    """A customizable color bar legend widget for displaying temperature scales.
    
    This widget renders a color gradient bar with tick marks and labels,
    supporting both vertical and horizontal orientations. It's designed
    for thermal imaging applications where temperature ranges need to be
    visualized with color mappings.
    """

    def __init__(self, parent=None):
        """Initialize the color bar legend widget.
        
        Args:
            parent: Parent widget, defaults to None.
        """
        super().__init__(parent)
        self._min = 0.0
        self._max = 1.0
        self._palette = "Iron"
        self._inverted = False
        self._orientation = Qt.Vertical  # Qt.Vertical or Qt.Horizontal
        self._tick_count = 5  # Elegant appearance with 5 ticks
        self._draw_background = False  # Keep transparent by default
        self._unit = "°C"
        self._precision = 1
        self._forced_text_color = None  # Force specific text color for exports
        
        # Use smaller font for elegant appearance
        _f = self.font()
        try:
            _f.setPointSizeF(9.0)
        except Exception:
            pass
        self.setFont(_f)
        
        # Set default size for vertical orientation
        self.setMinimumSize(90, 320)
        self.setSizePolicy(QSP.Fixed, QSP.Preferred)
        
        # Avoid unit repetition if present in title
        self._show_units_on_ticks = False
        
        # Set transparent background for PNG exports
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background-color: transparent;")

    def set_range(self, vmin: float, vmax: float):
        """Set the value range for the color bar.
        
        Args:
            vmin (float): Minimum value of the range.
            vmax (float): Maximum value of the range.
        """
        self._min, self._max = float(vmin), float(vmax)
        self.update()

    def set_palette(self, name: str, inverted: bool):
        """Set the color palette and inversion state.
        
        Args:
            name (str): Name of the color palette.
            inverted (bool): Whether to invert the palette colors.
        """
        self._palette = name
        self._inverted = bool(inverted)
        self.update()

    def set_orientation(self, orientation: Qt.Orientation):
        """Set the orientation of the color bar.
        
        Args:
            orientation (Qt.Orientation): Either Qt.Vertical or Qt.Horizontal.
        """
        self._orientation = orientation
        # Adjust default minimum size for horizontal layout
        if self._orientation == Qt.Horizontal:
            self.setMinimumSize(240, 48)
            self.setSizePolicy(QSP.Preferred, QSP.Fixed)
        else:
            self.setMinimumSize(90, 320)
            self.setSizePolicy(QSP.Fixed, QSP.Preferred)
        self.update()

    def set_tick_count(self, tick_count: int):
        """Set the number of tick marks on the color bar.
        
        Args:
            tick_count (int): Number of ticks, minimum value is 2.
        """
        self._tick_count = max(2, int(tick_count))
        self.update()

    def set_background(self, draw_background: bool):
        """Set whether to draw a background for the color bar.
        
        Args:
            draw_background (bool): True to draw background, False for transparent.
        """
        self._draw_background = bool(draw_background)
        self.update()

    def set_unit(self, unit: str):
        """Set the unit string for value labels.
        
        Args:
            unit (str): Unit string to display (e.g., "°C", "°F").
        """
        self._unit = unit
        self.update()

    def set_precision(self, precision: int):
        """Set the decimal precision for value labels.
        
        Args:
            precision (int): Number of decimal places, minimum is 0.
        """
        self._precision = max(0, int(precision))
        self.update()

    def set_show_units_on_ticks(self, enabled: bool):
        """Set whether to show units on each tick label.
        
        Args:
            enabled (bool): True to show units on ticks, False to hide them.
        """
        self._show_units_on_ticks = bool(enabled)
        self.update()

    def set_forced_text_color(self, color):
        """Set a forced text color for exports, overriding theme-based color.
        
        Args:
            color: QColor instance, or None to use automatic theme-based color.
        """
        self._forced_text_color = color
        self.update()

    def _make_bar_pixmap(self, height: int, width: int = 28) -> QPixmap:
        """Create a gradient bar pixmap with the current palette.
        
        Args:
            height (int): Height of the pixmap in pixels.
            width (int): Width of the pixmap in pixels, defaults to 28.
            
        Returns:
            QPixmap: The rendered gradient bar pixmap.
        """
        cmap = PALETTE_MAP.get(self._palette, cm.inferno)
        if self._orientation == Qt.Vertical:
            steps = max(2, height)
            grad = np.linspace(1.0, 0.0, steps).reshape(steps, 1)
            if self._inverted:
                grad = 1.0 - grad
            rgb = (cmap(grad)[:, :, :3] * 255).astype(np.uint8)  # (H,1,3)
            qimg = QImage(rgb.data, 1, steps, 3, QImage.Format_RGB888)
            return QPixmap.fromImage(qimg).scaled(width, height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        else:
            steps = max(2, width)
            grad = np.linspace(0.0, 1.0, steps).reshape(1, steps)
            if self._inverted:
                grad = 1.0 - grad
            rgb = (cmap(grad)[:, :, :3] * 255).astype(np.uint8)  # (1,W,3)
            qimg = QImage(rgb.data, steps, 1, steps * 3, QImage.Format_RGB888)
            return QPixmap.fromImage(qimg).scaled(width, height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

    def paintEvent(self, _):
        """Handle the paint event to render the color bar legend.
        
        Args:
            _: Paint event (unused).
        """
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        margin = 8
        bar_w = 16
        label_gap = 6
        tick_len = 6

        full = self.rect()
        fm = QFontMetrics(p.font())

        if self._orientation == Qt.Vertical:
            bar_x = full.left() + margin
            bar_y = full.top() + margin
            bar_h = full.height() - margin * 2
            bar_pix = self._make_bar_pixmap(bar_h, bar_w)

            # Draw background only if requested
            if self._draw_background:
                p.fillRect(full.adjusted(0, 0, -1, -1), QColor(248, 248, 248))
                p.setPen(QColor(220, 220, 220))
                p.drawRoundedRect(full.adjusted(0, 0, -1, -1), 4, 4)

            p.drawPixmap(bar_x, bar_y, bar_pix)

            p.setPen(QColor(60, 60, 60, 100))
            p.drawRect(bar_x, bar_y, bar_w, bar_h)

            vmin, vmax = self._min, self._max
            rng = max(1e-9, (vmax - vmin))
            if self._tick_count <= 2:
                values = [vmax, vmin]
            else:
                values = [vmin + i * (rng / (self._tick_count - 1)) for i in range(self._tick_count)]
                values = values[::-1]  # Top to bottom labels as max ... min
            for idx, val in enumerate(values):
                t = (val - vmin) / rng  # 0..1 bottom -> top mapping
                y = int(bar_y + (1.0 - t) * bar_h)
                
                # Use forced color for exports, or system color for UI
                if self._forced_text_color is not None:
                    text_color = self._forced_text_color
                else:
                    # Use system text color for better theme compatibility
                    from PySide6.QtWidgets import QApplication
                    text_color = QApplication.palette().color(QApplication.palette().ColorRole.Text)
                p.setPen(QPen(text_color, 1))
                
                p.drawLine(bar_x + bar_w, y, bar_x + bar_w + tick_len, y)
                label = f"{val:.{self._precision}f}" + (f" {self._unit}" if self._show_units_on_ticks else "")
                p.drawText(bar_x + bar_w + tick_len + label_gap, y + fm.ascent() // 2, label)
        else:
            bar_h = 18
            bar_x = full.left() + margin
            bar_y = full.center().y() - bar_h // 2
            bar_w_pix = full.width() - margin * 2
            bar_pix = self._make_bar_pixmap(bar_h, bar_w_pix)

            if self._draw_background:
                p.fillRect(full.adjusted(0, 0, -1, -1), QColor(248, 248, 248))
                p.setPen(QColor(220, 220, 220))
                p.drawRoundedRect(full.adjusted(0, 0, -1, -1), 4, 4)

            p.drawPixmap(bar_x, bar_y, bar_pix)
            p.setPen(QColor(60, 60, 60, 100))
            p.drawRect(bar_x, bar_y, bar_w_pix, bar_h)

            vmin, vmax = self._min, self._max
            rng = max(1e-9, (vmax - vmin))
            if self._tick_count <= 2:
                values = [vmin, vmax]
            else:
                values = [vmin + i * (rng / (self._tick_count - 1)) for i in range(self._tick_count)]
            baseline = bar_y + bar_h + 8
            for val in values:
                t = (val - vmin) / rng
                x = int(bar_x + t * bar_w_pix)
                
                # Use forced color for exports, or system color for UI
                if self._forced_text_color is not None:
                    text_color = self._forced_text_color
                else:
                    # Use system text color for better theme compatibility
                    from PySide6.QtWidgets import QApplication
                    text_color = QApplication.palette().color(QApplication.palette().ColorRole.Text)
                p.setPen(QPen(text_color, 1))
                
                p.drawLine(x, bar_y + bar_h, x, bar_y + bar_h + tick_len)
                label = f"{val:.{self._precision}f}" + (f" {self._unit}" if self._show_units_on_ticks else "")
                label_w = fm.horizontalAdvance(label)
                p.drawText(x - label_w // 2, baseline + fm.ascent(), label)

        p.end()
