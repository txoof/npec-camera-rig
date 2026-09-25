#!/usr/bin/env bash
# Renders every .scad file in this directory to a diagonal-perspective PNG
# in images/, overwriting any existing PNGs by default.
set -euo pipefail

OPENSCAD="/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGES_DIR="$SCRIPT_DIR/images"
IMGSIZE="1000,1000"
CAMERA="0,0,0,55,0,25,0"

mkdir -p "$IMAGES_DIR"
cd "$SCRIPT_DIR"

shopt -s nullglob
for scad_file in *.scad; do
  name="${scad_file%.scad}"
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
