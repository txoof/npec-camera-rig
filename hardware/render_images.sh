#!/usr/bin/env bash
# Renders every standalone .scad in camera_rig/, tray_tags/, calibration_targets/
# and libraries/ to a diagonal-perspective PNG in images/, overwriting any
# existing PNGs by default.
# Skips BOSL2 and the `use`-only AprilTag library files, which draw nothing.
set -euo pipefail

OPENSCAD="/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGES_DIR="$SCRIPT_DIR/images"
IMGSIZE="1000,1000"
CAMERA="0,0,0,55,0,25,0"
SKIP="apriltag_36h11.scad apriltags-36h11-0-586.scad"

mkdir -p "$IMAGES_DIR"
cd "$SCRIPT_DIR"

shopt -s nullglob
for scad_file in camera_rig/*.scad tray_tags/*.scad calibration_targets/*.scad libraries/*.scad; do
  case " $SKIP " in *" ${scad_file##*/} "*) continue ;; esac
  name="$(basename "$scad_file" .scad)"
  out="$IMAGES_DIR/${name}.png"
  echo "=== $scad_file -> images/${name}.png ==="
  "$OPENSCAD" \
    --render=cgal \
    --imgsize="$IMGSIZE" \
    --projection=perspective \
    --camera="$CAMERA" \
    --viewall --autocenter \
    -o "$out" \
    "$scad_file"
done
