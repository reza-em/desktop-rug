#!/usr/bin/env bash
# Build the Linux binary (PyInstaller one-file) and an AppImage.
# Usage: ./build_linux.sh            (creates .venv if missing)
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
[ -d .venv ] || $PY -m venv .venv
.venv/bin/pip install -q -r requirements.txt pyinstaller
# compiled cloth solver (optional: the app falls back to numpy without it)
if command -v gcc >/dev/null; then
  gcc -O3 -ffast-math -fno-finite-math-only -shared -fPIC -o desktop_rug/native/libclothsim.so desktop_rug/native/clothsim.c -lm
fi
.venv/bin/python -m PyInstaller --noconfirm --clean --distpath dist/linux --workpath build/linux packaging/desktop-rug.spec
echo "Binary: dist/linux/desktop-rug"

# ---- AppImage ----------------------------------------------------------------
APPDIR=build/AppDir
rm -rf "$APPDIR"; mkdir -p "$APPDIR/usr/bin"
cp dist/linux/desktop-rug "$APPDIR/usr/bin/"
cp desktop_rug/assets/icon.png "$APPDIR/desktop-rug.png"
cp packaging/desktop-rug.desktop "$APPDIR/desktop-rug.desktop"
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/desktop-rug" "$@"
RUN
chmod +x "$APPDIR/AppRun"
TOOL=build/appimagetool-x86_64.AppImage
if [ ! -x "$TOOL" ]; then
  curl -sSL -o "$TOOL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage || true
  chmod +x "$TOOL" || true
fi
if [ -x "$TOOL" ]; then
  ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$APPDIR" dist/linux/DesktopRug-x86_64.AppImage \
    && echo "AppImage: dist/linux/DesktopRug-x86_64.AppImage"
else
  echo "appimagetool not available - skipped AppImage (the one-file binary works on its own)"
fi
