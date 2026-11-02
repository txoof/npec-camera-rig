"""Run one tray finder over the test stills: python run.py MODULE:FUNCTION --version vN [--notes ...]."""

import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("finder", help="module:function, e.g. methods_blue:find")
ap.add_argument("--version", required=True)
ap.add_argument("--notes", default="")
ap.add_argument("--rig", choices=harness.RIGS, help="one set only")
ap.add_argument("--pictures", default="layouts", choices=("layouts", "all", "none"))
a = ap.parse_args()
mod, fn = a.finder.split(":")
find = getattr(importlib.import_module(mod), fn)
harness.run(mod.removeprefix("methods_") + "-" + fn if fn != "find" else mod.removeprefix("methods_"),
            find, a.version, a.notes, rigs=(a.rig,) if a.rig else harness.RIGS, pictures=a.pictures)
