# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec shared by Linux and Windows builds:  pyinstaller packaging/desktop-rug.spec
import os, sys
ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
IS_WIN = sys.platform.startswith('win')

# Qt modules we never use -> keeps the binary small
EXCLUDES = ['PySide6.QtNetwork', 'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtSql',
            'PySide6.QtTest', 'PySide6.QtOpenGLWidgets', 'PySide6.QtPdf',
            'PySide6.QtConcurrent', 'PySide6.QtXml', 'PySide6.QtDBus', 'PySide6.QtSvg',
            'PySide6.QtHelp', 'PySide6.QtDesigner', 'PySide6.QtMultimedia',
            'tkinter', 'PIL', 'unittest', 'pydoc', 'xmlrpc']

NATIVE = [(os.path.join(ROOT, 'desktop_rug', 'native', 'clothsim.dll' if IS_WIN else 'libclothsim.so'),
           os.path.join('desktop_rug', 'native'))]
if IS_WIN:
    import PySide6
    sw = os.path.join(os.path.dirname(PySide6.__file__), 'opengl32sw.dll')   # Mesa llvmpipe fallback
    if os.path.exists(sw):
        NATIVE.append((sw, 'PySide6'))

a = Analysis([os.path.join(ROOT, 'run_desktop_rug.py')],
             pathex=[ROOT],
             datas=[(os.path.join(ROOT, 'desktop_rug', 'assets'), os.path.join('desktop_rug', 'assets')),
                    (os.path.join(ROOT, 'desktop_rug', 'scripts', 'windows' if IS_WIN else 'linux'),
                     os.path.join('desktop_rug', 'scripts', 'windows' if IS_WIN else 'linux'))],
             binaries=NATIVE,
             hiddenimports=['PySide6.QtOpenGL', 'numpy', 'shiboken6', 'secrets', 'hmac', 'base64'],
             excludes=EXCLUDES,
             noarchive=False)

# drop big unused Qt translations / plugins
def keep(entry):
    name = entry[0].replace('\\', '/')
    bad = ('/translations/', 'qtwebengine', 'Qt6Quick', 'Qt6Qml', 'Qt6Pdf', 'Qt6Network',
           'Qt6VirtualKeyboard', 'imageformats/qpdf', 'Qt6Svg')
    return not any(b.lower() in name.lower() for b in bad)
a.datas = [d for d in a.datas if keep(d)]
a.binaries = [b for b in a.binaries if keep(b)]

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
          name='DesktopRug' if IS_WIN else 'desktop-rug',
          debug=False, strip=False, upx=False, console=False,
          icon=os.path.join(ROOT, 'packaging', 'icon.ico') if IS_WIN else None,
          version=None)
