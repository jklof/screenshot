import sys
import os
import argparse
from datetime import datetime
from pathlib import Path
from io import BytesIO
import requests
import webbrowser
import keyboard
import threading
from PyQt5.QtWidgets import QApplication, QMainWindow, QRubberBand, QSystemTrayIcon, QMenu, QAction, QActionGroup
from PyQt5.QtCore import QObject, QRect, Qt, pyqtSignal, QBuffer, QByteArray, QPoint
from PyQt5.QtGui import QPixmap, QIcon, QCursor, QColor, QPainter, QPen


class Uploader(QObject):
    uploadedsignal = pyqtSignal(str)

    def __init__(self, save_dir=None):
        super().__init__()
        self.save_dir = save_dir
        self.uploading = False
        self.queue = []
        self.condition = threading.Condition()
        self.thread = threading.Thread(target=self._process_queue, daemon=True)
        self.thread.start()

    def set_save_dir(self, dir):
        with self.condition:
            self.save_dir = dir

    def get_save_dir(self):
        with self.condition:
            return self.save_dir

    def stop(self):
        with self.condition:
            self.queue.insert(0,None)
            self.condition.notify()
        self.thread.join(timeout=15.0)

    def enqueue(self, image):
        with self.condition:
            self.queue.append(image)
            self.condition.notify()

    def dequeue(self):
        with self.condition:
            while not self.queue:
                self.condition.wait()
            return self.queue.pop(0)


    def save(self, buffer, save_dir):
        try:
            os.makedirs(save_dir, exist_ok=True)
            path = Path(save_dir) / f'screenshot_{datetime.now():%Y%m%d_%H%M%S}.png'
            with open(path, 'wb') as f:
                f.write(buffer.getvalue())
            return path.as_uri()
        except Exception as e:
            print(f"Save failed: {e}")
            return None

    def upload(self, buffer):
        try:
            response = requests.post(
                'https://uguu.se/upload?output=json',
                files={'files[]': ('screenshot.png', buffer, 'image/png')},
                timeout=10
            )
            response.raise_for_status()
            return response.json().get("files", [{}])[0].get("url")
        except Exception as e:
            print(f"Upload failed: {e}")
            return None

    def to_png(self, image):
        qbytearray = QByteArray()
        qbuffer = QBuffer(qbytearray)
        qbuffer.open(QBuffer.WriteOnly)
        image.save(qbuffer, "PNG")
        qbuffer.close()
        return BytesIO(qbytearray.data())


    def _process_queue(self):
        while (image := self.dequeue()) is not None:
            png_buffer = self.to_png(image)
            save_dir = self.get_save_dir()
            uri = self.save(png_buffer,save_dir) if save_dir else self.upload(png_buffer)
            self.uploadedsignal.emit(uri)


