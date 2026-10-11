#!/bin/sh
# Desktop Rug - DISABLE: close it and stop it starting at login (settings are kept).
CONF="${XDG_CONFIG_HOME:-$HOME/.config}"
CFG="$CONF/desktop-rug"
say() { echo "$1"; command -v notify-send >/dev/null 2>&1 && notify-send -i preferences-desktop-wallpaper "Desktop Rug" "$1" 2>/dev/null; }

rm -f "$CONF/autostart/desktop-rug.desktop" "${XDG_DATA_HOME:-$HOME/.local/share}/desktop-rug/desktop-rug-autostart.sh"
mkdir -p "$CFG/control"
touch "$CFG/autostart-initialized"          # never auto-enable again until Enable is run

# ask the running instance to save and quit, then make sure it is gone
LOCK="${TMPDIR:-/tmp}/desktop-rug-${USER:-$(id -un)}.lock"
PID="$(head -n 1 "$LOCK" 2>/dev/null)"
if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  touch "$CFG/control/quit"
  i=0
  while kill -0 "$PID" 2>/dev/null && [ $i -lt 30 ]; do sleep 0.2; i=$((i+1)); done
  kill "$PID" 2>/dev/null
fi
pkill -x desktop-rug 2>/dev/null
rm -f "$CFG/control/quit"
say "Desktop Rug is DISABLED: closed, and it will not start at login. Settings kept."
