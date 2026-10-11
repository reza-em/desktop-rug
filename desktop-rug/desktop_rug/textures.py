"""Rug textures: front (pile side, fringe stripped) and the woven back side."""
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QImage, QPainter, QColor, QPen


def opaque_rect(img: QImage) -> QRect:
    """Rug body without the transparent fringe area of the built-in image."""
    w, h = img.width(), img.height()
    if not img.hasAlphaChannel() or w < 4 or h < 4:
        return img.rect()

    def scan(n, get):
        lo = next((i for i in range(n) if get(i) > 250), 0)
        hi = next((i for i in range(n - 1, -1, -1) if get(i) > 250), n - 1)
        return lo, hi
    l, r = scan(w, lambda i: img.pixelColor(i, h // 2).alpha())
    t, b = scan(h, lambda i: img.pixelColor(w // 2, i).alpha())
    return QRect(l, t, r - l + 1, b - t + 1)


def front_texture(img: QImage, max_side=2048) -> QImage:
    body = img.copy(opaque_rect(img)).convertToFormat(QImage.Format_ARGB32)
    if max(body.width(), body.height()) > max_side:
        body = body.scaled(max_side, max_side, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    # make it fully opaque (custom images with alpha would otherwise show holes)
    out = QImage(body.size(), QImage.Format_ARGB32)
    out.fill(QColor(120, 30, 30))
    p = QPainter(out)
    p.drawImage(0, 0, body)
    p.end()
    return out


def back_texture(front: QImage) -> QImage:
    """Back of a hand-knotted rug: the same design, flatter and duller, with the
    warp/weft grid and knot rows clearly visible."""
    w, h = front.width(), front.height()
    small = front.scaled(max(1, w // 2), max(1, h // 2), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    back = small.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(QImage.Format_ARGB32)
    p = QPainter(back)
    p.fillRect(back.rect(), QColor(150, 125, 100, 95))     # desaturate towards undyed wool
    p.fillRect(back.rect(), QColor(20, 10, 5, 55))
    step = max(3, w // 420)
    p.setPen(QPen(QColor(250, 240, 220, 40), 1))
    for x in range(0, w, step):
        p.drawLine(x, 0, x, h)
    p.setPen(QPen(QColor(0, 0, 0, 45), 1))
    for y in range(0, h, step):
        p.drawLine(0, y, w, y)
    p.setPen(QPen(QColor(0, 0, 0, 28), 1))
    for y in range(step // 2, h, step * 2):
        p.drawLine(0, y, w, y)
    p.end()
    return back
