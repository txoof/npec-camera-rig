#!/bin/bash
# #511: Part 3B (serial vs 6 workers on the same 300) -> gate -> Part 4 (the full run).
# Runs unattended. Everything it does is appended to chain.log.
set -u
REPO=/home/txoof/temp.nobackup/444-amd-reprocess/repo
B=/home/txoof/temp.nobackup/444-amd-reprocess/ac-testing
D=$B/var/lib/npec-rig
PY=$REPO/.venv/bin/python
WORKERS=6
MEM_KB=6000000          # 6 GB per worker ceiling; 6 x 6 = 36 GB cap, actual peak is far lower
LOG=$B/chain.log

say() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG"; }

cd "$REPO" || exit 1
export NPEC_RIG_SYNTHETIC_CAMERA=1
export NPEC_RIG_PHOTOS_DIR="$D/rig"
export NPEC_RIG_EXPERIMENTS_DIR="$D/experiments"
export NPEC_RIG_CALIBRATION_DIR="$D/calibration"

say "=== chain start ==="

# ---------------------------------------------------------------- Part 3B
say "Part 3B: same 300 photos, $WORKERS workers, fresh scratch from pre-444"
S=$B/part3/scratch-B
rm -rf "$S"; mkdir -p "$S/masks/experiments/2026-10-22_df206967" "$S/derived"
cp "$D/rig.db.pre-444-20261124T135651Z" "$S/rig.db"
cp -a "$D/masks-pre-444-2026-10-22_df206967-20261124T135909Z/." "$S/masks/experiments/2026-10-22_df206967/"
say "Part 3B: scratch ready"

export NPEC_RIG_DB_PATH="$S/rig.db"
export NPEC_RIG_MASKS_DIR="$S/masks"
export NPEC_RIG_DERIVED_DIR="$S/derived"

for i in $(seq 0 $((WORKERS - 1))); do
  ( ulimit -v $MEM_KB; "$PY" experiments/444-amd-reprocess/code/run_photos.py \
      "$B/part3/sample-paths.txt" "$B/part3/parallel.jsonl" --slice "$i/$WORKERS" \
      >> "$B/part3/parallel.stdout" 2>&1 ) &
done
wait
say "Part 3B: workers finished"

# ------------------------------------------------------- the gate: A vs B
say "Gate: comparing serial (scratch-A) against $WORKERS workers (scratch-B)"
"$PY" experiments/444-amd-reprocess/code/compare_runs.py \
  "$B/part3/scratch-A/rig.db" "$S/rig.db" "$B/part3/sample-paths.txt" \
  > "$B/part3/compare-serial-vs-parallel.txt" 2>&1
GATE=$?
tail -5 "$B/part3/compare-serial-vs-parallel.txt" >> "$LOG"

# Exclusions are worked out from neighbouring photos, so they are checked separately.
"$PY" - "$B/part3/scratch-A/rig.db" "$S/rig.db" >> "$LOG" 2>&1 <<'PYEOF'
import sqlite3, sys
def rows(db):
    c = sqlite3.connect(db)
    try:
        return sorted(c.execute("SELECT capture_id, tray_id, reason FROM exclusion").fetchall())
    except sqlite3.OperationalError as e:
        return f"no exclusion table: {e}"
a, b = rows(sys.argv[1]), rows(sys.argv[2])
print(f"exclusion rows serial={len(a) if isinstance(a,list) else a} parallel={len(b) if isinstance(b,list) else b}")
print("exclusions identical:", a == b)
PYEOF

if [ "$GATE" -ne 0 ]; then
  say "GATE FAILED: serial and $WORKERS workers disagree. Full run NOT started."
  say "See $B/part3/compare-serial-vs-parallel.txt"
  exit 1
fi
say "GATE PASSED: serial and $WORKERS workers agree on all readings"

# ---------------------------------------------------------------- Part 4
say "Keeping the Pi's values for the post-run comparison"
cp "$D/rig.db" "$B/pi-reference.db"
say "pi-reference.db written ($(stat -c %s "$B/pi-reference.db") bytes)"

say "Part 4: FULL RUN starting, all 47457 photos, $WORKERS workers"
"$PY" - "$D/rig.db" "$B/all-paths.txt" <<'PYEOF'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1]); c.row_factory = sqlite3.Row
rows = c.execute("SELECT path FROM capture WHERE experiment_id=18 AND purpose='capture'"
                 " ORDER BY taken_at, id").fetchall()
open(sys.argv[2], "w").write("".join(r["path"] + "\n" for r in rows))
print(f"{len(rows)} photos listed")
PYEOF
say "photo list: $(wc -l < "$B/all-paths.txt") photos"

export NPEC_RIG_DB_PATH="$D/rig.db"
export NPEC_RIG_MASKS_DIR="$D/masks"
export NPEC_RIG_DERIVED_DIR="$D/derived"
mkdir -p "$D/derived"

for i in $(seq 0 $((WORKERS - 1))); do
  ( ulimit -v $MEM_KB; "$PY" experiments/444-amd-reprocess/code/run_photos.py \
      "$B/all-paths.txt" "$B/full-run.jsonl" --slice "$i/$WORKERS" \
      >> "$B/full-run.stdout" 2>&1 ) &
done
say "Part 4: $WORKERS workers launched, pids: $(jobs -p | tr '\n' ' ')"
wait
say "=== Part 4 FINISHED ==="
say "$(grep -c '"event": "failed"' "$B/full-run.jsonl" 2>/dev/null || echo 0) failed photo records"
