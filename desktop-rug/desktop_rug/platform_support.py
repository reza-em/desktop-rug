"""OS-specific helpers: desktop layer, per-pixel input shape, autostart,
desktop icon positions. Every function degrades gracefully."""
import os
import sys
import ctypes

IS_WIN = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")


# --------------------------------------------------------------------------- autostart
# (implementation lives in install.py so the CLI flags work without a GUI)
def autostart_enabled():
    from . import install
    return install.autostart_enabled()


def set_autostart(enabled):
    from . import install
    if enabled:
        install.enable_autostart()
    else:
        install.disable_autostart()


def x11_compositor_running():
    """True if a compositing manager owns _NET_WM_CM_S<screen> (needed for transparency)."""
    if not IS_LINUX or not os.environ.get("DISPLAY"):
        return True
    try:
        from ctypes.util import find_library
        x = ctypes.CDLL(find_library("X11") or "libX11.so.6")
        x.XOpenDisplay.restype = ctypes.c_void_p
        x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x.XInternAtom.restype = ctypes.c_ulong
        x.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x.XGetSelectionOwner.restype = ctypes.c_ulong
        x.XGetSelectionOwner.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        x.XDefaultScreen.argtypes = [ctypes.c_void_p]
        x.XCloseDisplay.argtypes = [ctypes.c_void_p]
        d = x.XOpenDisplay(None)
        if not d:
            return False
        atom = x.XInternAtom(d, b"_NET_WM_CM_S%d" % x.XDefaultScreen(d), 0)
        owner = x.XGetSelectionOwner(d, atom)
        x.XCloseDisplay(d)
        return bool(owner)
    except Exception:
        return True


# --------------------------------------------------------------------------- X11 input shape
class _XRect(ctypes.Structure):
    _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short),
                ("width", ctypes.c_ushort), ("height", ctypes.c_ushort)]


class X11Shape:
    """Sets the X11 *input* shape (SHAPE extension, ShapeInput) so that only the
    visible rug receives mouse events, while painting stays fully anti-aliased."""

    def __init__(self):
        self.ok = False
        self.dpy = None
        if not IS_LINUX or not os.environ.get("DISPLAY"):
            return
        try:
            from ctypes.util import find_library
            self.x11 = ctypes.CDLL(find_library("X11") or "libX11.so.6")
            self.xext = ctypes.CDLL(find_library("Xext") or "libXext.so.6")
            self.x11.XOpenDisplay.restype = ctypes.c_void_p
            self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            self.x11.XFlush.argtypes = [ctypes.c_void_p]
            self.xext.XShapeCombineRectangles.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.POINTER(_XRect), ctypes.c_int, ctypes.c_int, ctypes.c_int]
            self.xext.XShapeQueryExtension.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
            self.dpy = self.x11.XOpenDisplay(None)
            if not self.dpy:
                return
            a, b = ctypes.c_int(), ctypes.c_int()
            self.ok = bool(self.xext.XShapeQueryExtension(self.dpy, ctypes.byref(a), ctypes.byref(b)))
        except Exception:
            self.ok = False

    def set_input_rects(self, wid, rects):
        """rects: list of (x, y, w, h) in device pixels relative to window."""
        if not self.ok:
            return False
        arr = (_XRect * max(1, len(rects)))()
        for i, (x, y, w, h) in enumerate(rects):
            arr[i] = _XRect(max(-32768, min(32767, x)), max(-32768, min(32767, y)),
                            max(0, min(65535, w)), max(0, min(65535, h)))
        SHAPE_INPUT, SHAPE_SET, UNSORTED = 2, 0, 0
        self.xext.XShapeCombineRectangles(self.dpy, int(wid), SHAPE_INPUT, 0, 0, arr,
                                          len(rects), SHAPE_SET, UNSORTED)
        self.x11.XFlush(self.dpy)
        return True


