"""Off-screen rendering helpers (wood 'desktop' background, preview images)."""
import random
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QImage, QPainter, QColor, QLinearGradient, QPen, QFont


def wood_background(w, h, seed=3):
    rnd = random.Random(seed)
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    plank_h = 58
    y = 0
    while y < h:
        x = -rnd.randint(0, 300)
        while x < w:
            L = rnd.randint(260, 520)
            base = QColor.fromHsv(28 + rnd.randint(-4, 4), 120 + rnd.randint(-20, 20), 200 + rnd.randint(-20, 15))
            g = QLinearGradient(0, y, 0, y + plank_h)
            g.setColorAt(0, base.lighter(108))
            g.setColorAt(1, base.darker(106))
            p.fillRect(QRectF(x, y, L, plank_h), g)
            pen = QPen(base.darker(118), 1)
            p.setPen(pen)
            for _ in range(7):
                yy = y + rnd.uniform(4, plank_h - 4)
                amp = rnd.uniform(0.5, 3)
                pts = [QPointF(x + t, yy + amp * ((t * 0.013 + rnd.random() * 0.02) % 2 - 1)) for t in range(0, L, 20)]
                for a, b in zip(pts, pts[1:]):
                    p.drawLine(a, b)
            p.setPen(QPen(QColor(90, 55, 30, 140), 1.5))
            p.drawLine(QPointF(x, y), QPointF(x, y + plank_h))
            x += L
        p.setPen(QPen(QColor(90, 55, 30, 160), 1.5))
        p.drawLine(QPointF(0, y), QPointF(w, y))
        y += plank_h
    p.end()
    return img


def draw_fake_icons(img, icons, labels=None):
    """Mac-like desktop file icons for demos/screenshots."""
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    f = QFont()
    f.setPixelSize(11)
    p.setFont(f)
    cols = [QColor(90, 170, 230), QColor(245, 245, 245), QColor(240, 240, 240), QColor(120, 200, 120)]
    for i, (x, y) in enumerate(icons):
        c = cols[i % len(cols)]
        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.setBrush(c)
        if i % 4 == 0:
            p.drawRoundedRect(QRectF(x - 24, y - 16, 48, 36), 4, 4)
            p.drawRoundedRect(QRectF(x - 24, y - 22, 20, 8), 3, 3)
        else:
            p.drawRect(QRectF(x - 18, y - 22, 36, 46))
            p.setPen(QPen(QColor(150, 150, 150), 1))
            for k in range(4):
                p.drawLine(QPointF(x - 12, y - 12 + k * 7), QPointF(x + 12, y - 12 + k * 7))
        label = (labels[i] if labels and i < len(labels) else "file-%d.pdf" % i)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(40, 100, 220))
        tw = p.fontMetrics().horizontalAdvance(label) + 8
        p.drawRoundedRect(QRectF(x - tw / 2, y + 28, tw, 15), 4, 4)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x - tw / 2, y + 28, tw, 15), Qt.AlignCenter, label)
    p.end()


# --------------------------------------------------------------------------- simulated previews
def simulate(scenario, cloth, frames=90, settle=260):
    """Drive the cloth with a scripted 'hand' (used for previews, CI and docs)."""
    import numpy as np
    c = cloth
    shots = {}

    def drag(px, py, tx, ty, n=frames):
        c.start_grab(px, py)
        for i in range(n):
            f = (i + 1) / n
            f = f * f * (3 - 2 * f)
            c.drag_to(px + (tx - px) * f, py + (ty - py) * f)
            c.step()
        c.end_grab()
        for _ in range(settle):
            if c.sleeping:
                break
            c.step()

    cx, cy = c.P[..., :2].reshape(-1, 2).mean(0)
    if scenario in ("corner", "unfold", "double", "bumps"):
        px, py = c.P[-1, -1, :2]
        drag(px, py, cx - 0.12 * c.w, cy - 0.22 * c.h)
    if scenario == "double":
        px, py = c.P[0, 0, :2]
        drag(px, py, cx + 0.05 * c.w, cy + 0.15 * c.h)
    if scenario == "edge":
        px, py = c.P[c.ny // 2, 0, :2]
        drag(px, py, px + 0.62 * c.w, py)
    if scenario == "over":
        px, py = c.P[-1, -1, :2]
        drag(px, py, c.P[0, 0, 0] - 0.05 * c.w, c.P[0, 0, 1] - 0.05 * c.h, n=110)
    if scenario == "unfold":
        pose = c.fit_pose()
        c.animate_to(c.flat_target(pose), duration=0.8)
        for _ in range(60):
            c.step()
        for _ in range(settle):
            if c.sleeping:
                break
            c.step()
    return c


def render_scenario(out_path, scenario, image, icons=None, renderer_pref="auto", size=(1280, 800)):
    from PySide6.QtGui import QPainter
    from .cloth import Cloth
    from .rug_window import make_renderer
    from .textures import front_texture, back_texture
    W, H = size
    front = front_texture(image)
    r = make_renderer(renderer_pref)
    r.set_textures(front, back_texture(front))
    w = 620.0
    c = Cloth(w, w * front.height() / front.width(), W / 2 - 60, H / 2, -4)
    if icons:
        import numpy as np
        c.bumps = np.asarray(icons, float)
    simulate(scenario, c)
    bg = wood_background(W, H)
    if icons and scenario != "bumps":
        draw_fake_icons(bg, icons)
    img = r.render(c, 0, 0, W, H, 1.0)
    p = QPainter(bg)
    p.drawImage(0, 0, img)
    p.end()
    bg.save(out_path)
    return "preview written: %s (renderer: %s)" % (out_path, r.name)
