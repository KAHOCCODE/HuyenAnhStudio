"""Direct composition editing on a still frame, using the export crop geometry."""
import math
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QImage, QPainter, QColor, QPen
from PySide6.QtWidgets import QWidget
from .video_effects import settings, SIZES


class FrameEditor(QWidget):
    edited = Signal(float, float, float)

    def __init__(self, image=None, source_size=(1920, 1080), parent=None):
        super().__init__(parent)
        self.image = image.copy() if image is not None else QImage()
        self.source_size = source_size
        self.values = settings({})
        self.drag = None
        self.setMinimumSize(240, 220)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip('Kéo hình để đổi bố cục. Cuộn chuột hoặc kéo ô vuông ở góc để zoom. Nhấp đúp để về giữa.')

    def set_values(self, values):
        self.values = dict(values)
        self.update()

    def geometry_data(self):
        v = self.values
        sw, sh = self.source_size
        ow, oh = (sw, sh) if v['size'] == 'source' else (
            (v['width'], v['height']) if v['size'] == 'custom' else SIZES[v['size']])
        ow, oh = max(2, ow), max(2, oh)
        screen_scale = min(max(1, self.width()-36)/ow, max(1, self.height()-36)/oh)
        canvas = QRectF((self.width()-ow*screen_scale)/2, (self.height()-oh*screen_scale)/2,
                        ow*screen_scale, oh*screen_scale)
        cw = max(2, math.floor(sw/v['zoom']/2)*2) if v['zoom'] != 1 else sw
        ch = max(2, math.floor(sh/v['zoom']/2)*2) if v['zoom'] != 1 else sh
        sx, sy = (sw-cw)*v['x']/100, (sh-ch)*v['y']/100
        fw, fh = ow, oh
        if v['layout'] in ('blur', 'frame'):
            fw = max(2, int(ow*(1-2*v['inset']/100))//2*2)
            fh = max(2, int(oh*(1-2*v['inset']/100))//2*2)
        factor = (max if v['layout'] == 'crop' else min)(fw/cw, fh/ch)
        dw, dh = cw*factor, ch*factor
        dest = QRectF(canvas.x()+(ow-dw)*v['x']/100*screen_scale,
                      canvas.y()+(oh-dh)*v['y']/100*screen_scale,
                      dw*screen_scale, dh*screen_scale)
        # Motion of a source pixel with respect to normalized X/Y includes
        # both the inner zoom crop and the outer fit/crop placement.
        motion = (((ow-dw)-(sw-cw)*factor)*screen_scale,
                  ((oh-dh)-(sh-ch)*factor)*screen_scale)
        return canvas, dest, QRectF(sx, sy, cw, ch), motion

    def handles(self):
        canvas = self.geometry_data()[0]
        return [QRectF(point.x()-6, point.y()-6, 12, 12) for point in
                (canvas.topLeft(), canvas.topRight(), canvas.bottomLeft(), canvas.bottomRight())]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#080e17'))
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        canvas, dest, crop, _ = self.geometry_data()
        v = self.values
        painter.fillRect(canvas, QColor(v['background']))
        if self.image.isNull():
            painter.setPen(QColor('#d5e0ef'))
            painter.drawText(canvas, Qt.AlignCenter | Qt.TextWordWrap,
                             'Chọn video và dừng ở khung hình muốn chỉnh, rồi mở lại cửa sổ này.')
        else:
            image = self.image.mirrored(True, False) if v['flip'] else self.image
            sw, sh = self.source_size
            source = QRectF(crop.x()*image.width()/sw, crop.y()*image.height()/sh,
                            crop.width()*image.width()/sw, crop.height()*image.height()/sh)
            painter.save(); painter.setClipRect(canvas)
            if v['layout'] in ('blur', 'frame'):
                # Reduced texture is only a quick layout approximation of export blur.
                blurred = image.scaled(24, 24, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                painter.drawImage(canvas, blurred)
                painter.fillRect(canvas, QColor(0, 0, 0, 70))
            painter.drawImage(dest, image, source)
            if v['layout'] == 'frame':
                painter.setPen(QPen(QColor(v['border']), 3)); painter.drawRect(canvas.adjusted(2, 2, -2, -2))
            painter.restore()
        painter.setPen(QPen(QColor('#64dfce'), 1, Qt.DashLine))
        for f in (1/3, 2/3):
            painter.drawLine(QPointF(canvas.x()+canvas.width()*f, canvas.top()), QPointF(canvas.x()+canvas.width()*f, canvas.bottom()))
            painter.drawLine(QPointF(canvas.left(), canvas.y()+canvas.height()*f), QPointF(canvas.right(), canvas.y()+canvas.height()*f))
        painter.setPen(QPen(QColor('#64dfce'), 2)); painter.drawRect(canvas)
        for handle in self.handles(): painter.fillRect(handle, QColor('#64dfce'))

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton: return
        canvas = self.geometry_data()[0]
        point = event.position()
        handle = any(r.contains(point) for r in self.handles())
        if not handle and not canvas.contains(point): return
        self.drag = (point, dict(self.values), handle, self.geometry_data()[3])
        self.setCursor(Qt.SizeFDiagCursor if handle else Qt.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):
        if self.drag is None:
            self.setCursor(Qt.SizeFDiagCursor if any(r.contains(event.position()) for r in self.handles()) else Qt.OpenHandCursor)
            return
        start, values, handle, motion = self.drag
        delta = event.position()-start
        x, y, z = values['x'], values['y'], values['zoom']
        if handle:
            center = self.geometry_data()[0].center()
            a, b = start-center, event.position()-center
            z *= math.hypot(b.x(), b.y())/max(1, math.hypot(a.x(), a.y()))
        else:
            if abs(motion[0]) > .5: x += delta.x()/motion[0]*100
            if abs(motion[1]) > .5: y += delta.y()/motion[1]*100
        self.edited.emit(max(0, min(100, x)), max(0, min(100, y)), max(1, min(3, z)))
        event.accept()

    def mouseReleaseEvent(self, event):
        self.drag = None
        self.setCursor(Qt.OpenHandCursor)
        event.accept()

    def wheelEvent(self, event):
        if not self.geometry_data()[0].contains(event.position()):
            event.ignore(); return
        z = max(1, min(3, self.values['zoom'] + event.angleDelta().y()/120*.05))
        self.edited.emit(self.values['x'], self.values['y'], z)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.edited.emit(50, 50, self.values['zoom'])
            event.accept()
