#!/bin/sh
# Desktop Rug - ENABLE: install for this user, start at login, start now.
HERE="$(cd "$(dirname "$0")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/desktop-rug"
CONF="${XDG_CONFIG_HOME:-$HOME/.config}"
DEST="$DATA/DesktopRug.AppImage"
say() { echo "$1"; command -v notify-send >/dev/null 2>&1 && notify-send -i preferences-desktop-wallpaper "Desktop Rug" "$1" 2>/dev/null; }

SRC=""
for f in "$HERE"/DesktopRug*.AppImage "$HERE"/../DesktopRug*.AppImage "$DEST"; do
  [ -f "$f" ] && { SRC="$f"; break; }
done
[ -n "$SRC" ] || { say "DesktopRug AppImage not found next to this script."; exit 1; }
chmod +x "$SRC" 2>/dev/null

run_app() {   # AppImage needs FUSE; fall back to extract-and-run without it
  "$SRC" "$@" 2>/dev/null || APPIMAGE_EXTRACT_AND_RUN=1 "$SRC" "$@"
}

# 1) the app copies itself to ~/.local/share/desktop-rug and writes the XDG autostart entry
run_app --enable-autostart >/dev/null
# 2) belt and braces, in case step 1 could not run
if [ ! -f "$CONF/autostart/desktop-rug.desktop" ]; then
  mkdir -p "$DATA" "$CONF/autostart"
  [ "$SRC" = "$DEST" ] || cp -f "$SRC" "$DEST"
  chmod +x "$DEST"
  cat > "$CONF/autostart/desktop-rug.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Desktop Rug
Exec=sh -c "sleep 6; exec env QT_QPA_PLATFORM=xcb '$DEST' --autostart"
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=4
DESK
fi
# 3) start it now (it never runs twice; a second start only shows the running one)
LAUNCHER="$DATA/desktop-rug-autostart.sh"
if [ -x "$LAUNCHER" ]; then
  DESKTOP_RUG_AUTOSTART_DELAY=0 nohup setsid "$LAUNCHER" >/dev/null 2>&1 &
else
  [ -n "$DISPLAY" ] && export QT_QPA_PLATFORM=xcb
  nohup setsid "$DEST" >/dev/null 2>&1 &
fi
say "Desktop Rug is ENABLED: running now and it will start after every reboot."
