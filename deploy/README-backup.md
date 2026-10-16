# Backup to media-server

Every 6 hours (00:15, 06:15, 12:15, 18:15 UTC) `npec-rig-backup.sh` copies the rig's data to
Aaron's backup disk on media-server (Tailscale 100.91.207.33). That disk has its own hourly,
daily, weekly and monthly rsnapshot backups, kept off site, which hold the version history.

## What is copied

Everything under `/var/lib/npec-rig/` except:

- `derived/`, which is made again from the photos
- `camera-process.pid`
- the live `rig.db`. It is copied with SQLite's backup API into `.backup-staging/` first, so
  the copy is consistent while the app writes to it, and that copy is sent.

The job copies only. Nothing on the disk is deleted, even when a file is deleted on the rig.

After the copy, every file is compared by checksum with the original. A file that differs is a
failed backup. Photos taken while the job ran are not a failure; the next run copies them.

The result goes to `/var/lib/npec-rig/backup-status.json`: start and end time (UTC), `ok`, a
message, files and bytes sent, and the number of files that differ.

## Access

The key is `/home/pi/.ssh/npec_backup_ed25519`. On media-server it is in `txoof`'s
`~/.ssh/authorized_keys` with `command="/usr/bin/rrsync <backup folder>",restrict`. It can only
run rsync inside that folder: no shell, no port forwarding, no other folders. The data goes to
`npec-rig/` in that folder.

## Install

```bash
sudo cp deploy/npec-rig-backup.service deploy/npec-rig-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now npec-rig-backup.timer
systemctl list-timers npec-rig-backup.timer     # next run
sudo systemctl start npec-rig-backup.service    # run one now
journalctl -u npec-rig-backup.service -n 20     # its output
```

The service runs the script from `/home/pi/npec_camera_rig/deploy/`, so it uses the version on
`main`.

## Not covered

- Free space on the backup disk. The restricted key can only run rsync, so the rig cannot ask
  for it.
- A disk missing or full shows as a failed run in `backup-status.json` and in the journal. The
  web page does not show the status yet.
