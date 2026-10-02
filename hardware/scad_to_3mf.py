# /// script
# requires-python = ">=3.10"
# ///
"""Export a multi-color OpenSCAD design as a 3MF that Orca/Bambu load ready to print.

OpenSCAD's lazy-union 3MF export writes each colored top-level solid as a
separate build item. Orca drops each of those to the bed independently and
ignores OpenSCAD's colors. This script runs the export, then rewrites the 3MF
so each printed item's solids become parts of one object (keeping their
authored positions) -- one object per printed item on a laid-out plate, see
group_parts() -- and adds Orca's Metadata/model_settings.config assigning one
filament per distinct color, numbered in the order the colors first appear.

Usage:
    uv run scad_to_3mf.py camera_rig/part.scad
    uv run scad_to_3mf.py camera_rig/part.scad -o ~/prints -D 'tag_ids=[350,351,352]'
    uv run scad_to_3mf.py camera_rig/part.scad -n tags_12-24 -D 'tag_ids=[for (i = [12:24]) i]'
Without -o, writes to exports/ mirroring the source folder, e.g.
``camera_rig/part.scad`` -> ``exports/camera_rig/part.3mf``.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPORTS = HERE / "exports"
DEFAULT_OPENSCAD = "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"
MODEL = "3D/3dmodel.model"
CONFIG = "Metadata/model_settings.config"


def run_openscad(openscad, scad, out, defines):
    """Run the lazy-union 3MF export and return OpenSCAD's combined log."""
    cmd = [
        openscad, "--enable=lazy-union", "--render=cgal",
        "-O", "export-3mf/color-mode=model",
        "-O", "export-3mf/material-type=color",
        "-o", str(out),
    ]
    for define in defines:
        cmd += ["-D", define]
    cmd.append(str(scad))
    result = subprocess.run(cmd, capture_output=True, text=True)
    log = result.stdout + result.stderr
    if result.returncode != 0 or not out.exists():
        sys.exit(f"scad_to_3mf: OpenSCAD export failed\n{log}")
    return log


def mesh_objects(xml):
    """Return [(object_id, color_hex, (xmin, xmax, ymin, ymax))] per build item."""
    colors = re.findall(r'<m:color color="([^"]*)"', xml)
    bodies = {
        m.group(1): m.group(2)
        for m in re.finditer(r'<object id="(\d+)"[^>]*>(.*?)</object>', xml, re.S)
    }
    parts = []
    for oid in re.findall(r'<item objectid="(\d+)"', xml):
        body = bodies[oid]
        indices = sorted(set(re.findall(r'p1="(\d+)"', body)))
        if len(indices) != 1:
            print(f"scad_to_3mf: warning: object {oid} carries {len(indices)} "
                  "colors; it will get one filament. Put each color in its own "
                  "top-level statement.", file=sys.stderr)
        color = colors[int(indices[0])] if indices else "#FFFFFFFF"
        xy = re.findall(r'<vertex x="([^"]*)" y="([^"]*)"', body)
        xs = [float(x) for x, _ in xy]
        ys = [float(y) for _, y in xy]
        parts.append((oid, color, (min(xs), max(xs), min(ys), max(ys))))
    return parts


def group_parts(parts):
    """Group parts into printed items: one anchor part each plus its attachments.

    The anchor color is the one whose parts cover the most XY bounding-box
    area (a mount's body, not its tag layer). Each anchor-color part starts
    its own group; parts of the same color are never merged, so nested items
    whose bounding boxes overlap (e.g. apriltag_tray_tag.scad on its side)
    stay separate objects. Every other part joins the anchor whose bounding
    box overlaps its own and that sits nearest to it in build order, the
    earlier one on a tie -- so a .scad that emits each item's statements
    together (body, then its tag layer) pairs them correctly even when a tag
    layer's box also overlaps a neighbour's body. A part that overlaps no
    anchor is its own group.
    """
    def area(b):
        return (b[1] - b[0]) * (b[3] - b[2])

    def overlaps(a, b):
        return a[0] < b[1] and b[0] < a[1] and a[2] < b[3] and b[2] < a[3]

    totals = {}
    for _, color, box in parts:
        totals[color] = totals.get(color, 0.0) + area(box)
    anchor_color = max(totals, key=totals.get)

    anchors = [i for i, (_, color, _) in enumerate(parts) if color == anchor_color]
    groups = {i: [parts[i]] for i in anchors}
    loose = []
    for i, (_, color, box) in enumerate(parts):
        if color == anchor_color:
            continue
        hits = [a for a in anchors if overlaps(box, parts[a][2])]
        if hits:
            groups[min(hits, key=lambda a: (abs(a - i), a > i))].append(parts[i])
        else:
            loose.append([parts[i]])
    return list(groups.values()) + loose


