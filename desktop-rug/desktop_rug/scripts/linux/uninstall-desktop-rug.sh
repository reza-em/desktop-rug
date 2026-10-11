#!/bin/sh
# Desktop Rug - UNINSTALL: disable, close, remove the installed copy AND the settings.
HERE="$(cd "$(dirname "$0")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/desktop-rug"
CFG="${XDG_CONFIG_HOME:-$HOME/.config}/desktop-rug"
APP=""
for f in "$HERE"/DesktopRug*.AppImage "$DATA/DesktopRug.AppImage"; do [ -f "$f" ] && { APP="$f"; break; }; done
[ -n "$APP" ] && { "$APP" --restore-wallpaper 2>/dev/null || APPIMAGE_EXTRACT_AND_RUN=1 "$APP" --restore-wallpaper; } >/dev/null 2>&1
sh "$HERE/disable-desktop-rug.sh" >/dev/null 2>&1 || true
rm -rf "$DATA" "$CFG"
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/desktop-rug-enable.desktop" "${XDG_DATA_HOME:-$HOME/.local/share}/applications/desktop-rug-disable.desktop"
echo "Desktop Rug has been removed."
command -v notify-send >/dev/null 2>&1 && notify-send "Desktop Rug" "Desktop Rug has been removed." 2>/dev/null
exit 0
