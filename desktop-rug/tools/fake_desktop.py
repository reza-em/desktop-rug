#!/usr/bin/env python3
"""Test helper: a fake 'desktop' (wood wallpaper + draggable file icons) that is
registered as _NET_WM_WINDOW_TYPE_DESKTOP, so Desktop Rug can be tested on a
headless X server (Xvfb + compositing WM). Logs clicks/drags to stdout."""
import subprocess, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QImage
from PySide6.QtWidgets import QApplication, QWidget
from desktop_rug.preview import wood_background, draw_fake_icons

LABELS = ["projects", "final-final-v2.docx", "blurry-pigeon.jpg", "taxes.pdf", "screenshot.png",
          "notes.txt", "weekend.mov", "invoice.pdf"]


class Desk(QWidget):
    def __init__(self, w, h):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.resize(w, h)
        self.move(0, 0)
        self.bg = wood_background(w, h)
        self.icons = [[1010.0 + (i % 2) * 110, 120.0 + (i // 2) * 105] for i in range(8)]
        self.drag = None

    def paintEvent(self, e):
        img = QImage(self.bg)
        draw_fake_icons(img, [tuple(i) for i in self.icons], LABELS)
        p = QPainter(self)
        p.drawImage(0, 0, img)

    def mousePressEvent(self, e):
        pos = e.position()
        print("DESKTOP_CLICK %d %d" % (pos.x(), pos.y()), flush=True)
        for i, (x, y) in enumerate(self.icons):
            if abs(pos.x() - x) < 30 and abs(pos.y() - y) < 35:
                self.drag = (i, pos.x() - x, pos.y() - y)

    def mouseMoveEvent(self, e):
        if self.drag:
            i, dx, dy = self.drag
            self.icons[i] = [e.position().x() - dx, e.position().y() - dy]
            self.update()

    def mouseReleaseEvent(self, e):
        if self.drag:
            i = self.drag[0]
            print("DESKTOP_ICON_MOVED %s -> %d %d" % (LABELS[i], *self.icons[i]), flush=True)
            open("/tmp/fake_icons.txt", "w").write(";".join("%d,%d" % tuple(map(int, p)) for p in self.icons))
        self.drag = None


app = QApplication(sys.argv)
scr = app.primaryScreen().geometry()
d = Desk(scr.width(), scr.height())
wid = int(d.winId())
subprocess.call(["xprop", "-id", str(wid), "-f", "_NET_WM_WINDOW_TYPE", "32a", "-set",
                 "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_DESKTOP"])
d.show()
print("FAKE_DESKTOP_READY", flush=True)
app.exec()
