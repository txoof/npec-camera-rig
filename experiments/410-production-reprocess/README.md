# 410-production-reprocess

Record of the production Reprocess of experiment 18 (issue #410), metrology log section 37.
Read-only scripts run from the controller against `ac-testing`; nothing here writes to a rig.

- `code/prod_status.py`: counts for experiment 18 (`ssh pi@ac-testing python3 - < prod_status.py`).
- `code/log_progress.sh`: the 10-minute progress logger (Reprocess progress, app memory, free memory and disk, read delay of the newest photo, tracebacks in the server log).
- `code/final_checks.py`: the checks against the rig.db backup taken before the run.
- `data/progress.tsv`: the logger's rows, 2026-11-14 06:40 to 2026-11-17 06:48 UTC (no rows 11:56 to 12:06 on 16 Nov).
- `data/final_checks_2026-11-17.txt`: output of `final_checks.py` after the run.
- `data/reprocess_failures.txt`: the 26 photos Reprocess could not read, from the server log.
