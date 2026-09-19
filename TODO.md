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
- [?] **Hailo accelerator** — no `hailortcli`, no PCIe device, no package installed on this OS
      build. Needs HailoRT install and physical seating confirmed. Blocks M5 only, and M5 ships
      with a classical fallback regardless.
- [?] **Chamber lighting spectrum vs. color accuracy** — a known-yellow object photographs blue
      under the chamber's grow lighting; checked channel order and white balance in code, both
      correct (see M1 slice 3 notes) — most likely a lighting-spectrum limitation, not fixable
      in software. Aaron confirms earlier captures in the same session showed correct color and
      later ones didn't, with no code change to `array_to_jpeg`/color handling in between —
      points at the physical lighting changing (schedule, cycle, or spectrum shift) rather than
      a regression. **Check the chamber's lighting conditions/schedule directly.** Matters for
      M5: `ExGSegmenter` (excess-green) depends on color being roughly right and roughly
      constant. *(Aaron, 2026-09-19)*
- [?] **Minimum-gain policy** — Aaron's supervisor requires minimal `AnalogueGain` at all times.
      Default is already 1.0 (satisfied as-is). Not yet decided: whether to *enforce* this
      further — e.g. cap the gain slider's usable max, or bias auto-exposure toward longer
      exposure time over gain (`AeExposureMode`, unverified whether picamera2 exposes a "long
      exposure preferred" mode — would need checking against real hardware before building
      anything, same as the format-string lesson from M1 slice 3). Not built; needs a decision
      on how strict this should be before doing more than the current default. *(Aaron,
      2026-09-19)*

---

## M0 — Probe the hardware · *PLAN.md § M0*

30 minutes. Do this before writing any code; it can change M1's shape.

- [x] `rpicam-hello --list-cameras`
- [x] `python3 -c "from picamera2 import Picamera2; p=Picamera2(); print(p.sensor_modes); print(p.camera_controls)"`
- [x] `hailortcli fw-control identify` — not found; no Hailo device/package detected anywhere.
      New `[?]` below.
- [x] Confirm whether `AfMode` / `LensPosition` are present. Present. Focus is
      software-controllable; M1 slices 4/5 proceed as planned.
- [x] Record findings in `reference/hardware-probe.md`

---

## M1 — Camera console · *PLAN.md § M1*

Sliced so each piece ends with something visible in a browser.

### Slice 1 — Skeleton
- [x] `git`-tracked project layout, `pyproject.toml`, venv with `--system-site-packages`
- [x] FastAPI + uvicorn serving one page
- [x] pytest with marker infrastructure and `addopts = -m unit`
- [x] systemd unit, restart-on-failure *(unit file written, not installed/enabled — manual start for now)*
- [ ] Install/enable the systemd unit and run the reboot-survival checks in PLAN.md's M1 "you
      verify" line and M3's acceptance bullet. **Deferred, low priority.** Aaron has no physical
      access to the device right now; a failed reboot is an unrecoverable round trip until he
      does. Pick this up later, at whichever milestone is testing reboot survival anyway (M3),
      not as a standalone task. *(Aaron, 2026-09-19)*
- [x] **Demo:** page loads (verified via curl, 200 OK) and `pytest` runs in 0.44s. Unit file written
      to `deploy/npec-rig.service` but not copied to `/etc/systemd/system` or enabled, per this
      slice's manual-start instruction — reboot survival not tested yet.

### Slice 2 — One still
- [x] `CameraManager` singleton wrapping picamera2
- [x] Synthetic camera backend so tests and UI run with no hardware
- [x] Single-JPEG snapshot endpoint
- [x] **Demo:** confirmed via `curl` against the running server — real 9152x6944 JPEG from the
      real camera, viewable in the browser at `/`. Frame is out of focus, as expected: manual
      focus control is slice 5, not built yet.

### Slice 3 — Live preview
- [x] Dual-stream config: `main` (1536x1152) + `lores` (320x240) preview from the same sensor
      frame. Note: `main` is not full sensor resolution — full-sensor stills top out at ~3 fps
      per M0, so `/snapshot.jpg` now serves `main` instead. True full-res capture-to-disk is
      slice 5's job, as a deliberate mode switch, not this continuous stream.
