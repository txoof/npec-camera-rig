# /// script
# requires-python = ">=3.10"
# ///
"""Export groups of AprilTag corner mounts, one Orca-ready 3MF per group.

Each group is an id range (``450-453``) or a single id (``460``), within the
corner/reference range 450-499. All groups are checked before anything is
exported.

Usage:
    uv run corner_tags.py 450-453 454-457
    uv run corner_tags.py 460 -o ~/prints -D plate_gap=15

Writes e.g. ``exports/camera_rig/corner_tags/apriltag_corner_mount_450-453.3mf``.
"""

import argparse
import sys
from pathlib import Path

import scad_to_3mf
from tray_tags import parse_ids

SCAD = scad_to_3mf.HERE / "camera_rig" / "apriltag_corner_mount.scad"
OUTPUT = scad_to_3mf.EXPORTS / "camera_rig" / "corner_tags"

# Must match the tag_ids assert in apriltag_corner_mount.scad (PLAN.md's
# corner/reference range).
FIRST_ID, LAST_ID = 450, 499


def parse_group(spec):
    """Parse a group spec and check it against the corner id range.

    Args:
        spec: ``"lo-hi"`` or a single id ``"n"``.

    Returns:
        (lo, hi).

    Raises:
        ValueError: The spec is malformed, reversed, or outside 450-499.
    """
    lo, hi = parse_ids(spec, spec)
    if lo < FIRST_ID or hi > LAST_ID:
        raise ValueError(f"{spec!r}: ids must be within {FIRST_ID}-{LAST_ID}")
    return lo, hi


def help_epilog():
    """Return the --help text listing the id range, group format and examples.

    Returns:
        Preformatted epilog text.
    """
    return f"""\
ids:
  {FIRST_ID}-{LAST_ID}  corner/reference tags (PLAN.md). Tray tags are 1-299 (tray_tags.py), calibration sheets 300-449

group format:
  FIRST-LAST   a range of ids   450-453
  ID           a single id      460
  Each group writes one file. No spaces inside a group.

examples:
  corner_tags.py 450-453
      ids 450 to 453, one rig's four corners
      -> exports/camera_rig/corner_tags/{SCAD.stem}_450-453.3mf
  corner_tags.py 450-453 454-457
      two files: 450-453 and 454-457
  corner_tags.py 460
      a single mount, id 460
  corner_tags.py 450-453 -D plate_gap=15 -o ~/prints
      more space between mounts, write to ~/prints

refused, nothing exported:
  corner_tags.py 1-4       ids start at {FIRST_ID}
  corner_tags.py 498-501   ids end at {LAST_ID}
  corner_tags.py 453-450   range runs backwards
"""


def main(argv=None):
    """Parse arguments, validate every group, then export each one.

    Args:
        argv: Argument list; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(
        description="Export groups of AprilTag corner mounts, one 3MF per group.",
        epilog=help_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("groups", nargs="+", metavar="GROUP",
                        help="tag ids for one file: 450-453 or 460. "
                             "See group format below")
    parser.add_argument("-o", "--output-dir", type=Path,
                        default=OUTPUT,
                        help="where to write the 3MFs "
                             "(default: exports/camera_rig/corner_tags/)")
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
        sys.exit("corner_tags: nothing exported\n  " + "\n  ".join(errors))

    for lo, hi in groups:
        ids = str(lo) if lo == hi else f"{lo}-{hi}"
        name = f"{SCAD.stem}_{ids}"
        argv = [str(SCAD), "-o", str(args.output_dir), "-n", name,
                "-D", f"tag_ids=[for (i = [{lo}:{hi}]) i]"]
        for d in args.defines:
            argv += ["-D", d]
        scad_to_3mf.main(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
