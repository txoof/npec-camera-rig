# 503 time lapse memory

`sample.py` records the memory of a time lapse video job (#503) from /proc.
Standard library only, does not import `npec_rig`. Not deployed, no tests.

Run it on the rig before the job starts (app PID from `systemctl show -p MainPID npec-rig`):

    python3 sample.py --app-pid N --out run.csv [--abort-used-gib 3.0] [--abort-avail-gib 1.0]

It notes the app's children at start (the camera process is among them), then
follows the first new `spawn_main` child (the video child) and its `ffmpeg`.
Check it on the controller with `python3 sample.py --selftest`.

Columns, one row per second (polled every 0.25 s, highest peak kept between rows):
`time_utc, elapsed_s`, `app_vmpeak_kb, app_vmhwm_kb`, `child_*` and `ffmpeg_*`
(`vmpeak_kb, vmhwm_kb, vmrss_kb`), `mem_total_kb, mem_available_kb`,
`used_kb` (total minus available), `note`. A process exited keeps its last values;
blank means not started yet.

Abort rule: if used memory is over 3.0 GiB or MemAvailable under 1.0 GiB, it sends
SIGTERM to ffmpeg then the video child (never the app or camera process), writes an
ABORT row and exits with status 3. Status 2: the video child did not appear within
`--wait-seconds` (600). It also stops when the child exits, on SIGINT/SIGTERM, or
after `--max-seconds` (7200).
