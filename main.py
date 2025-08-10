import os
import sys

from PySide6.QtCore import (Qt, QTimer, QPropertyAnimation, QEasingCurve, QRectF,
                            QRect, QParallelAnimationGroup)
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtWidgets import (QApplication, QSplashScreen, QGraphicsOpacityEffect)
from PySide6.QtSvg import QSvgRenderer
from ui.main_window import ThermalAnalyzerNG


class AppWindow(ThermalAnalyzerNG):
    """
    Questa è la TUA classe della finestra principale, che eredita dalla tua UI.
    """
    def __init__(self, parent=None):
        # Chiamiamo il costruttore della classe base SENZA argomenti.
        super().__init__()
        print("Costruttore della vera finestra 'AppWindow' completato.")

    # Se la tua classe AppWindow sovrascrive questo metodo, mantienilo.
    # Altrimenti, puoi rimuoverlo se non aggiunge nuova logica.
    def activate_rect_tool(self):
        super().activate_rect_tool()


# ==============================================================================
# FUNZIONI DI UTILITÀ PER LO SPLASH SCREEN
# ==============================================================================

def create_splash_pixmap(svg_path: str, screen_w: int, screen_h: int) -> QPixmap:
    renderer = QSvgRenderer(svg_path)
    if not renderer.isValid():
        pm = QPixmap(400, 200)
        pm.fill(Qt.transparent)
        return pm

    box = renderer.viewBoxF()
    vw = box.width() if box.width() > 0 else float(renderer.defaultSize().width())
    vh = box.height() if box.height() > 0 else float(renderer.defaultSize().height())

    max_w = screen_w / 5.0
    max_h = screen_h / 5.0
    scale = min(max_w / vw, max_h / vh) if vw > 0 and vh > 0 else 1.0
    tw = max(1, int(vw * scale))
    th = max(1, int(vh * scale))

    pm = QPixmap(tw, th)
    pm.fill(Qt.transparent)

    painter = QPainter(pm)
    renderer.render(painter, QRectF(0, 0, float(tw), float(th)))
    painter.end()
    return pm


def fade_out_and_close(widget, duration_ms: int, finished_cb=None):
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

    widget._opacity_anim = anim
    anim.start(QPropertyAnimation.DeleteWhenStopped)


# ==============================================================================
# BLOCCO DI ESECUZIONE PRINCIPALE
# ==============================================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    svg_path = os.path.join(base_dir, "Warmish Logo.svg") # Assicurati che il logo sia nella cartella principale
    if not os.path.exists(svg_path):
        svg_content = '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100"><rect width="200" height="100" style="fill:rgb(70,130,180);" /><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="white" font-size="20">Logo</text></svg>'
        with open(svg_path, 'w') as f: f.write(svg_content)

    screen = app.primaryScreen()
    geo = screen.availableGeometry()
    pixmap = create_splash_pixmap(svg_path, geo.width(), geo.height())

    splash = QSplashScreen(pixmap, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
    splash.setAttribute(Qt.WA_TranslucentBackground, True)
    splash.setAttribute(Qt.WA_NoSystemBackground, True)
    
    opacity_effect = QGraphicsOpacityEffect(splash)
    splash.setGraphicsEffect(opacity_effect)
    opacity_effect.setOpacity(0.0)

    final_rect = splash.geometry()
    center_point = final_rect.center()
    start_rect = QRect(center_point, final_rect.size() * 0.8)
    splash.setGeometry(start_rect)

    splash.show()
    splash.raise_()

    opacity_anim = QPropertyAnimation(opacity_effect, b"opacity")
    opacity_anim.setStartValue(0.0); opacity_anim.setEndValue(1.0)
    opacity_anim.setDuration(700); opacity_anim.setEasingCurve(QEasingCurve.InOutCubic)

    geom_anim = QPropertyAnimation(splash, b"geometry")
    geom_anim.setStartValue(start_rect); geom_anim.setEndValue(final_rect)
    geom_anim.setDuration(700); geom_anim.setEasingCurve(QEasingCurve.OutCubic)

    anim_group = QParallelAnimationGroup(splash)
    anim_group.addAnimation(opacity_anim)
    anim_group.addAnimation(geom_anim)
    anim_group.start(QPropertyAnimation.DeleteWhenStopped)
    app.processEvents()

    window = AppWindow()
    
    def show_main_window():
        window.show()
    
    def start_closing_splash():
        fade_out_and_close(splash, 600, finished_cb=show_main_window)

    QTimer.singleShot(1000, start_closing_splash)
    
    sys.exit(app.exec())