# -*- coding: utf-8 -*-
"""
Main entry point for the Thermal Analyzer NG application.

This script handles the application startup, including a splash screen with
animations, and initializes the main application window.
"""

import os
import sys

from PySide6.QtCore import (Qt, QTimer, QPropertyAnimation, QEasingCurve, QRectF,
                            QRect, QParallelAnimationGroup)
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtWidgets import (QApplication, QSplashScreen, QGraphicsOpacityEffect)
from PySide6.QtSvg import QSvgRenderer
from ui.main_window import ThermalAnalyzerNG

# ==============================================================================
# MODIFICA 1: Aggiunta della funzione di supporto resource_path
# Questa funzione è IDENTICA a quella usata in thermal_engine.py
# ==============================================================================
def resource_path(relative_path):
    """ Ottiene il percorso assoluto della risorsa, funziona sia in dev che con PyInstaller """
    try:
        # PyInstaller crea una cartella temporanea e ci salva il percorso in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Se non siamo in un pacchetto, usiamo il percorso del file corrente
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)
# ==============================================================================
# Fine Modifica 1
# ==============================================================================


class AppWindow(ThermalAnalyzerNG):
    """
    The main application window, inheriting from the UI class `ThermalAnalyzerNG`.

    This class serves as the primary interface for the user and can be extended
    with custom application logic and event handlers.
    """
    def __init__(self, parent=None):
        super().__init__()
        print("Application main window constructor completed.")

    def activate_rect_tool(self):
        """
        This method is overridden to allow for future customization.

        It currently calls the base implementation but can be extended with
        specific logic for this window.
        """
        super().activate_rect_tool()


# ==============================================================================
# UTILITY FUNCTIONS FOR THE SPLASH SCREEN
# ==============================================================================

def create_splash_pixmap(svg_path: str, screen_w: int, screen_h: int) -> QPixmap:
    """Renders an SVG file to a QPixmap, scaled for the splash screen.

    The function scales the SVG to fit within a fraction (1/5th) of the
    screen dimensions while preserving its aspect ratio. If the SVG file is
    invalid or not found, it returns a transparent placeholder pixmap.

    Args:
        svg_path (str): The absolute path to the SVG logo file.
        screen_w (int): The width of the available screen geometry.
        screen_h (int): The height of the available screen geometry.

    Returns:
        QPixmap: The rendered and scaled pixmap for the splash screen.
    """
    renderer = QSvgRenderer(svg_path)
    if not renderer.isValid():
        # Fallback to a transparent pixmap if SVG is invalid
        pm = QPixmap(400, 200)
        pm.fill(Qt.transparent)
        return pm

    # Calculate the target size based on screen dimensions
    box = renderer.viewBoxF()
    vw = box.width() if box.width() > 0 else float(renderer.defaultSize().width())
    vh = box.height() if box.height() > 0 else float(renderer.defaultSize().height())

    max_w = screen_w / 5.0
    max_h = screen_h / 5.0
    scale = min(max_w / vw, max_h / vh) if vw > 0 and vh > 0 else 1.0
    tw = max(1, int(vw * scale))
    th = max(1, int(vh * scale))

    # Create and render the pixmap
    pm = QPixmap(tw, th)
    pm.fill(Qt.transparent)

    painter = QPainter(pm)
    renderer.render(painter, QRectF(0, 0, float(tw), float(th)))
    painter.end()
    return pm


def fade_out_and_close(widget, duration_ms: int, finished_cb=None):
    """Fades out a widget and closes it upon completion.

    Applies a QGraphicsOpacityEffect to animate the widget's opacity from
    1.0 to 0.0. When the animation is finished, the widget's `close()` slot
    is called.

    Args:
        widget (QWidget): The widget to animate and close.
        duration_ms (int): The duration of the fade-out animation in milliseconds.
        finished_cb (callable, optional): A callback to execute when the
                                          animation is finished, just before closing.
    """
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)

    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(duration_ms)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.InOutQuad)

    if finished_cb:
        anim.finished.connect(finished_cb)
    anim.finished.connect(widget.close)

    # Store a reference to the animation to prevent garbage collection
    widget._opacity_anim = anim
    anim.start(QPropertyAnimation.DeleteWhenStopped)