- [x] MJPEG via `multipart/x-mixed-replace` into a plain `<img>`
- [x] **Bug fix (2026-09-19):** live preview was black-and-white with a garbled band in the
      bottom third. Root cause: `lores` stream was left format-unspecified and negotiated
      YUV420 planar (Y rows, then subsampled U/V rows packed below — that packed section is
      exactly a third of the total buffer height, matching where the artifact showed up); our
      code treated that buffer as interleaved RGB. Root cause of *that*: `encode="lores"` was
      left over from assuming we'd use picamera2's own hardware encoder, which we never do (we
      PIL-encode ourselves) — removed it and pinned `format: "RGB888"` on both `main` and
      `lores` explicitly instead of trusting the negotiated default. Verified: fresh preview
      frame is correct color, no artifact; snapshot/capture/focus-score still work.
- [x] **Demo:** measured 30 frames in 3s against real hardware = steady 10 fps (our configured
      cap), comfortably over 5 fps. Confirmed real frames, correct `Content-Length` framing.
- [x] **Investigated (2026-09-19):** Aaron reported a known-yellow object rendering blue in the
      preview. Checked directly against picamera2 rather than guessing — a channel-swap test
      (capturing the same scene as `RGB888` and `BGR888`, comparing each against the other
      reversed) confirms `RGB888` genuinely returns R,G,B channel order (not swapped, despite an
      initial wrong assumption on my part that it was — reverted a `BGR888` change that would
      have made this worse, not better). A known-neutral white paper sheet in the same frame
      also reads back neutral, ruling out a global white-balance cast. The object itself
      measures blue-dominant (B > G > R) in the raw data either way.
      **Conclusion: not a software bug as far as this checks** — most likely the chamber's
      grow lighting has a spectrum narrow enough that a genuinely yellow object doesn't reflect
      the wavelengths a normal camera expects, which auto white-balance can't fully correct.
      **Needs Aaron:** confirm by looking at the same object under the camera in normal room
      light vs. the chamber's grow light. If it still looks blue under the chamber light with
      the naked eye, this isn't a camera problem to fix at all.
- [x] Pulled a minimal lens-position slider in from slice 4/5 (Aaron asked to see live preview
      with focusing together) — POST/GET `/controls/lens-position`, no persistence yet. Verified
      against real hardware: write then read-back matches after ~0.5 s settle (camera pipeline
      latency, not a bug — metadata reflects the frame in flight, not instant on write).
      Full sharpness-score focus aid and settings persistence remain slice 4/5, not built.
- [x] Responsive layout (viewport meta, fluid width, larger touch controls) for mobile/small
      low-res displays — written but **not yet visually confirmed in an actual browser**. Please
      eyeball it on the target display and at phone width before calling this done.
- [x] Focus zoom sits to the right of the live preview above 800px width, stacks vertically
      below it (plain CSS flexbox + one media query, no JS) — same visual-confirmation caveat
      as above. *(Aaron, 2026-09-19)*

### Slice 4 — Controls and persistence
- [x] Control list generated from probed `camera_controls`, not hardcoded. Good thing it isn't:
      probed live, `LensPosition`'s max read 15.0, then 32.0, then 15.0 again across different
      probes in the same session; `ExposureTime`'s max varied by two orders of magnitude
      (66666 vs 122582952) and `AnalogueGain`'s max read both 16.0 and 64.0 — these ranges are
      config/mode-dependent, not fixed hardware facts. A hardcoded range would have been wrong
      at least once. Frontend renders whatever `/controls` reports, generically — a checkbox
      for boolean controls, a slider for numeric ones — so a different camera or firmware
      changes the UI without a code change.
- [x] Exposure time, analogue gain, AWB on/off (`AwbEnable`), AE on/off (`AeEnable`); manual
      lens position (already had dedicated coarse/fine/autofocus UI from slice 5 — its range is
      now also pulled from this same probe instead of a hardcoded 0–15).
- [x] Settings persist in SQLite (`/var/lib/npec-rig/rig.db`, table `camera_settings`) and load
      on startup instead of defaults.
      **Real bug found and fixed:** `AnalogueGain`/`ExposureTime` writes are silently
      overridden by the auto-exposure algorithm until `AeEnable` is off — confirmed on real
      hardware, not assumed. Loading persisted settings in dict order occasionally applied
      `AnalogueGain` before `AeEnable`, so the gain got immediately overwritten by AE before AE
      was turned off. Fixed by applying `AeEnable`/`AwbEnable` first, always.
