#!/usr/bin/env bash
# Copy the rig's data to the backup disk on media-server (issue #188).
#
# Run by npec-rig-backup.timer every 6 hours. Copy only: nothing is ever
# deleted on the disk. Version history is the disk's own rsnapshot backups.
#
# What is copied: everything under /var/lib/npec-rig except derived/ (made
# again from the photos), the camera pid file, and the live rig.db. rig.db is
# copied with SQLite's backup API into a staging folder first, so the copy is
# consistent while the app writes to it.
#
# The key on media-server is limited to rrsync, rooted at the backup folder,
# so the destination paths below are relative to that folder.
#
# The result is written to $DATA/backup-status.json for the web page to show.
# The job runs outside the app, so a failure here never stops a capture.

set -uo pipefail

DATA=${NPEC_BACKUP_SOURCE:-/var/lib/npec-rig}
DEST=${NPEC_BACKUP_DEST:-txoof@100.91.207.33:npec-rig}
KEY=${NPEC_BACKUP_KEY:-/home/pi/.ssh/npec_backup_ed25519}
STATUS=$DATA/backup-status.json
STAGING=$DATA/.backup-staging

SSH="ssh -i $KEY -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=20"
RSYNC_OPTS=(-a --mkpath --partial --timeout=120 -e "$SSH"
    --exclude=/derived/ --exclude=/camera-process.pid --exclude=/rig.db
    --exclude=/rig.db-journal --exclude=/rig.db-wal --exclude=/rig.db-shm
    --exclude=/.backup-staging/ --exclude=/backup-status.json*)

started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
log=$(mktemp)
trap 'rm -f "$log"' EXIT

write_status() {  # ok, message, files sent, bytes sent, verify mismatches
    local tmp=$STATUS.tmp
    /usr/bin/python3 - "$tmp" "$started" "$1" "$2" "$3" "$4" "$5" <<'EOF'
import json, sys, datetime
path, started, ok, message, files, size, mismatches = sys.argv[1:]
json.dump({
    "started": started,
    "finished": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "ok": ok == "1",
    "message": message,
    "files_sent": int(files or 0),
    "bytes_sent": int(size or 0),
    "verify_mismatches": int(mismatches or 0),
}, open(path, "w"), indent=2)
EOF
    mv "$tmp" "$STATUS"
}

fail() {
    echo "backup failed: $1" >&2
    tail -5 "$log" >&2
    write_status 0 "$1" 0 0 0
    exit 1
}

# 1. Consistent copy of the database.
mkdir -p "$STAGING"
/usr/bin/python3 - "$DATA/rig.db" "$STAGING/rig.db" <<'EOF' >"$log" 2>&1 || fail "database copy failed"
import sqlite3, sys
src = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close()
src.close()
EOF

# 2. Photos, sidecars, experiments, calibration frames, scans.
rsync "${RSYNC_OPTS[@]}" --stats "$DATA/" "$DEST/" >"$log" 2>&1 || fail "copy of the photos failed (rsync exit $?)"
files=$(sed -n 's/^Number of regular files transferred: \([0-9,]*\).*/\1/p' "$log" | tr -d ,)
size=$(sed -n 's/^Total transferred file size: \([0-9,]*\).*/\1/p' "$log" | tr -d ,)

# 3. The database copy, next to the photos.
rsync -a --mkpath --timeout=120 -e "$SSH" "$STAGING/rig.db" "$DEST/rig.db" >"$log" 2>&1 \
    || fail "copy of the database failed (rsync exit $?)"

# 4. Read-back check: compare checksums of every file on both sides. Files
# made after step 2 (new photos) are listed as new and are not a mismatch;
# they go in the next run.
rsync "${RSYNC_OPTS[@]}" -n -c --itemize-changes "$DATA/" "$DEST/" >"$log" 2>&1 \
    || fail "read-back check failed to run (rsync exit $?)"
mismatches=$(grep -E '^[<>c]f' "$log" | grep -vc '+++++++' || true)
if [ "$mismatches" -gt 0 ]; then
    grep -E '^[<>c]f' "$log" | grep -v '+++++++' | head -5 >&2
    write_status 0 "$mismatches files differ from the originals" "$files" "$size" "$mismatches"
    exit 1
fi

write_status 1 "ok" "$files" "$size" 0
echo "backup ok: $files files, $size bytes sent"
