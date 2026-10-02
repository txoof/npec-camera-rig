# /// script
# requires-python = ">=3.10"
# ///
"""Export groups of AprilTag tray tags, one Orca-ready 3MF per group.

Each group is an id range (``1-12``) or a single id (``7``). Every group must
fall inside one tray type, so each file holds one type and its name says
which. All groups are checked before anything is exported.

Usage:
    uv run tray_tags.py 1-12 13-24 101-113
    uv run tray_tags.py 1-12 --style bolt -o ~/prints
    uv run tray_tags.py 301-306 -D on_side=false

Writes e.g. ``exports/apriltag_tray_tag_4x5_1-12_clip.3mf``.
"""

import argparse
import sys
from pathlib import Path

import scad_to_3mf

SCAD = Path(__file__).with_name("apriltag_tray_tag.scad")

# Must match tray_type() in apriltag_tray_tag.scad, which engraves the label.
# (first id, last id, tray type)
TRAY_TYPES = [
    (1, 100, "4x5"),
    (101, 200, "4x4"),
    (201, 300, "1x1"),
    (301, 399, "OTHER"),
]


def tray_type(tag_id):
    """Return the tray type for a tag id.

    Args:
        tag_id: AprilTag 36h11 id.

    Returns:
        The tray type string, or None if the id is not allocated.
    """
    for lo, hi, name in TRAY_TYPES:
        if lo <= tag_id <= hi:
            return name
    return None


def parse_group(spec):
    """Parse a group spec and check it against the tray type ranges.

    Args:
        spec: ``"lo-hi"`` or a single id ``"n"``.

    Returns:
        (lo, hi, tray type).

    Raises:
        ValueError: The spec is malformed, reversed, outside the allocated
            ids, or crosses a tray type boundary.
    """
    parts = spec.split("-")
    if len(parts) not in (1, 2) or not all(p.strip().isdigit() for p in parts):
        raise ValueError(f"{spec!r}: expected an id or a range like 1-12")
    lo, hi = int(parts[0]), int(parts[-1])
    if lo > hi:
        raise ValueError(f"{spec!r}: range runs backwards")
    first, last = tray_type(lo), tray_type(hi)
    if first is None or last is None:
        raise ValueError(f"{spec!r}: ids must be within "
                         f"{TRAY_TYPES[0][0]}-{TRAY_TYPES[-1][1]}")
    if first != last:
        raise ValueError(f"{spec!r}: crosses tray types ({first} and {last}); "
                         "split it at the boundary")
    return lo, hi, first


def main(argv=None):
    """Parse arguments, validate every group, then export each one.

    Args:
        argv: Argument list; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(
        description="Export groups of tray tags, one 3MF per group.")
    parser.add_argument("groups", nargs="+", metavar="GROUP",
                        help="id range like 1-12, or a single id")
    parser.add_argument("--style", choices=["clip", "bolt"], default="clip",
                        help="tag_style for every group (default: clip)")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("exports"),
                        help="where to write the 3MFs (default: ./exports/)")
    parser.add_argument("-D", dest="defines", action="append", default=[],
                        metavar="VAR=VALUE",
                        help="extra Customizer override, passed to OpenSCAD; repeatable")
    args = parser.parse_args(argv)

    groups, errors = [], []
    for spec in args.groups:
        try:
            groups.append(parse_group(spec))
        except ValueError as e:
            errors.append(str(e))
    if errors:
        sys.exit("tray_tags: nothing exported\n  " + "\n  ".join(errors))

    for lo, hi, kind in groups:
        ids = str(lo) if lo == hi else f"{lo}-{hi}"
        name = f"{SCAD.stem}_{kind}_{ids}_{args.style}"
        defines = [f"tag_ids=[for (i = [{lo}:{hi}]) i]",
                   f'tag_style="{args.style}"'] + args.defines
        argv = [str(SCAD), "-o", str(args.output_dir), "-n", name]
        for d in defines:
            argv += ["-D", d]
        scad_to_3mf.main(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