# --------------------------------------------------------------------------- Windows
if IS_WIN:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class WINDOWPOS(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("hwndInsertAfter", wintypes.HWND),
                    ("x", ctypes.c_int), ("y", ctypes.c_int), ("cx", ctypes.c_int),
                    ("cy", ctypes.c_int), ("flags", ctypes.c_uint)]

    WM_WINDOWPOSCHANGING = 0x0046
    WM_MOUSEACTIVATE = 0x0021
    MA_NOACTIVATE = 3
    SWP_NOZORDER = 0x0004
    SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
    HWND_BOTTOM = 1
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE, WS_EX_APPWINDOW = 0x80, 0x08000000, 0x40000

    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowExW.restype = wintypes.HWND
    user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.SendMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.VirtualAllocEx.restype = ctypes.c_void_p
    kernel32.VirtualAllocEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
                                        wintypes.DWORD, wintypes.DWORD]
    kernel32.VirtualFreeEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD]
    kernel32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                           ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def win_prepare_window(hwnd, bottom):
    """Tool window (no taskbar button), never activates, optionally pinned to bottom."""
    if not IS_WIN:
        return
    hwnd = wintypes.HWND(int(hwnd))
    ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    ex = (ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
    if bottom:
        user32.SetWindowPos(hwnd, wintypes.HWND(HWND_BOTTOM), 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


def win_native_event(message, bottom):
    """Called from QWidget.nativeEvent. Keeps the rug at the bottom of the
    z-order (just above the desktop / icons) and prevents activation."""
    if not IS_WIN:
        return False, 0
    try:
        msg = wintypes.MSG.from_address(int(message))
    except Exception:
        return False, 0
    if msg.message == WM_MOUSEACTIVATE:
        return True, MA_NOACTIVATE
    if bottom and msg.message == WM_WINDOWPOSCHANGING and msg.lParam:
        wp = WINDOWPOS.from_address(msg.lParam)
        wp.hwndInsertAfter = HWND_BOTTOM
        wp.flags &= ~SWP_NOZORDER
    return False, 0


def win_desktop_icon_positions():
    """Return list of (x, y) screen coords (physical px) of desktop icon centres
    read from Explorer's SysListView32. [] on failure / non-Windows."""
    if not IS_WIN:
        return []
    try:
        lv = None
        progman = user32.FindWindowW("Progman", None)
        defview = user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
        if not defview:
            w = None
            while True:
                w = user32.FindWindowExW(None, w, "WorkerW", None)
                if not w:
                    break
                defview = user32.FindWindowExW(w, None, "SHELLDLL_DefView", None)
                if defview:
                    break
        if defview:
            lv = user32.FindWindowExW(defview, None, "SysListView32", None)
        if not lv:
            return []
        LVM_GETITEMCOUNT, LVM_GETITEMPOSITION, LVM_GETITEMSPACING = 0x1004, 0x1010, 0x1033
        count = user32.SendMessageW(lv, LVM_GETITEMCOUNT, 0, 0)
        if count <= 0:
            return []
        spacing = user32.SendMessageW(lv, LVM_GETITEMSPACING, 0, 0)
        sx, sy = spacing & 0xFFFF, (spacing >> 16) & 0xFFFF
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(lv, ctypes.byref(pid))
        PROCESS_VM_OPERATION, PROCESS_VM_READ, PROCESS_VM_WRITE = 0x8, 0x10, 0x20
        hp = kernel32.OpenProcess(PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE, False, pid.value)
        if not hp:
            return []
        MEM_COMMIT, MEM_RELEASE, PAGE_RW = 0x1000, 0x8000, 0x04
        remote = kernel32.VirtualAllocEx(hp, None, ctypes.sizeof(wintypes.POINT), MEM_COMMIT, PAGE_RW)
        out = []
        try:
            origin = wintypes.POINT(0, 0)
            user32.ClientToScreen(lv, ctypes.byref(origin))
            for i in range(min(count, 2000)):
                user32.SendMessageW(lv, LVM_GETITEMPOSITION, i, remote)
                pt = wintypes.POINT()
                n = ctypes.c_size_t()
                if kernel32.ReadProcessMemory(hp, remote, ctypes.byref(pt), ctypes.sizeof(pt), ctypes.byref(n)):
                    # position is the item's top-left; centre the icon part
                    out.append((origin.x + pt.x + sx // 2, origin.y + pt.y + min(sy, 48) // 2 + 8))
        finally:
            kernel32.VirtualFreeEx(hp, remote, 0, MEM_RELEASE)
            kernel32.CloseHandle(hp)
        return out
    except Exception:
        return []


def desktop_icon_positions():
    """Physical-pixel screen positions of desktop icons, where supported."""
    test_file = os.environ.get("DESKTOP_RUG_ICONS_FILE")   # testing / custom integrations
    if test_file:
        try:
            with open(test_file, encoding="utf-8") as f:
                return [tuple(float(v) for v in part.split(",")) for part in f.read().split(";") if "," in part]
        except (OSError, ValueError):
            return []
    if IS_WIN:
        return win_desktop_icon_positions()
    # Linux: no portable API (xfdesktop / nautilus-desktop / DING / KDE folder view all
    # differ) -> skip gracefully.
    return []