def create_icon(size=256):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.white)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(40, 40, 40), max(1, size // 12), Qt.SolidLine, Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(QColor(77, 169, 255))
    circle_margin = size // 4
    circle_size = size - circle_margin * 2
    painter.drawEllipse(circle_margin, circle_margin, circle_size, circle_size)
    painter.end()
    return QIcon(pixmap)


class ScreenCapture(QMainWindow):
    hotkey_triggered = pyqtSignal()

    def __init__(self, save_dir=None):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setWindowOpacity(0.3)
        self.save_dir = save_dir
        self.aspect_ratio = None
        self.start_pos = None
        self.rubber_band = QRubberBand(QRubberBand.Rectangle, self)
        self.uploader = Uploader(save_dir)
        self.uploader.uploadedsignal.connect(self._upload_success)
        self.tray = QSystemTrayIcon(create_icon(), self)
        self._setup_tray()
        keyboard.add_hotkey('ctrl+shift+k', lambda: self.hotkey_triggered.emit(), suppress=True)
        self.hotkey_triggered.connect(self._start_capture)

    def _setup_tray(self):

        menu = QMenu()

        # Add aspect ratio submenu
        aspect_menu = menu.addMenu("Aspect Ratio")
        ratios = {
            "Free": None,
            "1:1": 1.0,
            "4:3": 4/3,
            "16:9": 16/9,
            "2:3": 2/3,
            "3:2": 3/2
        }
        # Create action group to make radio-button behavior
        action_group = QActionGroup(self)
        action_group.setExclusive(True)
        
        # Add actions to both group and menu
        for name, ratio in ratios.items():
            action = QAction(name, self)
            action.setCheckable(True)
            action.setChecked(ratio == self.aspect_ratio)  # Check "Free" by default
            action.triggered.connect(lambda _, r=ratio: self._set_aspect_ratio(r))
            action_group.addAction(action)
            aspect_menu.addAction(action)

        menu.addSeparator()

        for i, screen in enumerate(QApplication.screens()):
            action = menu.addAction(f"Screen {i + 1} - {screen.geometry().width()}x{screen.geometry().height()}")
            action.triggered.connect(lambda _, s=screen: self._start_capture(s))


        if self.save_dir:
            menu.addSeparator()
            action = QAction("Uploading", self)
            action.setCheckable(True)
            action.setChecked( self.uploader.get_save_dir() is None )
            menu.addAction(action)
            action.toggled.connect(lambda isChecked : self.uploader.set_save_dir(None if isChecked else self.save_dir))

        menu.addSeparator()
        menu.addAction("Exit", self._exit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self._start_capture() if reason == QSystemTrayIcon.Trigger else None)
        self.tray.show()

    def _set_aspect_ratio(self, ratio):
        self.aspect_ratio = ratio

    def _calculate_constrained_rect(self, start_pos, current_pos):
        if self.aspect_ratio is None:
            return QRect(start_pos, current_pos).normalized()

        dx = current_pos.x() - start_pos.x()
        dy = current_pos.y() - start_pos.y()
        
        # Calculate width and height based on aspect ratio
        if abs(dx) * abs(self.aspect_ratio) > abs(dy):
            # Width is dominant
            width = dx
            height = int(abs(width) / self.aspect_ratio * (1 if dy >= 0 else -1))
        else:
            # Height is dominant
            height = dy
            width = int(abs(height) * self.aspect_ratio * (1 if dx >= 0 else -1))

        return QRect(
            start_pos,
            start_pos + QPoint(width, height)
        ).normalized()

    def _start_capture(self, screen=None):
        screen = screen or QApplication.screenAt(QCursor.pos())
        if screen:
            self.setGeometry(screen.geometry())
            self.rubber_band.hide()
            self.showFullScreen()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
            self.rubber_band.hide()

    def mousePressEvent(self, event):
        self.start_pos = self.last_pos = event.pos()
        self.rubber_band.setGeometry(QRect(self.start_pos, self.last_pos))
        self.rubber_band.show()

    def mouseMoveEvent(self, event):
        if self.rubber_band.isVisible():
            if QApplication.keyboardModifiers() == Qt.ShiftModifier:
                offset = event.pos() - self.last_pos
                self.start_pos += offset
            self.last_pos = event.pos()
            self.rubber_band.setGeometry(self._calculate_constrained_rect(self.start_pos, self.last_pos))

    def mouseReleaseEvent(self, event):
        self.mouseMoveEvent(event)
        if self.rubber_band.isVisible():
            self._capture(self.rubber_band.geometry())

    def _capture(self, geometry):
        self.hide()
        self.rubber_band.hide()
        QApplication.processEvents()
        if geometry.topLeft() != geometry.bottomRight():
            screen = QApplication.screenAt(self.geometry().topLeft())
            screenshot = screen.grabWindow(0,geometry.x(),geometry.y(),geometry.width(),geometry.height())
            self.uploader.enqueue(screenshot)

    def _upload_success(self, uri):
        if uri:
            QApplication.clipboard().setText(uri) 
            webbrowser.open(uri)
            self.tray.showMessage("Upload Successful", uri)
        else:
            self.tray.showMessage("Upload Failed", "Could not upload screenshot")

    def _exit(self):
        self.uploader.stop()
        QApplication.quit()


def main():
    parser = argparse.ArgumentParser(description="Screenshot capture tool")
    parser.add_argument('--save-dir', type=str, help="Save screenshots locally instead of uploading")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    ScreenCapture(save_dir=args.save_dir)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()