- [x] **Demo:** verified against real hardware. Set gain 3.5, AWB off, AE off, lens 6.3; stopped
      and restarted the *application* (not the Pi — Aaron doesn't want reboot tests, a failed
      one is a 3-hour round trip); after restart, `/controls` showed all four correctly
      restored, not defaults.
- Note: while testing this, Aaron was independently using the new controls live in his own
  browser tab — real concurrent usage, which is a better signal than my own curl checks. Took
  that as confirmation the UI works, not as noise to filter out.
- [?] One exposure-time value from testing (11.6 seconds) didn't reapply on restart — likely
      clamped because it exceeds what the *current streaming mode's* frame duration allows,
      even though the probed range's max is much larger (that max may be a still-mode-only
      figure). Not chased further; flagging in case exposure control feels unreliable near the
      top of its reported range. *(2026-09-19)*
- [x] UI polish on Camera settings (2026-09-19, Aaron): moved below Focus aid, collapsed by
      default (native `<details>`/`<summary>`, no custom widget); AWB and AE checkboxes shown
      on one line; exposure time displayed as a fraction of a second (`1/147 s`) instead of raw
      microseconds — the API still speaks microseconds underneath, this is display-only. Reset
      the live rig to the stated default policy: auto exposure on, auto white balance on,
      analogue gain 1.0.

### Slice 5 — Focus aid
*(Built ahead of slice 4 at Aaron's request, 2026-09-19 — not the plan order.)*
- [x] Laplacian-variance sharpness score on a selectable ROI (click the live preview to place it)
- [x] Magnified 1:1 ROI crop stream (`/focus/roi.mjpg`, 5 fps, no interpolation — genuine pixels,
      not resized, so the score and the display agree)
- [x] Lock and record lens position (`/focus/lock`, in-memory only — no persistence yet, that's
      still slice 4)
- [x] Full-res capture to `/var/lib/npec-rig/captures/YYYY-MM-DD/` with JSON sidecar. Created
      `/var/lib/npec-rig/captures` (root-owned parent, chowned to `pi`) since it didn't exist.
- [x] Recent-captures gallery on the main page
- [x] **Demo:** verified against real hardware — swept lens position 1.0 to 10.0, sharpness score
      peaked at 6.3 (score 1105–1119, vs. single digits elsewhere), matching the old rig's known
      focus position from the M0 probe notes. Captured, got a real JPEG + sidecar JSON on disk,
      listed in `/api/captures`.
- [x] Removed the "Full snapshot" link from the page — Aaron didn't want a manual full-snapshot
      click in the final UI, and the magnified crop now does that job.
- Note: found and killed two stray leftover processes (from an earlier hung test run) that were
  holding the camera device open, which had made the server silently fall back to the synthetic
  backend without erroring. Logged as a real gap: **slice 6/M6 candidate — surface backend choice
  (synthetic vs. real) somewhere visible in the UI**, so a silent fallback like this doesn't go
  unnoticed again.
- [x] One-shot hardware autofocus (`AfMode=Auto` + `AfTrigger`, via picamera2's
      `autofocus_cycle`), always returning to `Manual` afterward so it can't hunt or drift
      mid-experiment. Verified on real hardware: landed at 5.71 (score 324) in 0.7 s, manual
      control confirmed still working right after. *(Aaron, 2026-09-19)*
- [x] Replaced the single full-range lens slider with: an **Autofocus** button, a **coarse**
      `<input type="number">` (whole dioptres, native spinner + free digit entry — no custom
      widget needed), and a **fine** slider with a fixed `.00`-`.99` range (no recentering).
      Coarse (whole number) + fine (fraction) simply add together. Typing "6.8" into coarse
      splits into coarse=6, fine=.80 (slider jumps to 80%) — same mapping every time, so the
      slider position is always predictable from the number. Revised from an earlier
      ±1.0-dioptre-recentering design after Aaron pointed out unpredictable slider position was
      the actual problem — this version has *less* logic than that one (no dynamic range to
      recompute), not more. *(Aaron, 2026-09-19)*
- [ ] When the attached lens has no autofocus (some lenses are manual-only), gray out the
      Autofocus button with a note explaining why, instead of letting it fail silently or throw.
      Deferred until a manual-only lens is actually in use. *(Aaron, 2026-09-19)*
- [ ] Camera selector in the UI for when multiple cameras are detected. Not needed on the
      current single-camera rig; for a future project/rig with additional cameras.
      *(Aaron, 2026-09-19)*
- [ ] Optional suffix/label on a capture (filename and/or sidecar field), so a specific capture
      can be told apart from the rest without relying on timestamp alone. *(Aaron, 2026-09-19)*
- [x] Focus peaking: toggle with a description, highlights high-contrast edges in the magnified
      crop in magenta. Reuses the existing Laplacian machinery (one shared helper function, one
      boolean flag, no new modules) rather than a separate subsystem. Verified on real hardware
      at lens=6.3: dense magenta on the AprilTag edges, matching the 1130 sharpness score at the
      same position. *(Aaron, 2026-09-19)*

---

## M2 — Calibration and rig health · *PLAN.md § M2*

The heart of the project. Do not start before M1 slice 5.

- [ ] Hardware-test skip infrastructure in `tests/conftest.py`: detect camera absence and
      `pytest.skip()` `hardware`/`hailo`-marked tests, rather than letting them hard-fail on
      import. Add this alongside M2's first hardware-marked test (AprilTag detection needs real
      frames to be meaningful), not before. *(Aaron, 2026-09-19)*
