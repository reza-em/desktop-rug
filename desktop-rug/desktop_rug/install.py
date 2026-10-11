"""Install / autostart / single-instance control (no Qt GUI needed).

* The packaged app copies itself to a stable per-user location and registers
  autostart there (Windows: HKCU Run key, Linux: XDG autostart entry), so it keeps
  starting after reboots even if the downloaded file is moved or deleted.
* Autostart is switched on automatically on the first run; it is only switched off
  by --disable-autostart (the Disable scripts) or the tray option. Quitting or a
  crash never touches it.
* A running instance polls a small control directory: the file "quit" makes it save
  and exit (used by --quit-running and the Disable scripts), "show" makes it visible.
"""
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time

IS_WIN = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "DesktopRug"
HOME = os.path.expanduser("~")


# --------------------------------------------------------------------------- paths
def config_dir():
    if IS_WIN:
        base = os.environ.get("LOCALAPPDATA") or os.path.join(HOME, "AppData", "Local")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config")
    d = os.path.join(base, "desktop-rug")
    os.makedirs(d, exist_ok=True)
    return d


def control_dir():
    d = os.path.join(config_dir(), "control")
    os.makedirs(d, exist_ok=True)
    return d


def marker_path():
    return os.path.join(config_dir(), "autostart-initialized")


def lock_path():
    import tempfile
    user = os.environ.get("USER") or os.environ.get("USERNAME") or "u"
    tmp = os.environ.get("TMPDIR") if not IS_WIN else None
    return os.path.join(tmp or tempfile.gettempdir(), "desktop-rug-%s.lock" % user)


def install_dir():
    if IS_WIN:
        base = os.environ.get("LOCALAPPDATA") or os.path.join(HOME, "AppData", "Local")
        return os.path.join(base, "DesktopRug")
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local", "share")
    return os.path.join(base, "desktop-rug")


def current_binary():
    """The file the user launched (AppImage / exe / one-file binary), or None from source."""
    if os.environ.get("APPIMAGE"):
        return os.path.abspath(os.environ["APPIMAGE"])
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return None


def installed_binary(src=None):
    src = src or current_binary()
    if IS_WIN:
        name = "DesktopRug.exe"
    elif src and (os.environ.get("APPIMAGE") or src.lower().endswith(".appimage")):
        name = "DesktopRug.AppImage"
    else:
        name = "desktop-rug"
    return os.path.join(install_dir(), name)


def autostart_file():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config")
    return os.path.join(base, "autostart", "desktop-rug.desktop")


def startup_folder_items():
    appdata = os.environ.get("APPDATA") or os.path.join(HOME, "AppData", "Roaming")
    d = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
    return [os.path.join(d, n) for n in ("Desktop Rug.lnk", "DesktopRug.lnk", "DesktopRug.bat")]


def _same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _needs_copy(src, dst):
    if not os.path.exists(dst):
        return True
    s, d = os.stat(src), os.stat(dst)
    return s.st_size != d.st_size or int(s.st_mtime) != int(d.st_mtime)


# --------------------------------------------------------------------------- install copy
def install_copy(log=print):
    """Copy the running binary to the stable location; returns the launch command list."""
    src = current_binary()
    if src is None:                       # running from source: autostart the source tree
        exe = sys.executable
        if IS_WIN and exe.lower().endswith("python.exe"):
            cand = exe[:-10] + "pythonw.exe"
            exe = cand if os.path.exists(cand) else exe
        pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return [exe, os.path.join(pkg_root, "run_desktop_rug.py")]
    dst = installed_binary(src)
    if not _same_file(src, dst) and _needs_copy(src, dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst) and is_running():
            quit_running(log=log)                  # the installed copy may be locked (Windows)
        tmp = dst + ".new"
        shutil.copy2(src, tmp)
        if not IS_WIN:
            os.chmod(tmp, 0o755)
        for _ in range(20):
            try:
                os.replace(tmp, dst)
                break
            except PermissionError:
                time.sleep(0.5)
        else:
            raise PermissionError("could not replace %s (is it still running?)" % dst)
        log("installed %s" % dst)
    return [dst]


