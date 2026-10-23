# /// script
# requires-python = ">=3.10"
# dependencies = ["cadquery-ocp>=7.7"]
# ///
"""Fetch the official Raspberry Pi 5 STEP model and convert it to an STL ghost plus boxes.

OpenSCAD cannot import STEP, so the case files use an STL converted from the
official model as a see-through reference (``libraries/pi5_ghost.scad``). The
model belongs to Raspberry Pi Ltd: its dimensions may be used, but neither the
STEP nor the STL is committed. Both land in ``reference/pi5_step/``, which is
gitignored, and anyone who needs them runs this script.

The STEP is an assembly with a local coordinate system per part. Reading it
through ``STEPControl_Reader.OneShape()`` applies every part's placement, so
the STL comes out in the model's own global frame. ``libraries/pi5_ghost.scad``
then moves that frame onto the case convention.

Usage:
    uv run fetch_pi5_model.py
    uv run fetch_pi5_model.py --force    # download and convert again
"""

import argparse
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "reference" / "pi5_step"
URL = "https://datasheets.raspberrypi.com/rpi5/RaspberryPi5-step.zip"
ZIP = OUT / "RaspberryPi5-step.zip"
STL = OUT / "pi5.stl"
BOXES = OUT / "pi5_boxes.scad"


def download(force):
    """Download the STEP zip unless it is already present."""
    if ZIP.exists() and not force:
        return
    print(f"downloading {URL}")
    # The asset server answers 403 to urllib's default user agent.
    req = urllib.request.Request(URL, headers={"User-Agent": "npec-camera-rig/fetch_pi5_model"})
    with urllib.request.urlopen(req) as resp:
        ZIP.write_bytes(resp.read())


def extract_step():
    """Extract the zip and return the path of the single STEP file in it."""
    with zipfile.ZipFile(ZIP) as z:
        names = [n for n in z.namelist() if n.lower().endswith((".step", ".stp"))]
        if len(names) != 1:
            sys.exit(f"expected one STEP file in {ZIP.name}, found {names}")
        target = OUT / Path(names[0]).name
        target.write_bytes(z.read(names[0]))
    return target


def convert(step, stl, deflection=0.05):
    """Mesh every body of the STEP assembly in its global position and write an STL."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader
    from OCP.StlAPI import StlAPI_Writer

    reader = STEPControl_Reader()
    if reader.ReadFile(str(step)) != IFSelect_RetDone:
        sys.exit(f"could not read {step}")
    reader.TransferRoots()
    shape = reader.OneShape()
    BRepMesh_IncrementalMesh(shape, deflection, False, 0.5, True)
    writer = StlAPI_Writer()
    writer.ASCIIMode = False
    if not writer.Write(shape, str(stl)):
        sys.exit(f"could not write {stl}")
    return shape


def solid_boxes(shape):
    """Return one tight bounding box per solid as (x0, y0, z0, x1, y1, z1).

    The STL is fine to look at but its parts are not closed solids, so
    OpenSCAD cannot intersect it with a case. Boxes are closed, and each one
    holds its whole part, so an empty intersection with the boxes means no
    collision. A box can be larger than its part, so a hit still needs a look.
    """
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    boxes = []
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    while explorer.More():
        box = Bnd_Box()
        BRepBndLib.AddOptimal_s(explorer.Current(), box, True, False)
        p, q = box.CornerMin(), box.CornerMax()
        b = (p.X(), p.Y(), p.Z(), q.X(), q.Y(), q.Z())
        if min(b[i + 3] - b[i] for i in range(3)) > 0.01:
            boxes.append(b)
        explorer.Next()
    return boxes


def volume(b):
    return (b[3] - b[0]) * (b[4] - b[1]) * (b[5] - b[2])


def simplify(boxes, board_top=1.31, min_volume=1.0, edge=1.0, tall=3.0, deep=0.7):
    """Reduce the boxes to the few that matter for fitting a case.

    Keeps a box when any of these hold: its volume is at least min_volume
    (mm^3), it reaches within `edge` mm of the board outline or past it
    (walls), it stands more than `tall` mm above the board top (lid and
    HAT headroom), or it reaches more than `deep` mm below the board bottom
    (floor). Boxes inside a kept box are dropped. Everything else below the
    board is small SMD parts; they are replaced by one depth, returned as the
    lowest z among them, for an underside slab.

    Returns (board, kept, under_z): the PCB box, the kept part boxes, and the
    lowest z of the dropped underside parts.
    """
    board = max(boxes, key=lambda b: (b[3] - b[0]) * (b[4] - b[1]))
    x0, y0, _, x1, y1, _ = board

    def near_edge(b):
        return b[0] < x0 + edge or b[1] < y0 + edge or b[3] > x1 - edge or b[4] > y1 - edge

    def wanted(b):
        return (
            volume(b) >= min_volume
            or near_edge(b)
            or b[5] - board_top > tall
            or b[2] < board[2] - deep
        )

    def inside(b, o, tol=0.05):
        return all(b[i] >= o[i] - tol for i in range(3)) and all(
            b[i + 3] <= o[i + 3] + tol for i in range(3)
        )

    candidates = sorted((b for b in boxes if b is not board and wanted(b)), key=volume, reverse=True)
    kept = []
    for b in candidates:
        if not any(inside(b, o) for o in kept):
            kept.append(b)
    dropped_under = [b for b in boxes if b is not board and not wanted(b) and b[2] < board[2]]
    under_z = min((b[2] for b in dropped_under), default=board[2])
    return board, kept, under_z


def cube_line(b):
    s = [b[i + 3] - b[i] for i in range(3)]
    return (
        f"    translate([{b[0]:.3f}, {b[1]:.3f}, {b[2]:.3f}]) "
        f"cube([{s[0]:.3f}, {s[1]:.3f}, {s[2]:.3f}]);"
    )


def write_boxes(boxes, scad):
    """Write the full and the simplified box sets as OpenSCAD modules."""
    board, kept, under_z = simplify(boxes)
    lines = [
        "// Generated by fetch_pi5_model.py from the official Pi 5 STEP. Do not edit.",
        "// Boxes are in the STEP's own frame. See libraries/pi5_ghost.scad.",
        "",
        f"// {len(boxes)} boxes, one per STEP solid.",
        "module pi5_step_boxes() {",
        *[cube_line(b) for b in boxes],
        "}",
        "",
        "// PCB box (square corners; pi5_ghost.scad draws the rounded outline).",
        f"pi5_step_board = [{', '.join(f'{v:.3f}' for v in board)}];",
        "// Lowest z of the small underside parts folded into one slab.",
        f"pi5_step_under_z = {under_z:.3f};",
        "",
        f"// {len(kept)} part boxes kept by simplify(), PCB excluded.",
        "module pi5_step_simple_parts() {",
        *[cube_line(b) for b in kept],
        "}",
    ]
    scad.write_text("\n".join(lines) + "\n")
    print(f"{len(boxes)} boxes, {len(kept)} kept in the simple set")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="download and convert again")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    download(args.force)
    step = extract_step()
    if STL.exists() and BOXES.exists() and not args.force:
        print(f"{STL.relative_to(HERE)} already exists, use --force to rebuild")
        return
    print(f"converting {step.name}")
    shape = convert(step, STL)
    write_boxes(solid_boxes(shape), BOXES)
    print(f"wrote {STL.relative_to(HERE)} and {BOXES.relative_to(HERE)}")


if __name__ == "__main__":
    main()
