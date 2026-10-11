#!/usr/bin/env bash
# End-to-end test of first-run autostart + Enable/Disable scripts (Linux, needs $DISPLAY).
# Usage: tools/test_autostart_linux.sh path/to/DesktopRug-x86_64.AppImage
set -u
APP=${1:-dist/linux/DesktopRug-x86_64.AppImage}
REL=$(mktemp -d /tmp/rugrel.XXXX)
cp "$APP" "$REL/DesktopRug-x86_64.AppImage"; cp desktop_rug/scripts/linux/* "$REL/"
DATA=$HOME/.local/share/desktop-rug; AUTO=$HOME/.config/autostart/desktop-rug.desktop
pass=0; fail=0
ok() { if eval "$2"; then echo "PASS  $1"; pass=$((pass+1)); else echo "FAIL  $1"; fail=$((fail+1)); fi; }
running() { pgrep -x desktop-rug >/dev/null; }
waitrun() { for i in $(seq 1 ${1:-40}); do running && return 0; sleep 0.5; done; return 1; }
waitgone() { for i in $(seq 1 ${1:-30}); do running || return 0; sleep 0.5; done; return 1; }
# clean slate (fresh user)
sh "$REL/disable-desktop-rug.sh" >/dev/null 2>&1; rm -rf "$DATA" "$AUTO" ~/.config/desktop-rug/autostart-initialized ~/.local/share/applications/desktop-rug-*.desktop

echo "-- 1. first run of the downloaded AppImage enables autostart (default ON)"
("$REL/DesktopRug-x86_64.AppImage" >/dev/null 2>&1 &); sleep 8
ok "installed copy exists + executable" "[ -x $DATA/DesktopRug.AppImage ]"
ok "XDG autostart entry written" "[ -f $AUTO ] && grep -q 'X-GNOME-Autostart-enabled=true' $AUTO && grep -q 'QT_QPA_PLATFORM=xcb' $AUTO"
ok "Enable/Disable scripts copied next to installed app" "[ -x $DATA/disable-desktop-rug.sh ] && [ -x $DATA/enable-desktop-rug.sh ]"
ok "menu launchers installed" "[ -f ~/.local/share/applications/desktop-rug-disable.desktop ]"
ok "app running" "running"

echo "-- 2. a second launch does not start a second copy"
n1=$(pgrep -c -x desktop-rug); "$DATA/DesktopRug.AppImage" >/dev/null 2>&1; n2=$(pgrep -c -x desktop-rug)
ok "same process count ($n1 -> $n2)" "[ $n1 = $n2 ]"

echo "-- 3. downloaded file deleted + crash/power-off (kill -9): autostart survives"
rm -f "$REL/DesktopRug-x86_64.AppImage"; pkill -9 -x desktop-rug; waitgone
ok "autostart entry still present" "[ -f $AUTO ]"

echo "-- 4. simulated login: run the autostart entry like the session manager"
gio launch "$AUTO" >/dev/null 2>&1 &
for i in $(seq 1 60); do pgrep -f "desktop-rug --autostart" >/dev/null && break; sleep 0.5; done
ok "started from autostart entry (installed copy, --autostart)" "pgrep -f 'desktop-rug --autostart' >/dev/null"
ok "environment has APPIMAGE=installed copy + QT_QPA_PLATFORM=xcb" "for p in \$(pgrep -f 'desktop-rug --autostart'); do tr '\\0' '\\n' < /proc/\$p/environ; done | grep -q 'APPIMAGE=$DATA/DesktopRug.AppImage' && for p in \$(pgrep -f 'desktop-rug --autostart'); do tr '\\0' '\\n' < /proc/\$p/environ; done | grep -q QT_QPA_PLATFORM=xcb"
sleep 6

echo "-- 5. Quit (same as tray Quit) does not disable autostart"
"$DATA/DesktopRug.AppImage" --quit-running >/dev/null 2>&1; waitgone
ok "process closed" "! running"
ok "autostart still enabled" "[ -f $AUTO ]"

echo "-- 6. Enable script (double-click launcher from the release folder)"
gio launch "$REL/Desktop Rug - Enable.desktop" >/dev/null 2>&1; waitrun 60
ok "running after Enable" "running"
ok "autostart enabled" "[ -f $AUTO ]"
sleep 6

echo "-- 7. Disable script (double-click launcher)"
gio launch "$REL/Desktop Rug - Disable.desktop" >/dev/null 2>&1; waitgone 30
ok "process killed" "! running"
ok "autostart entry removed" "[ ! -f $AUTO ]"
ok "settings kept" "[ -f ~/.config/desktop-rug/settings.json ]"

echo "-- 8. after Disable, a manual start does NOT re-enable autostart"
("$DATA/DesktopRug.AppImage" >/dev/null 2>&1 &); waitrun 40; sleep 4
ok "still disabled" "[ ! -f $AUTO ]"
sh "$DATA/disable-desktop-rug.sh" >/dev/null; waitgone

echo "-- 9. enable-desktop-rug.sh from the installed folder (no download needed)"
sh "$DATA/enable-desktop-rug.sh" >/dev/null; waitrun 60
ok "running + autostart" "running && [ -f $AUTO ]"
sleep 5; sh "$DATA/disable-desktop-rug.sh" >/dev/null; waitgone
ok "disabled again" "! running && [ ! -f $AUTO ]"
echo "RESULT: $pass passed, $fail failed"
rm -rf "$REL"