# --------------------------------------------------------------------------- helper scripts
PERSIAN_BAT_NAMES = {
    "Enable-DesktopRug.bat": "فعال‌سازی فرش.bat",
    "Disable-DesktopRug.bat": "غیرفعال‌سازی فرش.bat",
    "Uninstall-DesktopRug.bat": "حذف کامل فرش.bat",
}


def scripts_src_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "windows" if IS_WIN else "linux")


def install_scripts(dest=None, log=print):
    """Put the Enable/Disable(/Uninstall) scripts next to the installed copy too."""
    src = scripts_src_dir()
    dest = dest or install_dir()
    if not os.path.isdir(src):
        return []
    os.makedirs(dest, exist_ok=True)
    out = []
    for name in sorted(os.listdir(src)):
        targets = [name] + ([PERSIAN_BAT_NAMES[name]] if name in PERSIAN_BAT_NAMES else [])
        for t in targets:
            d = os.path.join(dest, t)
            try:
                shutil.copyfile(os.path.join(src, name), d)
                if not IS_WIN:
                    os.chmod(d, 0o755)
                out.append(d)
            except OSError as ex:
                log("could not copy %s: %s" % (t, ex))
    if not IS_WIN:
        out += write_linux_launchers(dest)
    return out


def applications_dir():
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local", "share")
    return os.path.join(base, "applications")


def write_linux_launchers(dest):
    """Absolute-path 'Desktop Rug - Enable/Disable' launchers in the install folder
    and in the application menu (so they are one click away even without the
    downloaded folder)."""
    out = []
    names = {"enable": ("Desktop Rug - Enable", "فعال‌سازی فرش دسکتاپ",
                        "Start Desktop Rug now and at every login"),
             "disable": ("Desktop Rug - Disable", "غیرفعال‌سازی فرش دسکتاپ",
                         "Close Desktop Rug and stop it starting at login")}
    for kind, (name, fa, comment) in names.items():
        script = os.path.join(dest, "%s-desktop-rug.sh" % kind)
        body = ("[Desktop Entry]\nType=Application\nName=%s\nName[fa]=%s\nComment=%s\n"
                "Exec=sh \"%s\"\nIcon=preferences-desktop-wallpaper\nTerminal=false\n"
                "Categories=Utility;\n" % (name, fa, comment, script))
        for d, fn in ((dest, "%s.desktop" % name), (applications_dir(), "desktop-rug-%s.desktop" % kind)):
            try:
                os.makedirs(d, exist_ok=True)
                p = os.path.join(d, fn)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(body)
                os.chmod(p, 0o755)
                out.append(p)
            except OSError:
                pass
    return out


# --------------------------------------------------------------------------- autostart
def _win_cmdline(cmd):
    return " ".join('"%s"' % c for c in cmd) + " --autostart"


def autostart_enabled():
    if IS_WIN:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, RUN_NAME)
                return True
        except OSError:
            return False
    return os.path.exists(autostart_file())


def launcher_script_path():
    return os.path.join(install_dir(), "desktop-rug-autostart.sh")


def write_launcher(cmd):
    """Small wrapper used by the XDG autostart entry: waits for the session
    (compositor/panel) and forces XWayland, then starts the installed copy."""
    p = launcher_script_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    exe = " ".join(shlex.quote(c) for c in cmd)
    with open(p, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\n# Desktop Rug autostart launcher (generated)\n"
                "sleep ${DESKTOP_RUG_AUTOSTART_DELAY:-6}\n"
                "[ -n \"$DISPLAY\" ] && export QT_QPA_PLATFORM=xcb\n"
                + ("# AppImages need FUSE; without it, extract-and-run instead\n"
                   "%s --version >/dev/null 2>&1 || export APPIMAGE_EXTRACT_AND_RUN=1\n" % exe
                   if cmd[0].lower().endswith(".appimage") else "")
                + "exec %s --autostart \"$@\"\n" % exe)
    os.chmod(p, 0o755)
    return p


def desktop_entry(cmd):
    launcher = write_launcher(cmd)
    return ("[Desktop Entry]\nType=Application\nName=Desktop Rug\nName[fa]=فرش دسکتاپ\n"
            "Comment=A Persian rug for your desktop\n"
            "Exec=env QT_QPA_PLATFORM=xcb \"%s\"\n"
            "TryExec=%s\n"
            "Terminal=false\nNoDisplay=false\nHidden=false\n"
            "X-GNOME-Autostart-enabled=true\nX-GNOME-Autostart-Delay=4\n"
            "X-KDE-autostart-after=panel\nX-MATE-Autostart-Delay=4\n"
            % (launcher, launcher))


