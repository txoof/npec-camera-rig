# 444-amd-reprocess

Scripts that finished the full Reprocess of experiment 18 (#444) on an x86_64 Linux box instead of
the rig, after ac-testing went offline mid-run (#511). The result and its numbers are in
`docs/metrology-log.md` section 41.

The method is the app's own: every script calls `tray_readings.read_photo(path, reuse_mask=True)`,
the same per-photo call `tray_readings._run_reprocess` makes. Nothing under `src/` was changed, and
the app code was checked out at `9498c0f` (v0.5.0), the commit ac-testing ran.

`snapshot.py` and `compare.py` are not duplicated here: the ones in
`experiments/444-full-reprocess/code/` were used unchanged, with the hard-coded database path
substituted at run time.

## What each script does

| Script | What it does |
|---|---|
| `check_capture_files.py` | Every capture path of the experiment must exist as a file. A missing photo makes Reprocess keep the old values and list the photo as failed, so an incomplete copy would look like a result. Must read 0 missing before anything else. |
| `match_libraries.py` | Diffs the rig's Python, numpy, Pillow, OpenCV and libjpeg versions against this box's, from the rig's `dpkg` status and venv dist-info list. Reports; installs nothing. |
| `pick_sample.py` | Picks the photos for the Pi-against-AMD comparison: the rig's own failures, flagged readings, tray 1, the benchmark trays, lit and dark photos, then a spread. |
| `run_photos.py` | Runs the per-photo call over a list of paths. `--slice i/n` takes contiguous block `i` of `n` — contiguous, not every n-th, because the exclusion "visit" rule reads the photos before this one. |
| `compare_runs.py` | Compares two `rig.db` files reading for reading over one list of photos, against the 0.01 mm² pass rule. Used both for rig-against-box and for serial-against-parallel. |
| `preflight_checks.sh` | The checks that must pass before a run: unit tests, `quick_check`, schema version, `/api/about`, the dry-run count, and 0 missing capture files. |
| `chain.sh` | Runs serial-against-parallel, gates on it, and only then starts the full run. Unattended. |
| `status.sh` | One readable line of progress: photos done, failures with reasons, seconds per photo, memory. |
| `heartbeat.sh` | Appends `status.sh` to the run log every 5 minutes so a long run can be watched. |
| `set_env.sh.template` | The six `NPEC_RIG_*` variables, pointed at a copy of the rig's data. |

## Two things worth knowing before reusing these

**Do not cap a worker with `ulimit -v`.** One worker of the full run aborted with
`cannot allocate memory for thread-local data` under a 6 GB virtual cap while its actual resident
memory was about 600 MB. OpenCV's thread pools reserve large virtual arenas. Cap resident memory or
the worker count instead; the 1,884 photos that worker never reached had to be redone.

**The runner does not maintain `reprocess_run` / `reprocess_failure`.** It calls `read_photo`
directly to get parallelism, which bypasses the bookkeeping `start_reprocess` would do. The run's
row and its failure rows were written afterwards by hand. Readings are unaffected; a rig loading
such a database would otherwise misreport the Reprocess as unfinished.
