# Shuffle record

`shuffle-record-2026-10-22.csv` is the collaborator's own record of each Round 2 shuffle, copied
as written. Times are chamber time (Europe/Amsterdam: UTC+2 until 25 October, UTC+1 after). A
blank start was not written down. New shuffles are appended as rows, one per shuffle, in order.
The collaborator labelled every time CET; 22 and 23 October are read as summer time (UTC+2).
Shuffles 7 to 12 were added on 2026-11-09 (#223). Shuffle 12 puts the last of the 13
maps on the table.

This file is the source record and is not converted. `chamber-times-2026-10-22.csv` is the input
to `chamber_times.py`; the record differs from what that script accepts in these places:

- Shuffle 0 finish is 12:41, while the rig read the start layout at 10:40:51 (08:40:51 UTC).
  This is not a conflict: Aaron laid the trays out and the experiment started at 10:41; map 0
  was then written from the layout already on the table and recorded at 12:41. No tray moved
  in between (Aaron, 2026-10-30, and the rig's photos).
- Shuffle 1 has no start.
- Shuffles 5, 6, 7, 8, 10 and 11 start before 09:30, outside the script's shuffling window
  (09:30 to 17:00).
- Shuffle 11 took 2 h 17 min (09:05 to 11:22), against 7 to 13 minutes for the others.