def wrap_as_objects(xml, groups):
    """Make each group one parent object of components, one build item each."""
    next_id = max(int(i) for i in re.findall(r'<object id="(\d+)"', xml)) + 1
    parent_ids = list(range(next_id, next_id + len(groups)))
    parents = []
    for pid, group in zip(parent_ids, groups):
        components = "\n".join(
            f'\t\t\t\t<component objectid="{oid}" p:UUID="{uuid.uuid4()}"/>'
            for oid, _, _ in group
        )
        parents.append(
            f'\t\t<object id="{pid}" name="OpenSCAD Assembly" type="model" '
            f'p:UUID="{uuid.uuid4()}">\n'
            f"\t\t\t<components>\n{components}\n\t\t\t</components>\n"
            f"\t\t</object>"
        )
    xml = xml.replace("</resources>", "\n".join(parents) + "\n\t</resources>", 1)
    items = "\n".join(
        f'\t\t<item objectid="{pid}" p:UUID="{uuid.uuid4()}"/>' for pid in parent_ids
    )
    build = f'<build p:UUID="{uuid.uuid4()}">\n{items}\n\t</build>'
    return re.sub(r"<build.*?</build>", build, xml, count=1, flags=re.S), parent_ids


def filament_config(parent_ids, groups, name):
    """Build model_settings.config; returns (xml, {color: filament})."""
    filaments = {}
    for group in groups:
        for _, color, _ in group:
            filaments.setdefault(color, len(filaments) + 1)
    objects = []
    for n, (pid, group) in enumerate(zip(parent_ids, groups), start=1):
        label = name if len(groups) == 1 else f"{name} {n}"
        entries = "\n".join(
            f'    <part id="{oid}" subtype="normal_part">\n'
            f'      <metadata key="name" value="{color[:7]}"/>\n'
            f'      <metadata key="extruder" value="{filaments[color]}"/>\n'
            f"    </part>"
            for oid, color, _ in group
        )
        objects.append(
            f'  <object id="{pid}">\n'
            f'    <metadata key="name" value="{label}"/>\n'
            '    <metadata key="extruder" value="1"/>\n'
            f"{entries}\n  </object>"
        )
    config = ('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n'
              + "\n".join(objects) + "\n</config>\n")
    return config, filaments


def convert(raw, dst, name):
    """Rewrite OpenSCAD's raw 3MF at raw into an Orca-ready 3MF at dst."""
    with zipfile.ZipFile(raw) as zin:
        entries = {n: zin.read(n) for n in zin.namelist()}
    xml = entries[MODEL].decode("utf-8")
    groups = group_parts(mesh_objects(xml))
    xml, parent_ids = wrap_as_objects(xml, groups)
    config, filaments = filament_config(parent_ids, groups, name)
    entries[MODEL] = xml.encode("utf-8")
    entries[CONFIG] = config.encode("utf-8")
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for n, data in entries.items():
            zout.writestr(n, data)
    return groups, filaments


def default_output_dir(scad):
    """Return the exports/ folder that mirrors scad's source folder.

    Args:
        scad: Path to the .scad file.

    Returns:
        ``exports/<folder>`` for a file under this directory, else ``exports``.
    """
    try:
        return EXPORTS / scad.resolve().parent.relative_to(HERE)
    except ValueError:
        return EXPORTS


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Export a multi-color .scad as an Orca-ready 3MF.")
    parser.add_argument("scad", type=Path, help="OpenSCAD source file")
    parser.add_argument("-o", "--output-dir", type=Path,
                        help="where to write <name>.3mf (default: exports/<source folder>/)")
    parser.add_argument("-n", "--name",
                        help="output file stem and Orca object name "
                             "(default: the .scad file's stem)")
    parser.add_argument("-D", dest="defines", action="append", default=[],
                        metavar="VAR=VALUE",
                        help="override a Customizer variable, as OpenSCAD's -D; repeatable")
    parser.add_argument("--openscad",
                        default=os.environ.get("OPENSCAD", DEFAULT_OPENSCAD),
                        help="OpenSCAD binary (default: $OPENSCAD or the macOS app)")
    args = parser.parse_args(argv)

    if not args.scad.is_file():
        sys.exit(f"scad_to_3mf: no such file: {args.scad}")
    out_dir = args.output_dir or default_output_dir(args.scad)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = args.name or args.scad.stem
    dst = out_dir / f"{name}.3mf"

    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.3mf"
        run_openscad(args.openscad, args.scad, raw, args.defines)
        groups, filaments = convert(raw, dst, name)

    n_parts = sum(len(g) for g in groups)
    print(f"{dst}: {len(groups)} object(s), {n_parts} parts")
    for color, n in filaments.items():
        print(f"  filament {n}: {color[:7]}")
    if all(len(g) < 2 for g in groups):
        print("scad_to_3mf: warning: no object has more than one part; each "
              "color must be its own top-level statement", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
