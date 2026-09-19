# TODO

Actionable items. Each block names its section in [PLAN.md](PLAN.md) — read that section before
starting, not the whole document.

Status: `[ ]` not started · `[~]` in progress · `[x]` done · `[?]` needs Aaron

---

## Needs Aaron — blocking nothing yet, will block later

- [?] **Segmentation model** — what form is it in? Blocks M5, nothing before it.
- [?] **Capture rate vs storage** — 10/hr is ~29 GB/month, 60/hr is ~170 GB. Decide with retention
      policy and whether an external SSD is needed. Blocks M3.
- [?] **Tag ID allocation** — reserved 36h11 ranges for 12 tray tags, 4 corner tags, and the
      calibration sheets. Must not overlap. Blocks M2.
- [?] **Corner tag placement** — confirm NE/NW/SE/SW are mounted and in frame on the rebuilt rig.
      Blocks M2.
- [?] **Digest delivery** — email or web UI only. Blocks M6 only.

---

## M0 — Probe the hardware · *PLAN.md § M0*

30 minutes. Do this before writing any code; it can change M1's shape.

- [ ] `rpicam-hello --list-cameras`
- [ ] `python3 -c "from picamera2 import Picamera2; p=Picamera2(); print(p.sensor_modes); print(p.camera_controls)"`
- [ ] `hailortcli fw-control identify`
- [ ] Confirm whether `AfMode` / `LensPosition` are present. If absent, focus is mechanical and the
      console becomes a read-only focus aid.
- [ ] Record findings in `reference/hardware-probe.md`

---

## M1 — Camera console · *PLAN.md § M1*

Sliced so each piece ends with something visible in a browser.

### Slice 1 — Skeleton
- [ ] `git`-tracked project layout, `pyproject.toml`, venv with `--system-site-packages`
- [ ] FastAPI + uvicorn serving one page
- [ ] pytest with marker infrastructure and `addopts = -m unit`
- [ ] systemd unit, restart-on-failure
- [ ] **Demo:** page loads in a browser; service survives reboot; `pytest` runs in under a second

### Slice 2 — One still
- [ ] `CameraManager` singleton wrapping picamera2
- [ ] Synthetic camera backend so tests and UI run with no hardware
- [ ] Single-JPEG snapshot endpoint
- [ ] **Demo:** a real frame from the real camera appears in the browser

### Slice 3 — Live preview
- [ ] Dual-stream config: full-res `main` + `lores` preview from the same sensor frame
- [ ] MJPEG via `multipart/x-mixed-replace` into a plain `<img>`
- [ ] **Demo:** live preview at 5 fps or better

### Slice 4 — Controls and persistence
- [ ] Control list generated from probed `camera_controls`, not hardcoded
- [ ] Exposure, gain, AWB, AE on/off; manual lens position
- [ ] Settings persist in SQLite and survive restart *(the old UI's known gap)*
- [ ] **Demo:** change exposure, restart the service, setting is still there

### Slice 5 — Focus aid
- [ ] Laplacian-variance sharpness score on a selectable ROI
- [ ] Magnified 1:1 ROI crop stream
- [ ] Lock and record lens position
- [ ] Full-res capture to `/var/lib/npec-rig/captures/YYYY-MM-DD/` with JSON sidecar
- [ ] Recent-captures gallery
- [ ] **Demo:** turn the ring, watch the score peak, capture, file and sidecar on disk

---

## M2 — Calibration and rig health · *PLAN.md § M2*

The heart of the project. Do not start before M1 slice 5.

- [ ] AprilTag detection: `cv2.aruco`, `DICT_APRILTAG_36h11`, `CORNER_REFINE_SUBPIX`
- [ ] Calibration mode: paper sheets on alternating trays, reaching all four frame corners
- [ ] Scale field and uncertainty field across the measurement plane
- [ ] **Holdout coverage test** — build the field from half the tags, predict the other half
- [ ] Install report: roll, tilt, framing, scale variation, coverage verdicts in plain language
- [ ] Health baseline: four corner tags' positions, sizes, homography, locked lens position
- [ ] Per-capture tripwire: `OK` / `DRIFT` / `FAIL` stamped on every reading
- [ ] Tray tags re-fit scale **on top of** the frozen field — they do not rebuild it
- [ ] Calibration artifact: versioned, exportable

### M2 acceptance — run in the chamber
- [ ] **Two-baseline test** *(do first)* — two independent calibrations of the same static scene,
      diff the fields. That disagreement is the floor on achievable certainty.
- [ ] **Two-height test** — calibrate at two tray heights, diff the field shapes. Proves whether one
      rare paper calibration covers every experiment.
- [ ] Tape-measure two tags → app agrees within 2%
- [ ] Roll the camera ~5° → reported as ~5°; knock it hard → verdict flips to `FAIL`
- [ ] **Honesty plot** — claimed uncertainty vs actual error at 6 positions. Check whether residuals
      are random or structured (structured opens the intrinsics evidence gate)

---

## M3 — Capture, storage, export · *PLAN.md § M3*

- [ ] Full SQLite schema (`experiment`, `calibration`, `tray`, `capture`, `detection`,
      `measurement`, `alert`) — created here so every row has provenance from the start
- [ ] Experiment create/start/stop in the UI
- [ ] Interval scheduler, 1–6 min, trust verdict per capture
- [ ] Survives reboot; recovers from failures; never silently stops
- [ ] Disk monitoring with headroom shown prominently
- [ ] Retention policy
- [ ] Timelapse: scrub, play, mp4 export
- [ ] CSV export page: `measurements.csv`, `dwell.csv`, `captures.csv`, `calibration.json`
- [ ] **Acceptance:** 24 h unattended at exactly the expected count · reboot mid-run, resumes ·
      download a CSV and open it · headroom matches `df`

---

## M4 — Tray tracking · *PLAN.md § M4*

- [ ] Tray tag → identity, centroid, rotation 0–359°
- [ ] Regions: 2 × 6, defined in measurement-plane coordinates, not image pixels
- [ ] Dwell time per region per tray as a query, not a stored table
- [ ] Dirty-tag degradation: measure anyway, flag identity unknown, drop from scale solve
- [ ] **Acceptance:** 12 trays at random positions and rotations all identified · move one, dwell
      table reflects it · smear a tag with soil, degrades without crashing or lying

---

## M5 — Canopy area · *PLAN.md § M5*

- [ ] `Segmenter` interface defined first
- [ ] `ExGSegmenter` — classical excess-green, no ML, ships now, permanent baseline
- [ ] `HailoSegmenter` — stub with identical signature
- [ ] Mask → pixel area → mm² via the per-pixel scale field
- [ ] Store masks to disk so areas can be recomputed without re-inference
- [ ] **Reprocess** action in the UI
- [ ] Per-measurement confidence from measured quantities only
- [ ] **Acceptance:** known-area target at 6 positions — report error *and* whether the confidence
      band contains the truth · change calibration, hit Reprocess, areas update without re-inference

---

## M6 — Alerts and hardening · *PLAN.md § M6*

- [ ] Alerts: area jumps, `DRIFT`/`FAIL`, tag detection dropping, focus drift, scheduler stalls
- [ ] Daily/weekly digest *(Could-Have)*
- [ ] Soak test
- [ ] Deployment runbook for rigs 2–15

---

## Could-Have — only if M1–M6 land early

- [ ] Per-plant tracking within tray cells
- [ ] YOLO tray identification *(needs the evidence gate to open)*
- [ ] Height data / second camera *(needs the evidence gate to open)*
