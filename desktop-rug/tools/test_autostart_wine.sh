#!/usr/bin/env bash
# Test the Windows exe's autostart + Enable/Disable .bat files under Wine.
# Usage: WINEPREFIX=... tools/test_autostart_wine.sh dist/windows/DesktopRug.exe
set -u
EXE=${1:-dist/windows/DesktopRug.exe}
export WINEDEBUG=-all
REL=$(mktemp -d /tmp/rugwin.XXXX)
cp "$EXE" "$REL/DesktopRug.exe"
for f in desktop_rug/scripts/windows/*.bat; do cp "$f" "$REL/"; done
cp desktop_rug/scripts/windows/Enable-DesktopRug.bat "$REL/فعال‌سازی فرش.bat"
cp desktop_rug/scripts/windows/Disable-DesktopRug.bat "$REL/غیرفعال‌سازی فرش.bat"
W=$(winepath -w "$REL")
LAD="$WINEPREFIX/drive_c/users/$USER/AppData/Local"
RUN='HKCU\Software\Microsoft\Windows\CurrentVersion\Run'
pass=0; fail=0
ok() { if eval "$2"; then echo "PASS  $1"; pass=$((pass+1)); else echo "FAIL  $1"; fail=$((fail+1)); fi; }
# only Wine processes (their command line is a Windows path), not this script's own arguments
wp() { pgrep -af 'DesktopRug\.exe' | grep -E '^[0-9]+ [A-Za-z]:\\'; }
gui() { wp | grep -v -- '--\(enable\|disable\|quit\|uninstall\|wallpaper\|restore\)' | grep -v 'cmd' | grep -q .; }
waitgui() { for i in $(seq 1 ${1:-60}); do gui && return 0; sleep 0.5; done; return 1; }
waitnogui() { for i in $(seq 1 ${1:-40}); do gui || return 0; sleep 0.5; done; return 1; }
runkey() { wine reg query "$RUN" /v DesktopRug 2>/dev/null | tr -d '\r' | grep DesktopRug; }
bat() { # output to a file: the started app inherits the console handles, a pipe would never close
  (cd "${2:-$REL}" && timeout 120 wine cmd /c "$1" > /tmp/bat_out.txt 2>&1 < /dev/null); tr -d '\r' < /tmp/bat_out.txt | grep -v '^$' | sed 's/^/   | /'; }
ngui() { wp | grep -v -- '--\(enable\|disable\|quit\|uninstall\|wallpaper\|restore\)' | grep -vc 'cmd'; }

# clean slate
wineserver -k 2>/dev/null; wine reg delete "$RUN" /v DesktopRug /f >/dev/null 2>&1
rm -rf "$LAD/DesktopRug" "$LAD/desktop-rug/autostart-initialized"

echo "-- 1. first run enables autostart (default ON) and installs to %LOCALAPPDATA%\\DesktopRug"
(cd "$REL" && wine DesktopRug.exe >/dev/null 2>&1 &); waitgui 60; sleep 8
ok "installed copy exists" "[ -f '$LAD/DesktopRug/DesktopRug.exe' ]"
ok "HKCU Run key points at installed copy with --autostart" "runkey | grep -qi 'AppData.Local.DesktopRug.DesktopRug.exe\" --autostart'"
ok "Enable/Disable bats (ASCII + Persian names) copied next to it" "[ -f '$LAD/DesktopRug/Disable-DesktopRug.bat' ] && [ -f '$LAD/DesktopRug/غیرفعال‌سازی فرش.bat' ]"
ok "app running" "gui"
echo "   Run value: $(runkey)"

echo "-- 2. --quit-running (= tray Quit) closes it but keeps autostart"
(cd "$REL" && wine DesktopRug.exe --quit-running >/dev/null 2>&1 < /dev/null); waitnogui 30
ok "closed" "! gui"
ok "Run key still present" "runkey >/dev/null"

echo "-- 3. simulated login: run the Run-key command line"
CMD=$(runkey | sed 's/.*REG_SZ *//')
(eval "wine $CMD" >/dev/null 2>&1 &); waitgui 90
ok "started from the Run key command" "gui"
sleep 3; c1=$(ngui); (cd "$REL" && timeout 60 wine DesktopRug.exe >/dev/null 2>&1 < /dev/null); sleep 2; c2=$(ngui)
ok "single instance: a second start exits (gui processes $c1 -> $c2)" "[ $c1 -eq $c2 ]"

echo "-- 4. Persian-named Disable bat"
bat "غیرفعال‌سازی فرش.bat"; waitnogui 30
ok "process killed" "! gui"
ok "Run key removed" "! runkey >/dev/null"
ok "settings kept" "[ -f '$LAD/desktop-rug/settings.json' ]"

echo "-- 5. Persian-named Enable bat"
bat "فعال‌سازی فرش.bat"; waitgui 90
ok "running after Enable" "gui"
ok "Run key added" "runkey >/dev/null"
sleep 5

echo "-- 6. ASCII Disable / Enable bats"
bat Disable-DesktopRug.bat; waitnogui 30
ok "Disable-DesktopRug.bat: killed + Run key removed" "! gui && ! runkey >/dev/null"
bat Enable-DesktopRug.bat; waitgui 90
ok "Enable-DesktopRug.bat: running + Run key" "gui && runkey >/dev/null"
sleep 5

echo "-- 7. Disable bat from the installed folder after the download folder is deleted"
rm -f "$REL/DesktopRug.exe"
bat Disable-DesktopRug.bat "$LAD/DesktopRug"; waitnogui 30
ok "disabled from installed folder" "! gui && ! runkey >/dev/null"
echo "RESULT: $pass passed, $fail failed"
wineserver -k 2>/dev/null
rm -rf "$REL"
