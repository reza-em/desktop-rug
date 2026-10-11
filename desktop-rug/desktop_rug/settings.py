"""JSON persistence of rug state."""
import json
import os
from dataclasses import dataclass, asdict, field

from PySide6.QtCore import QStandardPaths


def config_dir():
    base = QStandardPaths.writableLocation(QStandardPaths.GenericConfigLocation)
    d = os.path.join(base, "desktop-rug")
    os.makedirs(d, exist_ok=True)
    return d


@dataclass
class RugState:
    cx: float = -1.0          # centre in global logical px (-1 = auto)
    cy: float = -1.0
    w: float = 636.0
    h: float = 400.0
    angle: float = -4.0       # degrees
    fold_x: float = 0.18      # stored fold point, as fraction of w/h (local coords)
    fold_y: float = 0.05
    folded: bool = False      # True = corner turned back (desktop revealed)
    visible: bool = True
    image: str = ""           # custom image path, "" = built-in design
    design: str = "tabriz"    # built-in rug design (see app.DESIGNS)
    bottom_layer: bool = True  # keep on desktop layer (below normal windows)
    hard_mask: bool = False   # force QWidget.setMask() click-through (compat mode)
    bumps: bool = True        # bumps in the rug where desktop icons are hidden
    renderer: str = "auto"    # auto | opengl | software
    extra: dict = field(default_factory=dict)


def settings_path():
    return os.path.join(config_dir(), "settings.json")


def load(path=None):
    path = path or settings_path()
    st = RugState()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            if hasattr(st, k):
                setattr(st, k, v)
    except (OSError, ValueError):
        pass
    return st


def save(st, path=None):
    path = path or settings_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(asdict(st), f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
