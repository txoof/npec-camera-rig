# /// script
# requires-python = ">=3.10"
# ///
"""Export a multi-color OpenSCAD design as a 3MF that Orca/Bambu load ready to print.

OpenSCAD's lazy-union 3MF export writes each colored top-level solid as a
separate build item. Orca drops each of those to the bed independently and
ignores OpenSCAD's colors. This script runs the export, then rewrites the 3MF
so solids whose XY footprints overlap become parts of one object (keeping
their authored positions) -- one object per printed item on a laid-out
plate -- and adds Orca's Metadata/model_settings.config assigning one
filament per distinct color, numbered in the order the colors first appear.

Usage:
    uv run scad_to_3mf.py part.scad
    uv run scad_to_3mf.py part.scad -o ~/prints -D 'tag_ids=[450,451,452]'
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
    """Group parts whose XY footprints overlap: one group per printed item.

    Parts of one mount (body plus its tag layer) overlap in plan view; separate
    mounts on a laid-out plate are `plate_gap` apart and do not.
    """
    root = list(range(len(parts)))

    def find(i):
        while root[i] != i:
            root[i] = root[root[i]]
            i = root[i]
        return i

    for i, (_, _, a) in enumerate(parts):
        for j in range(i + 1, len(parts)):
            b = parts[j][2]
            if a[0] < b[1] and b[0] < a[1] and a[2] < b[3] and b[2] < a[3]:
                root[find(j)] = find(i)

    groups = {}
    for i in range(len(parts)):
        groups.setdefault(find(i), []).append(parts[i])
    return list(groups.values())


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


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Export a multi-color .scad as an Orca-ready 3MF.")
    parser.add_argument("scad", type=Path, help="OpenSCAD source file")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("exports"),
                        help="where to write <name>.3mf (default: ./exports/)")
    parser.add_argument("-D", dest="defines", action="append", default=[],
                        metavar="VAR=VALUE",
                        help="override a Customizer variable, as OpenSCAD's -D; repeatable")
    parser.add_argument("--openscad",
                        default=os.environ.get("OPENSCAD", DEFAULT_OPENSCAD),
                        help="OpenSCAD binary (default: $OPENSCAD or the macOS app)")
    args = parser.parse_args(argv)

    if not args.scad.is_file():
        sys.exit(f"scad_to_3mf: no such file: {args.scad}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dst = args.output_dir / f"{args.scad.stem}.3mf"

    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.3mf"
        run_openscad(args.openscad, args.scad, raw, args.defines)
        groups, filaments = convert(raw, dst, args.scad.stem)

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