- [ ] AprilTag detection: `cv2.aruco`, `DICT_APRILTAG_36h11`, `CORNER_REFINE_SUBPIX`
- [ ] Calibration mode: paper sheets on alternating trays, reaching all four frame corners
- [ ] Scale field and uncertainty field across the measurement plane
- [ ] **Holdout coverage test** — build the field from half the tags, predict the other half
- [ ] Install report: roll, tilt, framing, scale variation, coverage verdicts in plain language
- [ ] Health baseline: four corner tags' positions, sizes, homography, locked lens position
- [ ] Per-capture tripwire: `OK` / `DRIFT` / `FAIL` stamped on every reading
- [ ] Tray tags re-fit scale **on top of** the frozen field — they do not rebuild it
- [ ] Calibration artifact: versioned, exportable
- [ ] Calibration data lives in its own storage location, separate from experiment captures —
      it's rig-level state, not per-experiment data. *(Aaron, 2026-09-19)*

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
- [ ] Experiment storage laid out so a whole experiment is easy to identify and remove as a unit
      (e.g. one directory per experiment, named/indexed so it's obvious which is which) — not
      commingled with calibration data or other experiments. *(Aaron, 2026-09-19)*
- [ ] Interval scheduler, 1–6 min, trust verdict per capture
- [ ] Survives reboot; recovers from failures; never silently stops
- [ ] Disk monitoring with headroom shown prominently
- [ ] Retention policy
- [ ] Storage tier: keep a significantly reduced/compressed version of each capture for long-term
      storage; full-resolution data is for the processing pipeline (segmentation, calibration,
      calculations — see M5), not for archival. RAW is captured only on explicit on-demand
      request, never automatically. *(Aaron, 2026-09-19)*
- [ ] Timelapse: scrub, play, mp4 export
- [ ] CSV export page: `measurements.csv`, `dwell.csv`, `captures.csv`, `calibration.json`
- [ ] Nice-to-have, not important: a fuller gallery for browsing captured photos (the slice-5
      "recent captures" strip only shows the latest few — this would be full browsing/paging).
      *(Aaron, 2026-09-19)*
- [ ] Nice-to-have, not important: download captures, single or as a batch. *(Aaron, 2026-09-19)*
- [ ] Nice-to-have, not important: clear/delete previously captured photos.
      *(Aaron, 2026-09-19)*
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
- [ ] Segmentation runs against full-resolution captures, not the reduced storage copy
      (see M3 storage tier note) — resolution loss here is a measurement error, not a
      storage decision. *(Aaron, 2026-09-19)*
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
- [ ] Each rig has an addressable name, shown in the interface *(added 2026-09-19, fleet mgmt)*
- [ ] Rig health status over an API (out of focus, experiment running, idle, etc.) for fleet
      monitoring *(added 2026-09-19, fleet mgmt)*

---

## Could-Have — only if M1–M6 land early

- [ ] Per-plant tracking within tray cells
- [ ] YOLO tray identification *(needs the evidence gate to open)*
- [ ] Height data / second camera *(needs the evidence gate to open)*
