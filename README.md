# NPEC Camera Rig

Plant growth monitoring for an environmental chamber. Runs on a Raspberry Pi 5 with a top-down
Arducam 64MP camera and a Hailo AI accelerator, and serves a web interface directly from the Pi.

## What it does

- Captures the growth table on a schedule (10–60 frames/hour)
- Measures **canopy area** per growth tray
- Tracks **tray identity, position and rotation** via AprilTags
- Reports **how much to trust each measurement**, and refuses to guess when the rig has been moved
- Produces timelapses and CSV exports for experimenters

## Status

**M1 slice 1 (skeleton) done.** See [PLAN.md](PLAN.md) and [TODO.md](TODO.md).

## Setup

Dependencies are managed with [`uv`](https://docs.astral.sh/uv/). The venv must use the system
Python interpreter, not one `uv` downloads itself — `picamera2` is a system package, and
`--system-site-packages` only works if the venv's Python version matches the one it was installed
against.

```bash
uv venv --system-site-packages --python /usr/bin/python3 .venv
uv pip install -e ".[dev]"
```

Use `uv run` for everything after that — no need to activate the venv:

```bash
uv run pytest
uv run uvicorn npec_rig.app:app --reload --host 0.0.0.0 --port 8000
```

Not yet installed as a systemd service — see `deploy/npec-rig.service`.

## The one thing to read before contributing

This project has been attempted three times and collapsed into camera metrology each time — lens
models, distortion coefficients, uncertainty propagation — without ever producing a working
application.

The governing principle is in PLAN.md and it is short:

> **Certainty is measured, never derived.** If a number can't be demonstrated with a ruler, a
> printed target, or a repeated observation, it doesn't ship.

Techniques like intrinsic calibration and orthorectification aren't forbidden because they're
unsound. They're deferred behind **evidence gates** — each has a specific measurement that would
justify picking it up. Read that section before proposing one.

A worked example of why this matters, from the previous attempt's own calibration data:

| Error source | Magnitude in area |
|---|---|
| Believing the tags are the 30 mm printed on the box (they measure 29.31 mm) | **~4.7%** |
| Tag corner-finding precision | ~0.15% |
| Segmentation edge ambiguity | several % |

The largest geometric error in the system was solved with a pair of callipers.

## Testing

The fast tier is the default and the expensive tiers are opt-in, by construction:

```bash
pytest                 # unit only — no hardware, budget <10s
pytest -m hardware     # needs the camera
pytest -m hailo        # needs the accelerator
pytest -m integration  # full pipeline against fixture images
pytest -m slow         # soak
```

**Do not run tests for documentation changes.** The previous attempt spent 223 seconds of every
303-second run decoding 64MP frames. See the test-tier table in PLAN.md for what to run when.
