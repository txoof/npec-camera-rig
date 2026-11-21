# Hailo-10H on npec-rig-01, 2026-11-21 ~12:30-12:45 UTC (Aaron's go-ahead; #439 still held the hardware label)
HEF plantseg_s2_final_e40_hailo10h.hef (sha256 5c54fe40...), copied to /tmp/npec406 on the rig, removed after.
hailortcli benchmark -t 15: batch 1 282.48 FPS, batch 8 282.44 FPS; chip 45-51 C.
pi_time_photo.py (app venv, nice 10, ulimit -v 4000000, batch 8), photo dev capture 23494 (2026-11-19 18:00:20 UTC),
432 tiles, 3 repeats: total 2.285 / 2.327 / 2.284 s; decode 0.61, scale 0.04, Hailo 1.34-1.35, blend 0.15-0.16,
threshold+resize 0.14; peak RSS 1000.6 MB. App running experiment 4 meanwhile (photo every 5 min).
Chip vs float final network, same photo, half res: IoU 0.9874, area ratio 0.9957, mean |dlogit| 0.667.
