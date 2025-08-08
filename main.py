from PySide6.QtWidgets import QApplication
import sys
from ui.main_window import ThermalAnalyzerNG


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ThermalAnalyzerNG()
    window.show()
    sys.exit(app.exec())
