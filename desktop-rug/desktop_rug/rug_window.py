"""The rug window: a frameless, translucent, click-through-where-transparent
window showing a real-time 3D cloth-simulated Persian rug."""
import json
import math
import os
import time

import numpy as np
from PySide6.QtCore import Qt, QPointF, QRect, QTimer, Signal
from PySide6.QtGui import (QPainter, QPixmap, QImage, QColor, QRegion, QPen, QCursor,
                           QGuiApplication, QBitmap, QTransform)
from PySide6.QtWidgets import QWidget

from . import geometry as G
from . import platform_support as PS
from .cloth import Cloth, THICK
from .textures import front_texture, back_texture

MIN_W, MIN_H = 160.0, 100.0
EDGE_ZONE = 16.0
FOLD_THRESHOLD = 12.0     # px of displacement from flat that counts as "folded"
FRAME_MS = 16
HOLD_MS = 450            # press-and-hold without moving -> move the whole rug


def rotate_cursor() -> QCursor:
    pm = QPixmap(28, 28)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    for col, wdt in ((QColor(255, 255, 255), 5), (QColor(0, 0, 0), 2)):
        pen = QPen(col, wdt)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(5, 5, 18, 18, 30 * 16, 260 * 16)
        p.drawLine(QPointF(21, 4), QPointF(21.5, 10))
        p.drawLine(QPointF(21.5, 10), QPointF(15.5, 9.5))
    p.end()
    return QCursor(pm, 14, 14)


def make_renderer(pref="auto"):
    """OpenGL renderer if possible, else the QPainter software fallback."""
    from .render_soft import SoftRenderer
    pref = (os.environ.get("DESKTOP_RUG_RENDERER") or pref or "auto").lower()
    if pref != "software":
        try:
            from .render_gl import GLRenderer
            r = GLRenderer()
            if r.ok:
                return r
            print("OpenGL unavailable (%s) - using software renderer" % r.error)
        except Exception as ex:
            print("OpenGL init failed (%s) - using software renderer" % ex)
    return SoftRenderer()


