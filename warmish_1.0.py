import sys
import exiftool
import numpy as np
import json
import subprocess
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget,
    QFileDialog, QMessageBox, QTextEdit, QSizePolicy, QLineEdit, QFormLayout,
    QGroupBox
)
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import Qt
from PIL import Image
import io
import matplotlib.cm as cm

class ThermalAnalyzerNG(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Analizzatore di Immagini Termiche NG")
        self.setGeometry(100, 100, 1400, 900)

        # Dati immagine
        self.thermal_data = None
        self.temperature_data = None
        self.temp_min = 0
        self.temp_max = 0
        self.metadata = None
        self.base_pixmap = None

        # --- Layout Principale (orizzontale) ---
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)

        # --- Colonna Sinistra (Controlli e Immagine) ---
        self.left_widget = QWidget()
        self.left_layout = QVBoxLayout(self.left_widget)
        self.main_layout.addWidget(self.left_widget, stretch=4)

        # Pulsante Apertura
        self.btn_open = QPushButton("Apri Immagine Termica FLIR")
        self.btn_open.clicked.connect(self.open_image)
        self.left_layout.addWidget(self.btn_open)
        
        # Etichetta Immagine
        self.image_label = QLabel("Nessuna immagine caricata.")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("border: 1px solid gray; background-color: #333;")
        self.image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image_label.setMouseTracking(True)
        self.image_label.mouseMoveEvent = self.image_mouse_move
        self.left_layout.addWidget(self.image_label, stretch=1)

        # Tooltip per la temperatura
        self.temp_tooltip_label = QLabel("Temp: --.-- °C")
        self.temp_tooltip_label.setStyleSheet("background-color: black; color: white; padding: 4px; border-radius: 3px;")
        self.temp_tooltip_label.setVisible(False)
        self.temp_tooltip_label.setParent(self.image_label)

        # --- Colonna Destra (Parametri e Legenda) ---
        self.right_widget = QWidget()
        self.right_layout = QVBoxLayout(self.right_widget)
        self.main_layout.addWidget(self.right_widget, stretch=1)

        # Box per i parametri di calcolo
        self.params_groupbox = QGroupBox("Parametri di Calcolo")
        self.params_layout = QFormLayout(self.params_groupbox)
        self.param_inputs = {}
        param_keys = ["Emissivity", "ObjectDistance", "ReflectedApparentTemperature", "PlanckR1", "PlanckR2", "PlanckB", "PlanckF", "PlanckO"]
        for key in param_keys:
            line_edit = QLineEdit()
            line_edit.editingFinished.connect(self.update_analysis)
            self.param_inputs[key] = line_edit
            self.params_layout.addRow(key, self.param_inputs[key])
        self.right_layout.addWidget(self.params_groupbox)
        
        # Legenda
        self.legend_groupbox = QGroupBox("Legenda Temperatura (°C)")
        self.legend_layout = QVBoxLayout(self.legend_groupbox)
        self.legend_layout.setAlignment(Qt.AlignCenter)
        self.legend_label_max = QLabel("Max")
        self.legend_label_max.setAlignment(Qt.AlignCenter)
        self.legend_gradient = QLabel()
        self.legend_gradient.setMinimumHeight(200)
        self.legend_label_min = QLabel("Min")
        self.legend_label_min.setAlignment(Qt.AlignCenter)
        self.legend_layout.addWidget(self.legend_label_max)
        self.legend_layout.addWidget(self.legend_gradient, stretch=1)
        self.legend_layout.addWidget(self.legend_label_min)
        self.right_layout.addWidget(self.legend_groupbox)

        # Area Metadati Completi
        self.all_meta_display = QTextEdit("Tutti i metadati estratti appariranno qui.")
        self.all_meta_display.setReadOnly(True)
        self.right_layout.addWidget(self.all_meta_display)
        
    def open_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Seleziona Immagine FLIR", "", "Immagini JPEG (*.jpg *.jpeg)")
        if not file_path: return

        try:
            self.setWindowTitle(f"Analizzatore - {file_path.split('/')[-1]}")
            with exiftool.ExifTool() as et:
                json_string = et.execute(b"-json", file_path.encode())
                self.metadata = json.loads(json_string)[0]
                self.all_meta_display.setPlainText(json.dumps(self.metadata, indent=4, default=str))
            
            self.populate_params()

            command = ["exiftool", "-b", "-RawThermalImage", file_path]
            result = subprocess.run(command, capture_output=True, check=True)
            raw_thermal_bytes = result.stdout
            if not raw_thermal_bytes: raise ValueError("Dati termici binari non estratti.")

            image_type = self.metadata.get("APP1:RawThermalImageType", "Unknown")
            if image_type == "PNG":
                self.thermal_data = np.array(Image.open(io.BytesIO(raw_thermal_bytes)))
                
                # LA CORREZIONE FONDAMENTALE: Invertiamo l'ordine dei byte!
                # Le PNG di FLIR usano un ordine dei byte non standard (MSB).
                # NumPy lo legge nell'ordine nativo della macchina (LSB).
                # Dobbiamo invertirlo per ottenere i valori corretti.
                self.thermal_data.byteswap(inplace=True)

            else:
                width = self.metadata.get('APP1:RawThermalImageWidth')
                height = self.metadata.get('APP1:RawThermalImageHeight')
                if not width or not height: raise ValueError("Dimensioni immagine non trovate.")
                self.thermal_data = np.frombuffer(raw_thermal_bytes, dtype=np.uint16).reshape((height, width))

            self.update_analysis()
            QMessageBox.information(self, "Successo", "Immagine radiometrica caricata con successo!")

        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Impossibile processare il file:\n{e}")
            import traceback
            traceback.print_exc()

    def update_analysis(self):
        if self.thermal_data is None: return
        print(">>> Ricalcolo temperature e visualizzazione...")
        self.calculate_temperature_matrix()
        self.create_colored_pixmap()
        self.update_legend()
        self.display_thermal_image()

    def populate_params(self):
        if not self.metadata: return
        for key, line_edit in self.param_inputs.items():
            value = self.metadata.get(f"APP1:{key}", self.metadata.get(key, "N/A"))
            line_edit.setText(str(value))

    def calculate_temperature_matrix(self):
        try:
            emissivity = float(self.param_inputs["Emissivity"].text())
            refl_temp_C = float(self.param_inputs["ReflectedApparentTemperature"].text())
            R1 = float(self.param_inputs["PlanckR1"].text())
            R2 = float(self.param_inputs["PlanckR2"].text())
            B = float(self.param_inputs["PlanckB"].text())
            F = float(self.param_inputs["PlanckF"].text())
            O = float(self.param_inputs["PlanckO"].text())
            refl_temp_K = refl_temp_C + 273.15
            
            raw_refl = R1 / (R2 * (np.exp(B / refl_temp_K) - F)) - O
            raw_obj = (self.thermal_data - (1 - emissivity) * raw_refl) / emissivity
            
            log_arg = R1 / (R2 * (raw_obj + O)) + F
            temp_K = np.full(log_arg.shape, np.nan, dtype=np.float64)
            valid_indices = log_arg > 0
            temp_K[valid_indices] = B / np.log(log_arg[valid_indices])

            self.temperature_data = temp_K - 273.15
            self.temp_min = np.nanmin(self.temperature_data)
            self.temp_max = np.nanmax(self.temperature_data)
        except Exception as e:
            print(f"Errore calcolo temperature: {e}")
            self.temperature_data = np.zeros_like(self.thermal_data, dtype=float)
            self.temp_min, self.temp_max = 0, 0
    
    def create_colored_pixmap(self):
        if self.temperature_data is None: return
        
        # Normalizza i dati di temperatura da min/max a 0-1
        # Aggiungiamo un piccolo epsilon per evitare divisioni per zero se min=max
        temp_range = self.temp_max - self.temp_min
        if temp_range == 0: temp_range = 1 
        
        norm_data = (self.temperature_data - self.temp_min) / temp_range
        norm_data = np.nan_to_num(norm_data)

        colored_data = cm.inferno(norm_data)
        image_8bit = (colored_data[:, :, :3] * 255).astype(np.uint8)
        
        height, width, _ = image_8bit.shape
        q_image = QImage(image_8bit.data, width, height, width * 3, QImage.Format_RGB888)
        self.base_pixmap = QPixmap.fromImage(q_image)

    def update_legend(self):
        gradient_array = np.linspace(1, 0, 256).reshape(256, 1)
        gradient_colored = cm.inferno(gradient_array)
        gradient_8bit = (gradient_colored[:, :, :3] * 255).astype(np.uint8)
        
        h, w, _ = gradient_8bit.shape
        q_image = QImage(gradient_8bit.data, w, h, w * 3, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)
        
        self.legend_gradient.setPixmap(pixmap.scaled(self.legend_gradient.width(), self.legend_gradient.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
        self.legend_label_max.setText(f"{self.temp_max:.2f} °C")
        self.legend_label_min.setText(f"{self.temp_min:.2f} °C")
        
    def image_mouse_move(self, event):
        if self.temperature_data is None: return
        pos = event.position()
        label_size = self.image_label.size()
        pixmap_size = self.image_label.pixmap().size()
        if pixmap_size.width() == 0 or pixmap_size.height() == 0: return

        offset_x = (label_size.width() - pixmap_size.width()) / 2
        offset_y = (label_size.height() - pixmap_size.height()) / 2
        pix_x, pix_y = pos.x() - offset_x, pos.y() - offset_y
        
        img_h, img_w = self.temperature_data.shape
        matrix_x = int(pix_x * img_w / pixmap_size.width())
        matrix_y = int(pix_y * img_h / pixmap_size.height())

        if 0 <= matrix_x < img_w and 0 <= matrix_y < img_h:
            temperature = self.temperature_data[matrix_y, matrix_x]
            if not np.isnan(temperature):
                self.temp_tooltip_label.setText(f"{temperature:.2f} °C")
                self.temp_tooltip_label.move(int(pos.x()) + 10, int(pos.y()) + 10)
                self.temp_tooltip_label.setVisible(True)
                self.temp_tooltip_label.adjustSize()
            else:
                self.temp_tooltip_label.setVisible(False)
        else:
            self.temp_tooltip_label.setVisible(False)
        
    def display_thermal_image(self):
        if self.base_pixmap is None: return
        self.image_label.setPixmap(
            self.base_pixmap.scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.display_thermal_image()
        self.update_legend()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ThermalAnalyzerNG()
    window.show()
    sys.exit(app.exec())