# ==============================================================================
# MAIN EXECUTION BLOCK
# ==============================================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Apply settings for better rendering and theming on Windows.
    if sys.platform == "win32":
        app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        app.setStyle("windowsvista") # Enables native support for Windows dark theme

    # ==============================================================================
    # MODIFICA 2: Usa resource_path per trovare il logo SVG
    # ==============================================================================
    # RIGA ORIGINALE COMMENTATA:
    # base_dir = os.path.dirname(os.path.abspath(__file__))
    # svg_path = os.path.join(base_dir, "Warmish Logo.svg")
    
    # NUOVA RIGA:
    svg_path = resource_path("Warmish Logo.svg")
    # ==============================================================================
    # Fine Modifica 2
    # ==============================================================================

    # If the logo SVG doesn't exist, create a simple placeholder.
    if not os.path.exists(svg_path):
        # NOTA: Questa parte di codice non verrà eseguita nel pacchetto finale,
        # perché il file esisterà. È utile solo durante lo sviluppo se il file manca.
        svg_content = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" '
            'viewBox="0 0 200 100"><rect width="200" height="100" '
            'style="fill:rgb(70,130,180);" /><text x="50%" y="50%" '
            'dominant-baseline="middle" text-anchor="middle" fill="white" '
            'font-size="20">Logo</text></svg>'
        )
        # Usiamo il percorso originale per creare il file se manca, ma PyInstaller lo includerà.
        original_svg_path = os.path.join(os.path.abspath("."), "Warmish Logo.svg")
        with open(original_svg_path, 'w') as f:
            f.write(svg_content)
        svg_path = original_svg_path


    # Create the pixmap for the splash screen
    screen = app.primaryScreen()
    geo = screen.availableGeometry()
    pixmap = create_splash_pixmap(svg_path, geo.width(), geo.height())

    # Create the splash screen widget with flags for a modern, frameless look.
    splash = QSplashScreen(pixmap, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
    splash.setAttribute(Qt.WA_TranslucentBackground, True)
    splash.setAttribute(Qt.WA_NoSystemBackground, True)

    # Use a QGraphicsOpacityEffect to enable smooth fading animations.
    opacity_effect = QGraphicsOpacityEffect(splash)
    splash.setGraphicsEffect(opacity_effect)
    opacity_effect.setOpacity(0.0) # Start fully transparent to fade in.

    # Define the animation start and end geometries for a "zoom-in" effect.
    final_rect = splash.geometry()
    center_point = final_rect.center()
    start_rect = QRect(center_point, final_rect.size() * 0.8) # Start smaller
    splash.setGeometry(start_rect)

    splash.show()
    splash.raise_()

    # Define the fade-in and zoom-in animations.
    opacity_anim = QPropertyAnimation(opacity_effect, b"opacity")
    opacity_anim.setStartValue(0.0)
    opacity_anim.setEndValue(1.0)
    opacity_anim.setDuration(700)
    opacity_anim.setEasingCurve(QEasingCurve.InOutCubic)

    geom_anim = QPropertyAnimation(splash, b"geometry")
    geom_anim.setStartValue(start_rect)
    geom_anim.setEndValue(final_rect)
    geom_anim.setDuration(700)
    geom_anim.setEasingCurve(QEasingCurve.OutCubic)

    # Group the opacity and geometry animations to run in parallel.
    anim_group = QParallelAnimationGroup(splash)
    anim_group.addAnimation(opacity_anim)
    anim_group.addAnimation(geom_anim)
    anim_group.start(QPropertyAnimation.DeleteWhenStopped)

    # Process events to ensure the animation starts smoothly.
    app.processEvents()

    # Initialize the main application window while the splash is visible.
    window = AppWindow()

    def show_main_window():
        """Shows the main application window."""
        try:
            window.show()
        except Exception as e:
            print(f"Error showing main window: {e}")
            import traceback
            traceback.print_exc()

    def start_closing_splash():
        """Starts the fade-out animation for the splash screen."""
        fade_out_and_close(splash, 600, finished_cb=show_main_window)

    # Display the splash screen for a minimum duration before closing it.
    # This ensures the user sees the animation and logo.
    QTimer.singleShot(1000, start_closing_splash)

    sys.exit(app.exec())