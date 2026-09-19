# M0 hardware probe

Run on the rebuilt rig, 2026-09-19. Raspberry Pi 5, Trixie, kernel 6.18.39+rpt-rpi-2712.

## `rpicam-hello --list-cameras`

One camera detected: `arducam_64mp`, sensor `9248x6944` 10-bit RGGB.

Seven modes, from 1280x720 @120fps up to full 9152x6944 @2.7fps. Full-res still capture
(8000x6000 or 9152x6944) tops out at ~3 fps — irrelevant for stills, relevant if a preview
stream is ever pulled from the full-res mode by mistake.

## `picamera2` sensor_modes / camera_controls

Sensor modes match `rpicam-hello`, with per-mode exposure limits and crop limits also reported.

**`AfMode` and `LensPosition` are both present:**

- `AfMode`: `(0, 2, 0)` — three states (Manual / Auto / Continuous, default 0 = Manual)
- `LensPosition`: `(0.0, 15.0, 1.0)` — range 0–15 dioptres, default 1.0, **at this probe's sensor
  mode only**. M1 slice 4 found this range (and `ExposureTime`'s, `AnalogueGain`'s) changes with
  the active sensor mode — this reading is a snapshot, not a fixed hardware fact. That's exactly
  why M1's control list is generated from a live probe at startup, not hardcoded from this file.
- `AfTrigger`, `AfPause`, `AfRange`, `AfSpeed`, `AfMetering`, `AfWindows` also present

Focus is software-controllable. Manual mode is the default state, which matches what we want
(continuous AF must stay off). The old rig's working lens position of 6.3 dioptres is within
range and worth trying first.

Full control dict also includes standard exposure/gain/AWB controls (`ExposureTime`,
`AnalogueGain`, `AwbMode`, `ColourGains`, `AeEnable`, etc.) plus `HdrMode`, `CnnEnableInputTensor`,
`SyncMode`/`SyncFrames` (multi-camera sync, unused here).

## `hailortcli fw-control identify`

**Command not found.** No `hailortcli` binary anywhere on the filesystem, no Hailo entry in
`lspci`, no Hailo kernel messages in `dmesg`, no Hailo package in `dpkg` or `pip3 list`.

The Hailo accelerator is not installed or not detected on this OS build at all — not a driver
version mismatch, a clean absence. This blocks nothing before M5 (`Segmenter` interface ships
with a classical excess-green fallback per CLAUDE.md), but M5 cannot start until this is
resolved: HailoRT software stack needs installing and the physical module needs to be seated
and recognized.

## Answer to the key question

**`AfMode` and `LensPosition` are exposed.** Focus is not mechanical-only. M1 slices 4 and 5
proceed as planned in PLAN.md: manual lens-position control in the console, Laplacian-variance
focus aid drives an actual `LensPosition` write, not just a read-only sharpness trace.

## Follow-up needed before M5

- [?] Install HailoRT and confirm the Hailo module is physically seated and enumerates.