class RugWindow(QWidget):
    contextMenuRequested = Signal(object)   # QPoint (global)
    stateChanged = Signal()

    def __init__(self, state, image: QImage, cloth_path=None, demo_icons=None, renderer=None, parent=None):
        super().__init__(parent)
        self.st = state
        self.cloth_path = cloth_path
        self.demo_icons = demo_icons or []
        self.icons = []
        self.x11 = PS.X11Shape() if PS.IS_LINUX else None
        self._apply_flags()
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self.setWindowTitle("Desktop Rug")
        self._rot_cursor = rotate_cursor()

        self.renderer = renderer or make_renderer(getattr(state, "renderer", "auto"))
        self.frame = None
        self.frame_no = 0
        self.press = None
        self.memory = None        # local-coords cloth state to re-fold to
        self.fps = 0.0
        self._t_last = time.perf_counter()

        if self.st.cx < 0 or self.st.cy < 0:
            self._default_pose(image)
        self.cloth = Cloth(self.st.w, self.st.h, self.st.cx, self.st.cy, self.st.angle)
        self.set_image(image, reset_cloth=False)
        self._load_cloth()
        if self.memory is None:
            self.memory = self.cloth.corner_fold_local()

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.icon_timer = QTimer(self)
        self.icon_timer.timeout.connect(self.refresh_icons)
        self.icon_timer.start(2500)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self._save_all)
        self.refresh_icons()
        self.render_now(tight=True)
        self.cloth.wake()
        self.timer.start(FRAME_MS)

    # ------------------------------------------------------------------ setup
    def _apply_flags(self):
        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.NoDropShadowWindowHint
        if self.st.bottom_layer:
            flags |= Qt.WindowStaysOnBottomHint
        if not PS.IS_WIN:
            flags |= Qt.WindowDoesNotAcceptFocus
        self.setWindowFlags(flags)

    def set_bottom_layer(self, on):
        self.st.bottom_layer = bool(on)
        vis = self.isVisible()
        self._apply_flags()
        if vis:
            self.show()
            self._after_show()
        self._schedule_save()

    def _default_pose(self, image):
        scr = QGuiApplication.primaryScreen().availableGeometry()
        ar = image.height() / max(1, image.width())
        self.st.w = min(640.0, scr.width() * 0.45)
        self.st.h = self.st.w * ar
        self.st.cx = scr.center().x()
        self.st.cy = scr.center().y()
        self.st.angle = -4.0

    def set_image(self, image: QImage, reset_cloth=True):
        self.image = image
        front = front_texture(image)
        back = back_texture(front)
        self.renderer.set_textures(front, back)
        if reset_cloth:
            ar = front.height() / max(1, front.width())
            self.st.h = self.st.w * ar
            self.rebuild_cloth(flat=True)

    def rebuild_cloth(self, flat=True):
        self.cloth = Cloth(self.st.w, self.st.h, self.st.cx, self.st.cy, self.st.angle)
        self.memory = self.cloth.corner_fold_local()
        self.wake()

    def reset_position(self):
        self._default_pose(self.image)
        ar = front_texture(self.image).height() / max(1, front_texture(self.image).width())
        self.st.h = self.st.w * ar
        self.rebuild_cloth()
        self._schedule_save()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._after_show)

    def _after_show(self):
        if PS.IS_WIN:
            PS.win_prepare_window(self.winId(), self.st.bottom_layer)
        self.update_shape()

    def nativeEvent(self, eventType, message):
        if PS.IS_WIN:
            handled, result = PS.win_native_event(message, self.st.bottom_layer)
            if handled:
                return True, result
        return super().nativeEvent(eventType, message)

    # ------------------------------------------------------------------ persistence
    def _load_cloth(self):
        if not self.cloth_path or not os.path.exists(self.cloth_path):
            return
        try:
            with open(self.cloth_path, encoding="utf-8") as f:
                d = json.load(f)
            c = self.cloth
            if d.get("nx") == c.nx and d.get("ny") == c.ny and abs(d.get("w", 0) - c.w) < 0.5 \
                    and abs(d.get("h", 0) - c.h) < 0.5:
                c.set_positions(d["P"])
                c._fringe_rest_layout()
                c.fr_prev = c.fr_P.copy()
                if d.get("memory"):
                    self.memory = np.asarray(d["memory"], float).reshape(c.ny, c.nx, 3)
        except (OSError, ValueError, KeyError) as ex:
            print("could not load cloth state:", ex)

    def _save_all(self):
        c = self.cloth
        try:
            pose = c.fit_pose()
            self.st.cx, self.st.cy, self.st.angle = pose
            self.st.folded = c.fold_amount(pose) > FOLD_THRESHOLD
        except Exception:
            pass
        self.stateChanged.emit()
        if self.cloth_path:
            d = c.to_dict()
            if self.memory is not None:
                d["memory"] = np.round(self.memory.reshape(-1), 2).tolist()
            tmp = self.cloth_path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(d, f)
                os.replace(tmp, self.cloth_path)
            except OSError as ex:
                print("could not save cloth:", ex)

    def _schedule_save(self):
        self.save_timer.start(500)

    # ------------------------------------------------------------------ simulation loop
    def wake(self):
        self.cloth.wake()
        if not self.timer.isActive():
            self.timer.start(FRAME_MS)

    def tick(self):
        now = time.perf_counter()
        dt = now - self._t_last
        self._t_last = now
        self.fps = 0.9 * self.fps + 0.1 * (1.0 / max(1e-3, dt))
        c = self.cloth
        if self.icons:
            c.bumps = self._bump_positions()
        else:
            c.bumps = None
        c.step(1 / 60)
        self.render_now(tight=c.sleeping)
        if c.sleeping and not self.press:
            self.timer.stop()
            self._schedule_save()

    def _needed_rect(self):
        mn, mx, zmax = self.cloth.bbox()
        sx, sy = 0.33 * (zmax + 2.5), 0.48 * (zmax + 2.5)
        j = 2.6 * (1 + zmax * 0.07) + 4
        x0, y0 = mn[0] - j - 6, mn[1] - j - 6
        x1, y1 = mx[0] + sx + j + 8, mx[1] + sy + j + 8
        return QRect(int(math.floor(x0)), int(math.floor(y0)),
                     int(math.ceil(x1 - x0)), int(math.ceil(y1 - y0)))

    def render_now(self, tight=False):
        need = self._needed_rect()
        cur = self.geometry()
        if tight:
            if need != cur:
                self.setGeometry(need)
        elif not cur.contains(need):
            self.setGeometry(need.adjusted(-80, -80, 80, 80).united(cur) if self.isVisible() else need)
        g = self.geometry()
        dpr = self.devicePixelRatioF() if self.isVisible() else 1.0
        try:
            self.frame = self.renderer.render(self.cloth, g.x(), g.y(), g.width(), g.height(), dpr)
        except Exception as ex:
            if self.renderer.name != "software":
                print("OpenGL rendering failed (%s) - switching to software renderer" % ex)
                from .render_soft import SoftRenderer
                self.renderer = SoftRenderer()
                front = front_texture(self.image)
                self.renderer.set_textures(front, back_texture(front))
                self.frame = self.renderer.render(self.cloth, g.x(), g.y(), g.width(), g.height(), dpr)
            else:
                raise
        self.frame_no += 1
        if tight or self.frame_no % 2 == 0 or self.renderer.name == "software":
            self.update_shape()
        self.update()

    def paintEvent(self, e):
        if self.frame is None:
            return
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawImage(0, 0, self.frame)
        p.end()

    # ------------------------------------------------------------------ click-through
    def silhouette_region(self):
        """Region (device px) of opaque rug pixels in the last frame (shadows excluded)."""
        if self.frame is None:
            return QRegion()
        mask = self.frame.createAlphaMask(Qt.ThresholdAlphaDither)   # alpha >= 128
        return QRegion(QBitmap.fromImage(mask))

    def update_shape(self):
        if not self.isVisible() or self.frame is None:
            return
        region = self.silhouette_region()
        dpr = self.frame.devicePixelRatio()
        use_x11 = (PS.IS_LINUX and self.x11 and self.x11.ok and QGuiApplication.platformName() == "xcb")
        hard = self.st.hard_mask or not (PS.IS_WIN or use_x11)
        if hard:
            if dpr != 1.0:
                region = QTransform.fromScale(1 / dpr, 1 / dpr).map(region)
            self.setMask(region)
            return
        if not self.mask().isEmpty():
            self.clearMask()
        if use_x11:
            rects = [(r.x(), r.y(), r.width(), r.height()) for r in region]
            self.x11.set_input_rects(self.winId(), rects)
        # Windows: Qt shows translucent windows as layered windows; the OS lets
        # clicks fall through fully transparent pixels by itself.

    # ------------------------------------------------------------------ icons -> bumps under the rug
    def refresh_icons(self):
        if not self.st.bumps:
            if self.icons:
                self.icons = []
                self.wake()
            return
        icons = list(self.demo_icons)
        phys = PS.desktop_icon_positions()
        if phys:
            scr = QGuiApplication.primaryScreen()
            dpr = scr.devicePixelRatio() if scr else 1.0
            icons += [(x / dpr, y / dpr) for x, y in phys]
        if icons != self.icons:
            self.icons = icons
            self.wake()

    def _bump_positions(self):
        return np.asarray(self.icons, float) if self.icons else None

    # ------------------------------------------------------------------ fold / unfold
    def pose(self):
        return self.cloth.fit_pose()

    def is_folded(self):
        return self.cloth.fold_amount() > FOLD_THRESHOLD

    def unfold(self):
        c = self.cloth
        pose = c.fit_pose()
        if c.fold_amount(pose) > FOLD_THRESHOLD:
            self.memory = c.to_local(c.P, pose)
        c.animate_to(c.flat_target(pose), duration=0.8)
        self.wake()

    def refold(self):
        c = self.cloth
        if self.memory is None:
            self.memory = c.corner_fold_local()
        pose = c.fit_pose()
        c.animate_to(c.from_local(self.memory, pose), duration=0.8)
        self.wake()

    def toggle_fold(self):
        if self.is_folded():
            self.unfold()
        else:
            self.refold()

    def click_at(self, x, y):
        """Click (no drag): folded -> lay it flat; flat -> lift the remembered fold
        again if the click is on the part that was folded."""
        c = self.cloth
        pose = c.fit_pose()
        if c.fold_amount(pose) > FOLD_THRESHOLD:
            self.unfold()
            return
        if self.memory is None:
            return
        iy, ix = c.pick(x, y)
        flat = np.append(c.rest[iy, ix], 0.0)
        if np.linalg.norm(self.memory[iy, ix] - flat) > 10.0:
            self.refold()

    # ------------------------------------------------------------------ interaction
    def _zone(self, x, y, mods, button):
        if button == Qt.MiddleButton:
            return "move"
        if mods & (Qt.ShiftModifier | Qt.AltModifier):
            return "rotate"
        if mods & Qt.ControlModifier:
            lx, ly = G.to_local((x, y), (self.st.cx, self.st.cy), self.st.angle)
            w, h = self.st.w, self.st.h
            d = {"resize-l": abs(lx + w / 2), "resize-r": abs(lx - w / 2),
                 "resize-t": abs(ly + h / 2), "resize-b": abs(ly - h / 2)}
            z = min(d, key=d.get)
            if d[z] < EDGE_ZONE and not self.is_folded():
                return z
            return "move"
        return "grab"

    def _cursor_for(self, zone):
        if zone == "rotate":
            return self._rot_cursor
        if zone == "move":
            return Qt.SizeAllCursor
        if zone.startswith("resize"):
            ang = (self.st.angle + (0 if zone in ("resize-l", "resize-r") else 90)) % 180
            if ang < 22.5 or ang >= 157.5:
                return Qt.SizeHorCursor
            if ang < 67.5:
                return Qt.SizeFDiagCursor
            if ang < 112.5:
                return Qt.SizeVerCursor
            return Qt.SizeBDiagCursor
        return Qt.OpenHandCursor

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.contextMenuRequested.emit(e.globalPosition().toPoint())
            return
        if e.button() not in (Qt.LeftButton, Qt.MiddleButton):
            return
        gp = e.globalPosition()
        x, y = gp.x(), gp.y()
        if not self.cloth.sleeping:
            pose = self.cloth.fit_pose()
        else:
            pose = (self.st.cx, self.st.cy, self.st.angle)
        self.st.cx, self.st.cy, self.st.angle = pose
        zone = self._zone(x, y, e.modifiers(), e.button())
        cen = self.cloth.P[..., :2].reshape(-1, 2).mean(0)
        self.press = dict(zone=zone, start=(x, y), last=(x, y), moved=False, grabbed=False,
                          pose=pose, w=self.st.w, h=self.st.h, center=(float(cen[0]), float(cen[1])))
        self.setCursor(Qt.ClosedHandCursor if zone == "grab" else self._cursor_for(zone))
        if zone == "grab":
            # press-and-hold (without moving) picks the whole rug up to move it
            pr = self.press
            QTimer.singleShot(HOLD_MS, lambda: self._hold_to_move(pr))
        e.accept()

    def _hold_to_move(self, pr):
        if self.press is pr and not pr["moved"] and pr["zone"] == "grab":
            pr["zone"] = "move"
            self.setCursor(Qt.SizeAllCursor)

    def mouseMoveEvent(self, e):
        gp = e.globalPosition()
        x, y = gp.x(), gp.y()
        if not self.press:
            zone = self._zone(x, y, QGuiApplication.keyboardModifiers(), Qt.NoButton)
            self.setCursor(self._cursor_for(zone))
            return
        pr = self.press
        if not pr["moved"] and math.hypot(x - pr["start"][0], y - pr["start"][1]) < 4:
            return
        pr["moved"] = True
        z = pr["zone"]
        lx, ly = pr["last"]
        if z == "grab":
            if not pr["grabbed"]:
                self.cloth.start_grab(*pr["start"])
                pr["grabbed"] = True
            self.cloth.drag_to(x, y)
        elif z == "move":
            self.cloth.translate(x - lx, y - ly)
        elif z == "rotate":
            cx, cy = pr["center"]
            a1 = math.atan2(ly - cy, lx - cx)
            a2 = math.atan2(y - cy, x - cx)
            self.cloth.rotate(math.degrees(a2 - a1), center=(cx, cy))
        elif z.startswith("resize"):
            cx0, cy0, a0 = pr["pose"]
            w0, h0 = pr["w"], pr["h"]
            mx, my = G.to_local((x, y), (cx0, cy0), a0)
            l, r, t, b = -w0 / 2, w0 / 2, -h0 / 2, h0 / 2
            if z == "resize-l":
                l = min(mx, r - MIN_W)
            elif z == "resize-r":
                r = max(mx, l + MIN_W)
            elif z == "resize-t":
                t = min(my, b - MIN_H)
            else:
                b = max(my, t + MIN_H)
            self.st.w, self.st.h = r - l, b - t
            self.st.cx, self.st.cy = G.to_global(((l + r) / 2, (t + b) / 2), (cx0, cy0), a0)
            self.st.angle = a0
            self.rebuild_cloth()
        pr["last"] = (x, y)
        self.wake()

    def mouseReleaseEvent(self, e):
        if e.button() not in (Qt.LeftButton, Qt.MiddleButton) or not self.press:
            return
        pr, self.press = self.press, None
        if pr["grabbed"]:
            self.cloth.end_grab()
        elif not pr["moved"] and pr["zone"] == "grab":
            self.click_at(*pr["start"])
        self.setCursor(Qt.OpenHandCursor)
        self.wake()
        self._schedule_save()

    def closeEvent(self, e):
        self._save_all()
        super().closeEvent(e)
