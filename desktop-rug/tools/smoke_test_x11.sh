#!/usr/bin/env bash
# Interactive smoke test (cloth version) on an X server ($DISPLAY) with a
# compositing WM, tools/fake_desktop.py and the rug running with
#   --settings $SETTINGS  (pose is read back from it so coordinates follow the rug)
# Usage: tools/smoke_test_x11.sh OUTDIR SETTINGS.json
set -e
OUT=${1:-screenshots}; SETTINGS=${2:-/tmp/rt.json}
mkdir -p "$OUT"
G() { python3 - "$SETTINGS" "$@" <<'PY'
import json, math, sys
d = json.load(open(sys.argv[1])); a = math.radians(d["angle"])
x, y = float(sys.argv[2]), float(sys.argv[3])
print(int(round(d["cx"] + x*math.cos(a) - y*math.sin(a))), int(round(d["cy"] + x*math.sin(a) + y*math.cos(a))))
PY
}
W() { python3 -c "import json;d=json.load(open('$SETTINGS'));print(d['w']/2, d['h']/2)"; }
drag() { # x0 y0 x1 y1 [steps] [button]
  local n=${5:-50} b=${6:-1}
  xdotool mousemove $1 $2 sleep 0.15 mousedown $b
  for i in $(seq 1 $n); do
    xdotool mousemove $(( $1 + ($3-$1)*i/n )) $(( $2 + ($4-$2)*i/n )) sleep 0.02
  done
  sleep 0.25; xdotool mouseup $b; }
settle() { sleep ${1:-3}; xdotool mousemove 1250 780; sleep 0.3; }
shot() { import -window root "$OUT/$1.png"; echo "  shot $1"; }
read HW HH < <(W)
shot 01_flat
echo "1) grab the bottom-right corner and fold it all the way over"
read X0 Y0 < <(G $(python3 -c "print($HW-6, $HH-6)"))
read X1 Y1 < <(G -90 -120)
drag $X0 $Y0 $X1 $Y1 70
settle 3.5; shot 02_corner_folded
echo "2) click + drag desktop icons into the revealed area"
read RX RY < <(G $(python3 -c "print($HW-60, $HH-50)"))
xdotool mousemove $RX $RY click 1; sleep 0.4
drag 1010 120 $RX $RY 25
read R2X R2Y < <(G $(python3 -c "print($HW-140, $HH-40)"))
drag 1120 225 $R2X $R2Y 25
read R3X R3Y < <(G $(python3 -c "print($HW-40, $HH-140)"))
drag 1010 330 $R3X $R3Y 25
settle 1; shot 03_icons_in_revealed_area
echo "3) click the folded rug -> it unfolds (animated) and hides the icons"
read CX CY < <(G -150 -40)
xdotool mousemove $CX $CY click 1
settle 4; shot 04_unfolded_icons_hidden
echo "4) click the formerly folded corner -> re-fold"
read KX KY < <(G $(python3 -c "print($HW-40, $HH-40)"))
xdotool mousemove $KX $KY click 1
settle 4; shot 05_refolded
xdotool mousemove $CX $CY click 1; settle 4
echo "5) fold from the left edge"
read EX EY < <(G $(python3 -c "print(-$HW+4, 0)"))
read EX1 EY1 < <(G 60 0)
drag $EX $EY $EX1 $EY1 60
settle 3.5; shot 06_edge_folded
read CX CY < <(G 150 0)
xdotool mousemove $CX $CY click 1; settle 4; shot 07_edge_unfolded
echo "6) Ctrl+drag right edge (resize), Shift+drag (rotate), middle-drag (move)"
read RX RY < <(G $(python3 -c "print($HW-6, 0)"))
xdotool keydown ctrl; drag $RX $RY $((RX+50)) $RY 20; xdotool keyup ctrl; settle 1.5
read SX SY < <(G -150 -100)
xdotool keydown shift; drag $SX $SY $((SX-40)) $((SY+60)) 25; xdotool keyup shift; settle 1.5
read MX MY < <(G 0 0)
drag $MX $MY $((MX-40)) $((MY+20)) 20 2; settle 2
shot 08_resized_rotated_moved
echo done
