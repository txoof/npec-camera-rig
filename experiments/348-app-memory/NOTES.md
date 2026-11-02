# App memory on a 4 GB Pi 5 (#348)

Development check, 2026-11-02, npec-rig-01 (Pi 5, 4 cores, 8 GB), experiment 2 running, one
photo per 60 s. All figures in GiB (1024 MiB). The logger records MiB (kB / 1024).

## Method

- `log.sh OUT` writes one line per second: time, app PID, main process RSS and peak (VmHWM),
  camera process RSS and peak, the Pi's MemAvailable.
- Each build ran as the `npec-rig` service, deployed with `make update-app ... npec_rig_version=<branch>`.
  The first 60 s after a restart are left out.
- `compare_one.py PHOTO` reads one photo the way the app does (decode, tag search, mask, JPEG encode)
  in its own process. It prints the tags, a hash of the mask, hashes of the JPEG bytes (3 and 4
  channels) and the process's peak RSS. It was run with main's code and with the branch's code on
  the same 3 experiment 2 photos (2026-11-02 15:40:06, 15:41:06, 15:43:05 UTC).
- `plot_mem.py` draws the chart.

## Results

| Build | Main mean | Main peak | Camera peak | Total peak | Lowest available |
|---|---|---|---|---|---|
| main cf4c1dd (255 s) | 3.40 | 4.46 | 0.78 | 4.55 | 2.49 |
| f208268: allocator settings, fewer copies (578 s) | 0.78 | 3.13 | 0.78 | 3.22 | 4.03 |
| 350e732: plus OpenCV on 1 thread (1748 s) | 0.53 | 1.29 | 0.78 | 1.39 | 5.60 |
| fd3852e: plus tag search on the grey copy only (583 s) | 0.48 | 1.21 | 0.78 | 1.30 | 5.90 |

Between photos the main process went from 3.3 to 3.4 GiB to about 0.2 to 0.3 GiB.

One photo read in its own process (peak after the tag search):

| Code | Peak | Tag search |
|---|---|---|
| main, OpenCV default 4 threads | 3.23 to 3.43 GiB | 10 to 12 s |
| branch, 4 threads | 2.95 to 3.08 GiB | 12 to 18 s |
| branch, 2 threads | 1.79 GiB | 17 s |
| branch, 1 thread | 1.20 GiB | 17 s |
| branch fd3852e, 1 thread, grey copy only | 1.08 to 1.13 GiB | 17 to 20 s |

Times are noisy: the app took and read its own photo every minute during these runs.

App CPU, fd3852e, 180 s: 0.41 cores on average, 10% of the Pi. (main, 76 s with top: about 13%.)

**Results are unchanged.** On all 3 photos the branch gives the same tag ids and corners (to 6
decimals), the same mask (SHA-256 of the packed bits) and the same JPEG bytes, for 3- and
4-channel frames, as main. Also with 1 and 2 OpenCV threads.

## What made the memory

1. **Held between photos (3.3 GiB):** freed memory kept by glibc's malloc. The app had about 50
   per-thread pools of 64 MiB. Fix: 2 pools, a fixed 1 MiB limit above which blocks go straight
   back to the system, and `malloc_trim` after each photo and each tray reading.
2. **Peak during a tray reading:** OpenCV's tag search on 4 threads (about 1.8 GiB of it), a
   float64 grey conversion of the whole frame (about 1.5 GiB of temporaries), and a second
   Pillow copy of each decoded photo (about 0.25 GiB). Fixes: OpenCV on 1 thread, the grey copy
   worked out 256 rows at a time (same arithmetic, same values), the Pillow image closed before
   the work, the colour frame released before the tag search, segmentation sharing the
   one-at-a-time slot for full-size work.
3. **The photo encode:** a redundant `convert("RGB")` copy (about 0.25 GiB) removed.

## Limits of the evidence

- The 4 GB Pi itself was not tested. A 3.5 GiB cap was set on the service, but this kernel boots
  with `cgroup_disable=memory`, so the cap was not enforced. The measured peak, 1.30 GiB, is well
  under it either way.
- Not measured: a calibration run, the tripwire check and Show tags on an unread photo. They use
  the same tag search, now on 1 thread, but were not run during these logs.
- A reprocess of experiment 2 ran in the main app from 15:37:40 to about 15:43 UTC. Main's figures
  above use only the 255 s before it started.
- Earlier figures given in chat divided MiB by 1000, so they read about 2.4% high.
