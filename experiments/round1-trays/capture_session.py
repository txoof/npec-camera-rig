"""Round 1 (issue #213): take a step's stills through the rig's capture API and record their IDs.

Method: docs/metrology-log.md section 15.5f. Run only under the `hardware` label. Each still is one
POST /capture; its row (step, title, experiment uuid, experiment folder, still) is added to the
record as soon as it is taken, in the format of experiments/round1/session-2026-10-15.csv. Stills
are spaced start to start. Stops at the first error, or if a still lands outside the expected
experiment (a still with no experiment would go to rig/, not to the session's folder).

    python3 experiments/round1-trays/capture_session.py --experiment pots-2026-10-19 \\
        --step 1 --title "Gaps, nothing moved" --count 10
    python3 experiments/round1-trays/capture_session.py --experiment pots-2026-10-19 \\
        --step 6 --title "Pushed together, nothing moved" --count 120 --every 15

Reads nothing from the experiment folder and writes only the record.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECORD = HERE / "session-2026-10-19.csv"
FIELDS = ["step", "title", "experiment_uuid", "experiment_dir", "still"]


def capture(url: str) -> dict:
    req = urllib.request.Request(f"{url}/capture", method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--experiment", required=True, help="name of the running experiment the stills must land in")
    ap.add_argument("--step", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--every", type=float, default=0, help="seconds start to start (0: one after another)")
    ap.add_argument("--record", type=Path, default=RECORD)
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    args = ap.parse_args(argv)

    new = not args.record.exists()
    with open(args.record, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for k in range(args.count):
            start = time.monotonic()
            try:
                rec = capture(args.url)
            except Exception as exc:  # the rig's message is printed and the run stops
                print(f"step {args.step}, still {k + 1} of {args.count}: capture failed: {exc}", flush=True)
                return 1
            exp = rec.get("experiment") or {}
            still = Path(rec["filename"]).stem
            if exp.get("name") != args.experiment:
                print(f"{still}: in experiment {exp.get('name')!r}, not {args.experiment!r}; not recorded, stopped",
                      flush=True)
                return 1
            w.writerow({"step": args.step, "title": args.title, "experiment_uuid": exp["uuid"],
                        "experiment_dir": exp["folder"], "still": still})
            f.flush()
            flags = "; ".join(rec.get("flags") or []) or "no flags"
            print(f"step {args.step} {k + 1}/{args.count}: {still} lens {rec.get('lens_position')} ({flags})", flush=True)
            if k + 1 < args.count:
                time.sleep(max(0.0, args.every - (time.monotonic() - start)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
