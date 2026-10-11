"""Software fallback renderer (QPainter only, no OpenGL): affine-textured
triangles of a down-sampled mesh, painter's-algorithm sorted by height, flat
per-triangle lighting, simple soft shadow. Slower and less pretty than the
OpenGL path, but works everywhere (VMs, Wine without GL, remote desktops)."""
import math
import numpy as np
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QImage, QPainter, QPolygonF, QTransform, QColor, QPainterPath, QPen

LIGHT = np.array([-0.32, -0.45, 1.0]) / np.linalg.norm([-0.32, -0.45, 1.0])


class SoftRenderer:
    name = "software"
    ok = True
    error = ""
    info = "QPainter software renderer"

    def __init__(self, step=2):
        self.step = step
        self.front = self.back = None

    def set_textures(self, front: QImage, back: QImage):
        self.front = front.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        self.back = back.convertToFormat(QImage.Format_ARGB32_Premultiplied)

    def render(self, cloth, ox, oy, w, h, dpr=1.0, normals=None):
        img = QImage(max(1, int(w * dpr)), max(1, int(h * dpr)), QImage.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(Qt.transparent)
        s = self.step
        P = cloth.P[::s, ::s]
        if (cloth.ny - 1) % s:
            P = np.concatenate([P, cloth.P[-1:, ::s]], 0)
        if (cloth.nx - 1) % s:
            col = cloth.P[::s, -1:]
            if (cloth.ny - 1) % s:
                col = np.concatenate([col, cloth.P[-1:, -1:]], 0)
            P = np.concatenate([P, col], 1)
        ny, nx = P.shape[:2]
        uvs = np.stack(np.meshgrid(np.linspace(0, 1, nx), np.linspace(0, 1, ny)), -1)
        X = P[..., 0] - ox
        Y = P[..., 1] - oy
        Z = P[..., 2]
        p = QPainter(img)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        # --- shadow
        path = QPainterPath()
        path.setFillRule(Qt.WindingFill)
        sx = X + Z * 0.33 + 1.5
        sy = Y + Z * 0.48 + 2.5
        for j in range(ny - 1):
            for i in range(nx - 1):
                path.addPolygon(QPolygonF([QPointF(sx[j, i], sy[j, i]), QPointF(sx[j, i + 1], sy[j, i + 1]),
                                           QPointF(sx[j + 1, i + 1], sy[j + 1, i + 1]), QPointF(sx[j + 1, i], sy[j + 1, i])]))
        p.setRenderHint(QPainter.Antialiasing, True)
        for k, (dx, dy, a) in enumerate(((0, 0, 70), (1.5, 1.5, 35), (-1.2, 2.5, 25))):
            p.fillPath(path.translated(dx, dy), QColor(0, 0, 0, a))
        p.setRenderHint(QPainter.Antialiasing, False)
        # --- triangles, low to high
        tris = []
        for j in range(ny - 1):
            for i in range(nx - 1):
                a, b, c, d = (j, i), (j, i + 1), (j + 1, i + 1), (j + 1, i)
                tris.append((a, b, d))
                tris.append((b, c, d))
        zs = np.array([Z[t[0]] + Z[t[1]] + Z[t[2]] for t in tris])
        order = np.argsort(zs, kind="stable")
        fw, fh = self.front.width(), self.front.height()
        for k in order:
            t = tris[k]
            pts = [(X[q], Y[q]) for q in t]
            area = (pts[1][0] - pts[0][0]) * (pts[2][1] - pts[0][1]) - (pts[2][0] - pts[0][0]) * (pts[1][1] - pts[0][1])
            if abs(area) < 1e-3:
                continue
            front = area > 0
            tex = self.front if front else self.back
            uv = [(uvs[q][0] * fw, uvs[q][1] * fh) for q in t]
            T = _affine(uv, pts)
            if T is None:
                continue
            cx = sum(x for x, _ in pts) / 3
            cy = sum(y for _, y in pts) / 3
            grow = [(x + (x - cx) * 0.06 + math.copysign(0.4, x - cx), y + (y - cy) * 0.06 + math.copysign(0.4, y - cy)) for x, y in pts]
            poly = QPolygonF([QPointF(x, y) for x, y in grow])
            clip = QPainterPath()
            clip.addPolygon(poly)
            p.save()
            p.setClipPath(clip)
            p.setTransform(T)
            p.drawImage(0, 0, tex)
            p.restore()
            # flat lighting
            P3 = [np.array([X[q], Y[q], Z[q]]) for q in t]
            n = np.cross(P3[1] - P3[0], P3[2] - P3[0])
            nl = np.linalg.norm(n)
            if nl > 0:
                n = n / nl
                if n[2] < 0:
                    n = -n
                lit = 0.30 + 0.80 * max(0.0, float(n @ LIGHT))
                if lit < 1.0:
                    p.fillPath(clip, QColor(0, 0, 0, int(min(200, (1 - lit) * 255))))
                else:
                    p.fillPath(clip, QColor(255, 250, 235, int(min(90, (lit - 1) * 255))))
        # --- fringe
        p.setRenderHint(QPainter.Antialiasing, True)
        F = cloth.fr_P
        pen = QPen(QColor(236, 224, 194), 1.4)
        p.setPen(pen)
        for e in range(F.shape[0]):
            for sidx in range(F.shape[1]):
                pts = F[e, sidx]
                for k2 in range(F.shape[2] - 1):
                    p.drawLine(QPointF(pts[k2, 0] - ox, pts[k2, 1] - oy), QPointF(pts[k2 + 1, 0] - ox, pts[k2 + 1, 1] - oy))
        p.end()
        return img


def _affine(src, dst):
    """QTransform mapping 3 src points onto 3 dst points."""
    (x0, y0), (x1, y1), (x2, y2) = src
    (u0, v0), (u1, v1), (u2, v2) = dst
    M = np.array([[x0, y0, 1], [x1, y1, 1], [x2, y2, 1]], float)
    try:
        a = np.linalg.solve(M, [u0, u1, u2])
        b = np.linalg.solve(M, [v0, v1, v2])
    except np.linalg.LinAlgError:
        return None
    return QTransform(a[0], b[0], a[1], b[1], a[2], b[2])
