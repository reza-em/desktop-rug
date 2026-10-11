#!/usr/bin/env python3
"""Package release bundles:
  release/DesktopRug-Windows.zip   (exe + Enable/Disable/Uninstall .bat, ASCII + Persian names, README_FA.txt)
  release/DesktopRug-Linux.tar.gz  (AppImage + .sh scripts + .desktop launchers + README_FA.txt)"""
import os, sys, tarfile, zipfile, io

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
from desktop_rug.install import PERSIAN_BAT_NAMES   # noqa: E402

OUT = os.path.join(ROOT, 'release')
os.makedirs(OUT, exist_ok=True)
SW = os.path.join(ROOT, 'desktop_rug', 'scripts', 'windows')
SL = os.path.join(ROOT, 'desktop_rug', 'scripts', 'linux')
REL = os.path.join(ROOT, 'packaging', 'release')


def windows():
    exe = os.path.join(ROOT, 'dist', 'windows', 'DesktopRug.exe')
    p = os.path.join(OUT, 'DesktopRug-Windows.zip')
    with zipfile.ZipFile(p, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(exe, 'DesktopRug-Windows/DesktopRug.exe')
        for n in sorted(os.listdir(SW)):
            data = open(os.path.join(SW, n), 'rb').read()
            z.writestr('DesktopRug-Windows/' + n, data)
            if n in PERSIAN_BAT_NAMES:          # zipfile sets the UTF-8 name flag for these
                z.writestr('DesktopRug-Windows/' + PERSIAN_BAT_NAMES[n], data)
        txt = open(os.path.join(REL, 'README_FA_windows.txt'), encoding='utf-8').read()
        z.writestr('DesktopRug-Windows/README_FA.txt', b'\xef\xbb\xbf' + txt.replace('\n', '\r\n').encode('utf-8'))
    return p


def linux():
    app = os.path.join(ROOT, 'dist', 'linux', 'DesktopRug-x86_64.AppImage')
    p = os.path.join(OUT, 'DesktopRug-Linux.tar.gz')

    def add(t, src, name, mode=0o755):
        ti = t.gettarinfo(src, 'DesktopRug-Linux/' + name)
        ti.mode = mode
        ti.uid = ti.gid = 0
        ti.uname = ti.gname = ''
        with open(src, 'rb') as f:
            t.addfile(ti, f)
    with tarfile.open(p, 'w:gz', format=tarfile.PAX_FORMAT) as t:
        add(t, app, 'DesktopRug-x86_64.AppImage')
        for n in sorted(os.listdir(SL)):
            add(t, os.path.join(SL, n), n)
        add(t, os.path.join(REL, 'README_FA_linux.txt'), 'README_FA.txt', 0o644)
    return p


if __name__ == '__main__':
    for fn in (windows, linux):
        path = fn()
        print('%s  %.1f MB' % (path, os.path.getsize(path) / 1e6))
