"""Change / restore the desktop wallpaper (the 'floor' the rug lies on).

Windows: SystemParametersInfoW(SPI_SETDESKWALLPAPER) for the current user.
Linux:   GNOME/Ubuntu/Budgie (gsettings org.gnome.desktop.background), Cinnamon,
         MATE, Xfce (xfconf-query), KDE Plasma (plasma-apply-wallpaperimage / qdbus),
         LXDE/LXQt (pcmanfm), otherwise feh (plain X11 WMs).
Images are first copied to <config>/wallpapers/ so the wallpaper keeps working
after the app (or a one-file binary's temp folder) is gone.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from urllib.parse import quote, unquote, urlparse

IS_WIN = sys.platform.startswith("win")
FLOORS = [  # id, file, English, Persian
    ("parquet_light", "parquet_light.jpg", "Light parquet", "پارکت روشن"),
    ("wood_dark", "wood_dark.jpg", "Dark wood", "چوب تیره"),
    ("stone_tiles", "stone_tiles.jpg", "Stone tiles", "کاشی سنگی"),
    ("carpet", "carpet.jpg", "Carpeted floor", "موکت"),
]


def assets_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "floors")


def floor_path(fid):
    for i, f, _, _ in FLOORS:
        if i == fid:
            return os.path.join(assets_dir(), f)
    return None


def _store_dir():
    from .install import config_dir
    d = os.path.join(config_dir(), "wallpapers")
    os.makedirs(d, exist_ok=True)
    return d


def _stable_copy(src, tag, keep=None):
    ext = os.path.splitext(src)[1].lower() or ".jpg"
    d = _store_dir()
    for old in glob.glob(os.path.join(d, tag + "_*")):       # unique name: DEs cache by path/URI
        if keep and os.path.normcase(os.path.abspath(old)) == os.path.normcase(os.path.abspath(keep)):
            continue                                          # still needed by "Restore"
        try:
            os.remove(old)
        except OSError:
            pass
    dst = os.path.join(d, "%s_%d%s" % (tag, int(time.time()), ext))
    shutil.copyfile(src, dst)
    return dst


def _run(cmd, timeout=8):
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, text=True)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except (OSError, subprocess.SubprocessError) as ex:
        return 127, "", str(ex)


def _have(tool):
    return shutil.which(tool) is not None


def _uri(p):
    return "file://" + quote(os.path.abspath(p))


def _from_uri(v):
    v = v.strip().strip("'\"")
    if v.startswith("file://"):
        return unquote(urlparse(v).path)
    return v


# --------------------------------------------------------------------------- backend detection
def desktop_env():
    de = (os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or "").lower()
    return de


def _proc(name):
    return _have("pgrep") and _run(["pgrep", "-x", "-u", str(os.getuid()), name])[0] == 0


def _gsettings_has(schema):
    if not _have("gsettings"):
        return False
    rc, out, _ = _run(["gsettings", "list-schemas"])
    return rc == 0 and schema in out.split()


def backend():
    if IS_WIN:
        return "windows"
    de = desktop_env()
    if "xfce" in de and _have("xfconf-query"):
        return "xfce"
    if ("kde" in de or "plasma" in de) and (_have("plasma-apply-wallpaperimage") or _have("qdbus") or _have("qdbus6")):
        return "kde"
    if "cinnamon" in de and _gsettings_has("org.cinnamon.desktop.background"):
        return "cinnamon"
    if "mate" in de and _gsettings_has("org.mate.background"):
        return "mate"
    if any(k in de for k in ("gnome", "unity", "ubuntu", "budgie", "pantheon", "pop", "cosmic")) \
            and _gsettings_has("org.gnome.desktop.background"):
        return "gnome"
    if "lxqt" in de and _have("pcmanfm-qt"):
        return "lxqt"
    if "lxde" in de and _have("pcmanfm"):
        return "lxde"
    # unknown session: look at what is actually drawing the desktop
    if _proc("xfdesktop") and _have("xfconf-query"):
        return "xfce"
    if _proc("plasmashell"):
        return "kde"
    if _proc("gnome-shell") and _gsettings_has("org.gnome.desktop.background"):
        return "gnome"
    if _proc("cinnamon") and _gsettings_has("org.cinnamon.desktop.background"):
        return "cinnamon"
    if _proc("caja") and _gsettings_has("org.mate.background"):
        return "mate"
    if _proc("pcmanfm-qt"):
        return "lxqt"
    if _proc("pcmanfm"):
        return "lxde"
    if _have("feh"):
        return "feh"
    return None


# --------------------------------------------------------------------------- Windows
def _win_get():
    import ctypes
    buf = ctypes.create_unicode_buffer(1024)
    ctypes.windll.user32.SystemParametersInfoW(0x0073, 1024, buf, 0)   # SPI_GETDESKWALLPAPER
    return buf.value


def _win_style_get():
    import winreg
    out = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as k:
            for n in ("WallpaperStyle", "TileWallpaper"):
                try:
                    out[n] = winreg.QueryValueEx(k, n)[0]
                except OSError:
                    pass
    except OSError:
        pass
    return out


def _win_set(path, style=None):
    import ctypes
    import winreg
    style = style or {"WallpaperStyle": "10", "TileWallpaper": "0"}   # "Fill": the floor covers the screen
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE) as k:
            for n, v in style.items():
                winreg.SetValueEx(k, n, 0, winreg.REG_SZ, str(v))
    except OSError:
        pass
    ok = ctypes.windll.user32.SystemParametersInfoW(0x0014, 0, path, 0x01 | 0x02)  # SET, UPDATEINI|SENDCHANGE
    return bool(ok)


# --------------------------------------------------------------------------- Linux backends
def _xfce_props():
    rc, out, _ = _run(["xfconf-query", "-c", "xfce4-desktop", "-l"])
    return [l for l in out.splitlines() if l.endswith("/last-image")] if rc == 0 else []


def get_current():
    b = backend()
    try:
        if b == "windows":
            return _win_get()
        if b == "gnome":
            return _from_uri(_run(["gsettings", "get", "org.gnome.desktop.background", "picture-uri"])[1])
        if b == "cinnamon":
            return _from_uri(_run(["gsettings", "get", "org.cinnamon.desktop.background", "picture-uri"])[1])
        if b == "mate":
            return _from_uri(_run(["gsettings", "get", "org.mate.background", "picture-filename"])[1])
        if b == "xfce":
            props = _xfce_props()
            if props:
                return _run(["xfconf-query", "-c", "xfce4-desktop", "-p", props[0]])[1]
        if b == "kde":
            rc = os.path.expanduser("~/.config/plasma-org.kde.plasma.desktop-appletsrc")
            with open(rc, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("Image="):
                        return _from_uri(line.split("=", 1)[1])
        if b == "feh":
            with open(os.path.expanduser("~/.fehbg"), encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "feh" in line and "--bg" in line:
                        return line.strip().split()[-1].strip("'\"")
    except Exception:
        pass
    return ""


def _set_linux(b, path):
    uri = _uri(path)
    if b == "gnome":
        ok = _run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri])[0] == 0
        _run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri])   # GNOME 42+
        _run(["gsettings", "set", "org.gnome.desktop.background", "picture-options", "zoom"])
        return ok
    if b == "cinnamon":
        ok = _run(["gsettings", "set", "org.cinnamon.desktop.background", "picture-uri", uri])[0] == 0
        _run(["gsettings", "set", "org.cinnamon.desktop.background", "picture-options", "zoom"])
        return ok
    if b == "mate":
        ok = _run(["gsettings", "set", "org.mate.background", "picture-filename", path])[0] == 0
        _run(["gsettings", "set", "org.mate.background", "picture-options", "zoom"])
        return ok
    if b == "xfce":
        props = _xfce_props() or ["/backdrop/screen0/monitor0/workspace0/last-image"]
        ok = True
        for p in props:
            r = _run(["xfconf-query", "-c", "xfce4-desktop", "-p", p, "-n", "-t", "string", "-s", path])[0]
            ok = ok and r == 0
            _run(["xfconf-query", "-c", "xfce4-desktop", "-p", p.replace("last-image", "image-style"),
                  "-n", "-t", "int", "-s", "5"])                               # zoomed
        return ok
    if b == "kde":
        if _have("plasma-apply-wallpaperimage"):
            return _run(["plasma-apply-wallpaperimage", path], timeout=15)[0] == 0
        js = ("var a=desktops();for(var i=0;i<a.length;i++){var d=a[i];d.wallpaperPlugin='org.kde.image';"
              "d.currentConfigGroup=['Wallpaper','org.kde.image','General'];d.writeConfig('Image','%s');}" % uri)
        q = "qdbus6" if _have("qdbus6") else "qdbus"
        return _run([q, "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.evaluateScript", js])[0] == 0
    if b == "lxqt":
        return _run(["pcmanfm-qt", "--set-wallpaper", path, "--wallpaper-mode", "zoom"])[0] == 0
    if b == "lxde":
        return _run(["pcmanfm", "--set-wallpaper", path, "--wallpaper-mode", "crop"])[0] == 0
    if b == "feh":
        return _run(["feh", "--bg-fill", path])[0] == 0
    return False


# --------------------------------------------------------------------------- public API
def set_wallpaper(image_path, state=None, tag="floor"):
    """Set the wallpaper. Remembers the user's original wallpaper in state.extra
    the first time. Returns (ok, message)."""
    if not image_path or not os.path.exists(image_path):
        return False, "image not found: %s" % image_path
    b = backend()
    if b is None:
        return False, "no supported wallpaper backend found for this desktop (%s)" % (desktop_env() or "unknown")
    if state is not None and not state.extra.get("orig_wallpaper_saved"):
        cur = get_current()
        state.extra["orig_wallpaper"] = cur
        state.extra["orig_wallpaper_backend"] = b
        state.extra["orig_wallpaper_saved"] = True
        if b == "windows":
            state.extra["orig_wallpaper_style"] = _win_style_get()
        if b == "gnome":
            state.extra["orig_wallpaper_dark"] = _from_uri(
                _run(["gsettings", "get", "org.gnome.desktop.background", "picture-uri-dark"])[1])
    stable = _stable_copy(image_path, tag, keep=(state.extra.get("orig_wallpaper") if state else None))
    ok = _win_set(stable) if b == "windows" else _set_linux(b, stable)
    if state is not None and ok:
        state.extra["wallpaper"] = stable
    return ok, ("wallpaper set via %s" % b) if ok else ("setting the wallpaper failed (%s)" % b)


def restore_original(state):
    orig = state.extra.get("orig_wallpaper") if state is not None else None
    if not state or not state.extra.get("orig_wallpaper_saved"):
        return False, "the wallpaper was never changed by Desktop Rug"
    b = backend()
    if not orig and b != "windows":
        return False, "the original wallpaper was not a file (solid colour?) - set it again in your desktop settings"
    # Windows: an empty path means "no picture" (plain colour), which SPI restores too
    ok = _win_set(orig, state.extra.get("orig_wallpaper_style") or None) if b == "windows" else _set_linux(b, orig)
    dark = state.extra.get("orig_wallpaper_dark")
    if ok and b == "gnome" and dark:
        _run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", _uri(dark)])
    if ok:
        state.extra["wallpaper"] = ""
        state.extra["orig_wallpaper_saved"] = False
    return ok, ("original wallpaper restored (%s)" % (orig or "plain colour")) if ok else "restoring failed"


def main(argv=None):
    """python -m desktop_rug.wallpaper [get | set FILE | floor ID] (debug helper)."""
    argv = sys.argv[1:] if argv is None else argv
    print("backend:", backend())
    if not argv or argv[0] == "get":
        print(get_current())
    elif argv[0] == "set":
        print(set_wallpaper(argv[1]))
    elif argv[0] == "floor":
        print(set_wallpaper(floor_path(argv[1])))


if __name__ == "__main__":
    main()
