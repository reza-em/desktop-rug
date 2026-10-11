#!/usr/bin/env bash
# Cross-build the Windows .exe on Linux with Wine + Windows CPython (NuGet package)
# + PyInstaller. Produces dist/windows/DesktopRug.exe
set -euo pipefail
cd "$(dirname "$0")"
WB=${WINBUILD_DIR:-$PWD/build/wine}
export WINEPREFIX=$WB/prefix WINEDEBUG=-all WINEARCH=win64
mkdir -p "$WB"
WPY="$WB/py/tools/python.exe"
RUN="xvfb-run -a"
command -v wine >/dev/null || { echo "install wine (apt install wine wine64) first"; exit 1; }
if [ ! -f "$WPY" ]; then
  curl -sSL -o "$WB/python.nupkg" https://www.nuget.org/api/v2/package/python/3.12.10
  rm -rf "$WB/py"; mkdir -p "$WB/py"; (cd "$WB/py" && unzip -q ../python.nupkg)
  $RUN wineboot -i
  $RUN wine "$WPY" -m ensurepip
fi
if command -v x86_64-w64-mingw32-gcc >/dev/null; then
  x86_64-w64-mingw32-gcc -O3 -ffast-math -fno-finite-math-only -shared -static-libgcc \
    -o desktop_rug/native/clothsim.dll desktop_rug/native/clothsim.c
fi
$RUN wine "$WPY" -m pip install -q --no-warn-script-location -r requirements-windows.txt pyinstaller
$RUN wine "$WPY" -m PyInstaller --noconfirm --clean --distpath dist/windows --workpath build/windows packaging/desktop-rug.spec
ls -la dist/windows