def enable_autostart(log=print, copy=True):
    cmd = install_copy(log) if copy else ([current_binary()] if current_binary() else install_copy(log))
    if IS_WIN:
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, _win_cmdline(cmd))
        log("autostart: HKCU\\%s\\%s = %s" % (RUN_KEY, RUN_NAME, _win_cmdline(cmd)))
    else:
        p = autostart_file()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(desktop_entry(cmd))
        os.chmod(p, 0o755)
        log("autostart: %s" % p)
    _touch(marker_path())
    if current_binary() is not None:
        install_scripts(log=log)
    return cmd


def disable_autostart(log=print):
    if IS_WIN:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, RUN_NAME)
        except OSError:
            pass
        for p in startup_folder_items():
            _rm(p)
    else:
        _rm(autostart_file())
        _rm(launcher_script_path())
    _touch(marker_path())          # never auto-enable again after an explicit disable
    log("autostart disabled")


def first_run_enable(log=print):
    """Default ON: the first time the packaged app runs, switch autostart on."""
    if os.environ.get("DESKTOP_RUG_NO_AUTO_ENABLE") or os.path.exists(marker_path()):
        return False
    if current_binary() is None and not os.environ.get("DESKTOP_RUG_AUTO_ENABLE_SOURCE"):
        _touch(marker_path())
        return False
    try:
        enable_autostart(log)
        return True
    except Exception as ex:                       # never block the app over this
        log("could not enable autostart: %s" % ex)
        return False


# --------------------------------------------------------------------------- running instance
def _lock_pid():
    try:
        with open(lock_path(), "r", encoding="utf-8", errors="ignore") as f:
            return int(f.readline().strip() or 0)
    except (OSError, ValueError):
        return 0


def _pid_alive(pid):
    if pid <= 0:
        return False
    if IS_WIN:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return code.value == 259                                       # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def is_running():
    return _pid_alive(_lock_pid())


def request(name):
    _touch(os.path.join(control_dir(), name))


def quit_running(timeout=6.0, log=print):
    pid = _lock_pid()
    if pid == os.getpid() or not _pid_alive(pid):
        _rm(os.path.join(control_dir(), "quit"))
        return False
    request("quit")
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not _pid_alive(pid):
            log("running instance closed")
            return True
        time.sleep(0.2)
    log("instance %d did not exit - terminating" % pid)
    try:
        if IS_WIN:
            subprocess.call(["taskkill", "/PID", str(pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.kill(pid, signal.SIGTERM)
            time.sleep(1.0)
            if _pid_alive(pid):
                os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    _rm(os.path.join(control_dir(), "quit"))
    return True


def take_request(name):
    p = os.path.join(control_dir(), name)
    if os.path.exists(p):
        _rm(p)
        return True
    return False


# --------------------------------------------------------------------------- login readiness
def wait_for_desktop(max_wait=60.0):
    """At login: wait until Explorer's taskbar/desktop (Windows) exists."""
    if not IS_WIN:
        return
    import ctypes
    u = ctypes.windll.user32
    t0 = time.time()
    while time.time() - t0 < max_wait:
        if u.FindWindowW("Shell_TrayWnd", None) and u.FindWindowW("Progman", None):
            break
        if time.time() - t0 > 15 and u.FindWindowW("Progman", None):
            break                       # desktop is up but no taskbar (custom shell, Wine)
        time.sleep(1.0)
    time.sleep(2.0)


def uninstall(log=print, remove_settings=True):
    disable_autostart(log)
    quit_running(log=log)
    shutil.rmtree(install_dir(), ignore_errors=True)
    if not IS_WIN:
        for kind in ("enable", "disable"):
            _rm(os.path.join(applications_dir(), "desktop-rug-%s.desktop" % kind))
    if remove_settings:
        shutil.rmtree(config_dir(), ignore_errors=True)
    log("uninstalled")


# --------------------------------------------------------------------------- utils
def _touch(p):
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8"):
            pass
    except OSError:
        pass


def _rm(p):
    try:
        os.remove(p)
    except OSError:
        pass
