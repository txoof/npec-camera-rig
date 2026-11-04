# Randomize page memory check (#343, metrology log 25)

- `drive.sh`: pressed Suggest and Check on npec-rig-01 through the page's API, 2026-11-04 13:58 to
  14:03 UTC. Its output: suggest 13:58:07, check 13:58:23, overlay 13:58:43; suggest 13:59:24,
  check 13:59:39, overlay 14:00:00; suggest 14:00:41, check 14:00:56, overlay 14:01:24; suggest
  14:02:47 and check 14:02:48 together, 2 s after the scheduled photo of 14:02:45 (overlay 20
  fetched by hand at 14:03:30).
- `memory-2026-11-04.log`: `experiments/348-app-memory/log.sh` on the rig, one line a second:
  epoch, main PID, main RSS MiB, main HWM MiB, camera RSS MiB, camera HWM MiB, MemAvailable MiB.
