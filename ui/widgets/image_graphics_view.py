from typing import Optional
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QWidget, QStyleOptionGraphicsItem
from PySide6.QtCore import Qt, QPointF, Signal, QRectF
from PySide6.QtGui import QPixmap, QPainter, QWheelEvent, QMouseEvent, QTransform


class BlendablePixmapItem(QGraphicsPixmapItem):
    """QGraphicsPixmapItem personalizzato che supporta blend modes."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._blend_mode = QPainter.CompositionMode_SourceOver
        
    def set_blend_mode(self, mode: QPainter.CompositionMode):
        """Imposta il blend mode per questo item."""
        self._blend_mode = mode
        self.update()
    
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        """Override del metodo paint per applicare il blend mode."""
        if self.pixmap().isNull():
            return
            
        # Salva lo stato corrente del painter
        old_composition_mode = painter.compositionMode()
        
        # Applica il blend mode
        painter.setCompositionMode(self._blend_mode)
        
        # Chiama il paint della classe base
        super().paint(painter, option, widget)
        
        # Ripristina lo stato del painter
        painter.setCompositionMode(old_composition_mode)


class ImageGraphicsView(QGraphicsView):
    """
    Vista custom basata su QGraphicsView per visualizzare e gestire immagini termiche
    con zoom, pan e overlay automatici.
    """
    
    # Segnali esistenti
    mouse_moved_on_thermal = Signal(QPointF)
    
    # Segnale aggiornato per includere dimensioni pixmap
    view_transformed = Signal(float, QPointF, tuple)  # zoom_factor, pan_offset, pixmap_size
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        # Configurazione base della vista
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # Inizializza la scena
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        
        # Items grafici per le immagini
        self._thermal_item = BlendablePixmapItem()  # <-- Usa la classe personalizzata
        self._visible_item = QGraphicsPixmapItem()
        
        # Aggiungi gli items alla scena (ordine importante: visibile sotto, termica sopra)
        self._scene.addItem(self._visible_item)
        self._scene.addItem(self._thermal_item)
        
        # Configurazione overlay
        self._overlay_mode = False
        self._overlay_alpha = 0.5
        self._overlay_scale = 1.0
        self._overlay_offset = QPointF(0, 0)
        self._blend_mode = QPainter.CompositionMode_SourceOver
        
        # Stato zoom e pan
        self._zoom_factor = 1.0
        self._min_zoom = 0.1
        self._max_zoom = 10.0
        self._pan_active = False
        
        self._is_sync_source = True  # Per evitare loop di sincronizzazione
        
        # Configurazione mouse tracking
        self.setMouseTracking(True)
        
    def set_thermal_pixmap(self, pixmap: QPixmap):
        """Imposta l'immagine termica."""
        if pixmap is None or pixmap.isNull():
            self._thermal_item.setPixmap(QPixmap())
            return
            
        self._thermal_item.setPixmap(pixmap)
        
        # Fit automatico sempre quando si imposta una nuova immagine
        if not self._overlay_mode:
            self._fit_thermal_in_view()
        else:
            self._update_overlay_positioning()
    
    def set_visible_pixmap(self, pixmap: QPixmap):
        """Imposta l'immagine visibile."""
        if pixmap is None or pixmap.isNull():
            self._visible_item.setPixmap(QPixmap())
            self._visible_item.setVisible(False)
            return
            
        self._visible_item.setPixmap(pixmap)
        # Non impostare automaticamente visible qui, lo gestisce update_overlay
        
        # Se siamo in modalità overlay, aggiorna il posizionamento
        if self._overlay_mode:
            self._update_overlay_positioning()

    def update_overlay(self, visible: bool, alpha: float = 0.5, scale: float = 1.0, 
                      offset: QPointF = QPointF(0, 0), blend_mode: QPainter.CompositionMode = None):
        """Aggiorna le impostazioni dell'overlay."""
        self._overlay_mode = visible
        self._overlay_alpha = max(0.0, min(1.0, alpha))
        self._overlay_scale = max(0.1, min(5.0, scale))
        self._overlay_offset = offset
        
        if blend_mode is not None:
            self._blend_mode = blend_mode
            # Applica il blend mode all'item termico
            self._thermal_item.set_blend_mode(blend_mode)
        
        if self._overlay_mode:
            # In modalità overlay, mostra entrambe le immagini se disponibili
            self._visible_item.setVisible(not self._visible_item.pixmap().isNull())
            self._thermal_item.setVisible(not self._thermal_item.pixmap().isNull())
            self._thermal_item.setOpacity(self._overlay_alpha)
            
            # Assicurati che l'ordine Z sia corretto (visibile sotto, termica sopra)
            self._visible_item.setZValue(0)
            self._thermal_item.setZValue(1)
            
            self._update_overlay_positioning()
        else:
            # In modalità normale, mostra solo la termica
            self._visible_item.setVisible(False)
            self._thermal_item.setVisible(not self._thermal_item.pixmap().isNull())
            self._thermal_item.setOpacity(1.0)
            # Ripristina blend mode normale quando non in overlay
            self._thermal_item.set_blend_mode(QPainter.CompositionMode_SourceOver)
            self._fit_thermal_in_view()

    def _fit_thermal_in_view(self):
        """Adatta l'immagine termica alla vista quando non in modalità overlay."""
        if self._thermal_item.pixmap().isNull():
            return
        
        # Reset della trasformazione dell'item
        self._thermal_item.setTransform(QTransform())
        
        # Posiziona l'immagine termica al centro della scena
        thermal_rect = self._thermal_item.boundingRect()
        self._thermal_item.setPos(-thermal_rect.width()/2, -thermal_rect.height()/2)
        
        # Reset della vista e fit dell'immagine
        self.resetTransform()
        self.fitInView(self._thermal_item, Qt.KeepAspectRatio)
        self._zoom_factor = self.transform().m11()
    
    def _update_overlay_positioning(self):
        """Aggiorna il posizionamento delle immagini in modalità overlay."""
        if not self._overlay_mode:
            return
        
        # Reset delle trasformazioni
        self._visible_item.setTransform(QTransform())
        self._thermal_item.setTransform(QTransform())
        
        # Posiziona l'immagine visibile al centro della scena
        if not self._visible_item.pixmap().isNull():
            visible_rect = self._visible_item.boundingRect()
            self._visible_item.setPos(-visible_rect.width()/2, -visible_rect.height()/2)
            
            # Reset della vista e fit dell'immagine visibile
            self.resetTransform()
            self.fitInView(self._visible_item, Qt.KeepAspectRatio)
            self._zoom_factor = self.transform().m11()
        
        # Posiziona e scala l'immagine termica relativa alla visibile
        if not self._thermal_item.pixmap().isNull():
            if not self._visible_item.pixmap().isNull():
                # Calcola la scala relativa basata sulle dimensioni reali delle immagini
                thermal_pixmap = self._thermal_item.pixmap()
                visible_pixmap = self._visible_item.pixmap()
                
                # Dimensioni originali
                thermal_width = thermal_pixmap.width()
                thermal_height = thermal_pixmap.height()
                visible_width = visible_pixmap.width()
                visible_height = visible_pixmap.height()
                
                # Calcola il rapporto di scala "naturale" se le immagini fossero della stessa dimensione
                natural_scale_x = visible_width / thermal_width if thermal_width > 0 else 1.0
                natural_scale_y = visible_height / thermal_height if thermal_height > 0 else 1.0
                natural_scale = min(natural_scale_x, natural_scale_y)
                
                # Applica la scala dell'utente moltiplicata per la scala naturale
                final_scale = self._overlay_scale * natural_scale
                
                # Applica la trasformazione
                transform = QTransform()
                transform.scale(final_scale, final_scale)
                self._thermal_item.setTransform(transform)
                
                # Calcola gli offset in coordinate della scena
                thermal_rect = self._thermal_item.boundingRect()
                scaled_thermal_rect = transform.mapRect(thermal_rect)
                
                # Gli offset sono forniti in pixel dell'immagine visibile originale
                # Dobbiamo convertirli in coordinate della scena
                visible_rect = self._visible_item.boundingRect()
                
                # Calcola il rapporto tra le dimensioni dell'item nella scena e l'immagine originale
                scale_x = visible_rect.width() / visible_width
                scale_y = visible_rect.height() / visible_height
                
                # Converti gli offset da pixel dell'immagine visibile a coordinate scena
                offset_x_scene = self._overlay_offset.x() * scale_x
                offset_y_scene = self._overlay_offset.y() * scale_y
                
                # Posiziona l'immagine termica centrata più l'offset
                pos_x = -scaled_thermal_rect.width()/2 + offset_x_scene
                pos_y = -scaled_thermal_rect.height()/2 + offset_y_scene
                
                self._thermal_item.setPos(pos_x, pos_y)
            else:
                # Se non c'è immagine visibile, centra la termica
                transform = QTransform()
                transform.scale(self._overlay_scale, self._overlay_scale)
                self._thermal_item.setTransform(transform)
                
                thermal_rect = self._thermal_item.boundingRect()
                scaled_thermal_rect = transform.mapRect(thermal_rect)
                self._thermal_item.setPos(-scaled_thermal_rect.width()/2, -scaled_thermal_rect.height()/2)
                
                # Se non c'è visibile, fit sulla termica scalata
                self.resetTransform()
                self.fitInView(self._thermal_item, Qt.KeepAspectRatio)
                self._zoom_factor = self.transform().m11()
    
    def zoom_in(self, factor: float = 1.2):
        """Zoom in con fattore specificato."""
        new_zoom = self._zoom_factor * factor
        if new_zoom <= self._max_zoom:
            self.scale(factor, factor)
            self._zoom_factor = new_zoom
    
    def zoom_out(self, factor: float = 1.2):
        """Zoom out con fattore specificato."""
        new_zoom = self._zoom_factor / factor
        if new_zoom >= self._min_zoom:
            self.scale(1/factor, 1/factor)
            self._zoom_factor = new_zoom
    
    def reset_zoom(self):
        """Reset del zoom e pan."""
        self.resetTransform()
        self._zoom_factor = 1.0
        
        if self._overlay_mode:
            self._update_overlay_positioning()
        else:
            self._fit_thermal_in_view()
    
    def sync_transform(self, zoom_factor: float, pan_offset: QPointF, source_pixmap_size: tuple = None):
        """Sincronizza questa vista con un'altra, considerando le dimensioni relative delle immagini."""
        self._is_sync_source = False  # Evita loop
        
        # Se abbiamo informazioni sulla dimensione dell'immagine sorgente, 
        # calcoliamo un fattore di correzione
        scale_correction = 1.0
        if source_pixmap_size is not None and not self._thermal_item.pixmap().isNull():
            source_w, source_h = source_pixmap_size
            current_pixmap = self._thermal_item.pixmap()
            current_w, current_h = current_pixmap.width(), current_pixmap.height()
            
            # Calcola il rapporto tra le dimensioni delle due immagini
            # Questo ci dice quanto più grande/piccola è l'immagine corrente rispetto alla sorgente
            scale_ratio_x = current_w / source_w if source_w > 0 else 1.0
            scale_ratio_y = current_h / source_h if source_h > 0 else 1.0
            
            # Usa il rapporto più piccolo per mantenere l'aspect ratio
            scale_correction = min(scale_ratio_x, scale_ratio_y)
        
        # Applica zoom con correzione della scala
        corrected_zoom = zoom_factor * scale_correction
        scale_factor = corrected_zoom / self._zoom_factor
        
        if abs(scale_factor - 1.0) > 0.001:  # Evita micro-aggiustamenti
            self.scale(scale_factor, scale_factor)
            self._zoom_factor = corrected_zoom
            
        # Applica pan (potrebbe anche aver bisogno di correzione in futuro)
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
        """Ritorna le dimensioni del pixmap corrente."""
        if not self._thermal_item.pixmap().isNull():
            pixmap = self._thermal_item.pixmap()
            return (pixmap.width(), pixmap.height())
        return (1, 1)  # Fallback per evitare divisioni per zero

    def wheelEvent(self, event: QWheelEvent):
        """Gestione zoom con rotella del mouse."""
        if event.modifiers() == Qt.ControlModifier:
            # Zoom con Ctrl + rotella
            angle_delta = event.angleDelta().y()
            factor = 1.2 if angle_delta > 0 else 1/1.2
            
            if angle_delta > 0:
                self.zoom_in(factor)
            else:
                self.zoom_out(factor)
            
            # Emetti segnale di trasformazione con informazioni sulla dimensione
            if self._is_sync_source:
                pixmap_size = self.get_current_pixmap_size()
                self.view_transformed.emit(self._zoom_factor, self.get_pan_offset(), pixmap_size)
            
            event.accept()
        else:
            # Pan con rotella semplice
            super().wheelEvent(event)
            if self._is_sync_source:
                pixmap_size = self.get_current_pixmap_size()
                self.view_transformed.emit(self._zoom_factor, self.get_pan_offset(), pixmap_size)

    def mousePressEvent(self, event: QMouseEvent):
        """Gestione click del mouse."""
        if event.button() == Qt.MiddleButton:
            # Pan con tasto centrale
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self._pan_active = True
        
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """Gestione rilascio del mouse."""
        if event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.RubberBandDrag)
            self._pan_active = False
        
        super().mouseReleaseEvent(event)
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """Gestione movimento del mouse per tooltip temperatura e sincronizzazione pan."""
        super().mouseMoveEvent(event)
        
        # Emetti segnale se è cambiato il pan
        if self._pan_active and self._is_sync_source:
            pixmap_size = self.get_current_pixmap_size()
            self.view_transformed.emit(self._zoom_factor, self.get_pan_offset(), pixmap_size)
        
        # Calcola le coordinate sulla mappa termica
        if not self._thermal_item.pixmap().isNull():
            scene_pos = self.mapToScene(event.pos())
            thermal_pos = self._thermal_item.mapFromScene(scene_pos)
            
            # Converti in coordinate dell'immagine originale
            thermal_rect = self._thermal_item.boundingRect()
            if thermal_rect.contains(thermal_pos):
                # Normalizza le coordinate (0-1)
                norm_x = thermal_pos.x() / thermal_rect.width()
                norm_y = thermal_pos.y() / thermal_rect.height()
                
                # Converti in pixel dell'immagine originale
                original_pixmap = self._thermal_item.pixmap()
                pixel_x = norm_x * original_pixmap.width()
                pixel_y = norm_y * original_pixmap.height()
                
                # Emetti il segnale con le coordinate
                self.mouse_moved_on_thermal.emit(QPointF(pixel_x, pixel_y))
    
    def get_zoom_factor(self) -> float:
        """Ritorna il fattore di zoom corrente."""
        return self._zoom_factor
    
    def get_overlay_settings(self) -> dict:
        """Ritorna le impostazioni correnti dell'overlay."""
        return {
            'mode': self._overlay_mode,
            'alpha': self._overlay_alpha,
            'scale': self._overlay_scale,
            'offset': self._overlay_offset,
            'blend_mode': self._blend_mode
        }

    def get_scale_info(self) -> dict:
        """Ritorna informazioni dettagliate sulle scale per debug."""
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
            
            # Calcola gli offset convertiti
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
        """Ritorna l'offset corrente del pan."""
        transform = self.transform()
        return QPointF(transform.dx(), transform.dy())
        