# /// script
# requires-python = ">=3.10"
# ///
"""Export groups of AprilTag tray tags, one Orca-ready 3MF per group.

Each group is an id range (``1-12``) or a single id (``7``), optionally
followed by a style (``1-12:bolt``). Without a style, a group gets its tray
type's default (DEFAULT_STYLE). Every group must fall inside one tray type,
so each file holds one type and its name says which. All groups are checked
before anything is exported.

Usage:
    uv run tray_tags.py 1-12 13-24 101-112
    uv run tray_tags.py 1-12:bolt 101-112:tab -o ~/prints
    uv run tray_tags.py 226-231 -D on_side=false

Writes e.g. ``exports/tray_tags/4x5/apriltag_tray_tag_4x5_1-12_tab.3mf``;
with -o, every file goes straight into that folder.
"""

import argparse
import sys
from pathlib import Path

import scad_to_3mf

SCAD = scad_to_3mf.HERE / "tray_tags" / "apriltag_tray_tag.scad"
OUTPUT = scad_to_3mf.EXPORTS / "tray_tags"  # one subfolder per tray type

# Must match tray_type() in apriltag_tray_tag.scad, which engraves the label.
# Must stay inside TRAY_ID_RANGE in src/npec_rig/tags.py: 300-449 are the
# calibration sheets, 450-499 the corner tags.
# (first id, last id, tray type)
TRAY_TYPES = [
    (1, 75, "4x5"),
    (76, 150, "4x4"),
    (151, 225, "1x1"),
    (226, 299, "OTHER"),
]

STYLES = ("tab", "bolt")  # tag_style values in apriltag_tray_tag.scad

# style used when a group does not name one
DEFAULT_STYLE = {"4x5": "tab", "4x4": "bolt", "1x1": "bolt", "OTHER": "tab"}


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


def parse_ids(ids, spec):
    """Parse an id range or single id.

    Args:
        ids: ``"lo-hi"`` or ``"n"``.
        spec: The whole group spec, for error messages.

    Returns:
        (lo, hi).

    Raises:
        ValueError: ``ids`` is malformed or the range runs backwards.
    """
    parts = ids.split("-")
    if len(parts) not in (1, 2) or not all(p.strip().isdigit() for p in parts):
        raise ValueError(f"{spec!r}: expected an id (7) or a range (FIRST-LAST)")
    lo, hi = int(parts[0]), int(parts[-1])
    if lo > hi:
        raise ValueError(f"{spec!r}: range runs backwards")
    return lo, hi


def parse_group(spec):
    """Parse a group spec and check it against the tray type ranges.

    Args:
        spec: ``"lo-hi"`` or a single id ``"n"``, optionally followed by
            ``":style"``.

    Returns:
        (lo, hi, tray type, style).

    Raises:
        ValueError: The spec is malformed, reversed, outside the allocated
            ids, crosses a tray type boundary, or names an unknown style.
    """
    ids, _, style = spec.partition(":")
    if style and style not in STYLES:
        raise ValueError(f"{spec!r}: style must be one of {', '.join(STYLES)}")
    lo, hi = parse_ids(ids, spec)
    first, last = tray_type(lo), tray_type(hi)
    if first is None or last is None:
        raise ValueError(f"{spec!r}: ids must be within "
                         f"{TRAY_TYPES[0][0]}-{TRAY_TYPES[-1][1]}")
    if first != last:
        raise ValueError(f"{spec!r}: crosses tray types ({first} and {last}); "
                         "split it at the boundary")
    return lo, hi, first, style or DEFAULT_STYLE[first]


def help_epilog():
    """Return the --help text listing tray types, default styles and examples.

    Built from TRAY_TYPES and DEFAULT_STYLE so it cannot drift from them.

    Returns:
        Preformatted epilog text.
    """
    rows = "\n".join(f"  {lo:>3}-{hi:<3}  {name:<6}  {DEFAULT_STYLE[name]}"
                     for lo, hi, name in TRAY_TYPES)
    return f"""\
tray types (a group must stay inside one):
  ids      type    default style
{rows}

styles:
  tab   90 deg tab that hangs over the tray edge
  bolt  flat tab with an M8 clearance hole

group format:
  FIRST-LAST         a range of ids, default style for its type   1-12
  ID                 a single id, default style for its type      7
  FIRST-LAST:STYLE   a range of ids, in STYLE (tab or bolt)       1-12:bolt
  ID:STYLE           a single id, in STYLE                        7:bolt
  Each group writes one file. No spaces inside a group.

examples:
  tray_tags.py 1-12
      ids 1 to 12, 4x5, tab (the default for 4x5)
      -> exports/tray_tags/4x5/{SCAD.stem}_4x5_1-12_tab.3mf
  tray_tags.py 1-12 13-24 101-112
      three files: 4x5 1-12 tab, 4x5 13-24 tab, 4x4 101-112 bolt
  tray_tags.py 1-12:bolt
      ids 1 to 12, 4x5, bolt instead of the default tab
      -> exports/tray_tags/4x5/{SCAD.stem}_4x5_1-12_bolt.3mf
  tray_tags.py 1-6 7-12:bolt 101-106:tab 107-112
      four files, styles mixed: 4x5 tab, 4x5 bolt, 4x4 tab, 4x4 bolt
  tray_tags.py 7:bolt
      a single tag, id 7, bolt
  tray_tags.py 226-231 -D on_side=false -o ~/prints
      lay the tags flat instead of on their side, write to ~/prints

refused, nothing exported:
  tray_tags.py 70-80      crosses 4x5 and 4x4; use 70-75 76-80
  tray_tags.py 0-10       ids start at 1
  tray_tags.py 295-305    ids end at 299 (300-449 are calibration sheets)
  tray_tags.py 1-12:clip  style must be tab or bolt
"""


def main(argv=None):
    """Parse arguments, validate every group, then export each one.

    Args:
        argv: Argument list; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(
        description="Export groups of AprilTag tray tags, one 3MF per group.",
        epilog=help_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("groups", nargs="+", metavar="GROUP",
                        help="tag ids for one file, with an optional style: "
                             "1-12, 7, 1-12:bolt, 7:tab. See group format below")
    parser.add_argument("-o", "--output-dir", type=Path,
                        help="where to write the 3MFs "
                             "(default: exports/tray_tags/<tray type>/)")
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

    for lo, hi, kind, style in groups:
        ids = str(lo) if lo == hi else f"{lo}-{hi}"
        name = f"{SCAD.stem}_{kind}_{ids}_{style}"
        defines = [f"tag_ids=[for (i = [{lo}:{hi}]) i]",
                   f'tag_style="{style}"'] + args.defines
        out_dir = args.output_dir or OUTPUT / kind
        argv = [str(SCAD), "-o", str(out_dir), "-n", name]
        for d in defines:
            argv += ["-D", d]
        scad_to_3mf.main(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
