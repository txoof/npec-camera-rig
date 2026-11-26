#!/bin/bash
# Issue #511, Part 2 step 4: checks that must pass before anything else.
# Run after sourcing set_env.sh (with NPEC_RIG_* pointed at the HDD copy) and starting the app
# with NPEC_RIG_SYNTHETIC_CAMERA=1 on http://127.0.0.1:${PORT:-8000}.
#
# Usage: ./preflight_checks.sh <repo_root> <experiment_id>
set -u
REPO_ROOT="${1:?repo root}"
EXPERIMENT_ID="${2:?experiment id, e.g. 18}"
PORT="${PORT:-8000}"
BASE="http://127.0.0.1:${PORT}"
FAIL=0

check() { # name, command producing 0 on pass
  local name="$1"; shift
  if "$@"; then echo "PASS  $name"; else echo "FAIL  $name"; FAIL=1; fi
}

echo "== pytest (unit tier) =="
(cd "$REPO_ROOT" && PYTHONPATH="$REPO_ROOT/src" "$REPO_ROOT/.venv/bin/python" -m pytest -q)
[ $? -eq 0 ] && echo "PASS  pytest" || { echo "FAIL  pytest"; FAIL=1; }

echo "== rig.db =="
QUICK_CHECK=$(sqlite3 "$NPEC_RIG_DB_PATH" "PRAGMA quick_check;")
USER_VERSION=$(sqlite3 "$NPEC_RIG_DB_PATH" "PRAGMA user_version;")
[ "$QUICK_CHECK" = "ok" ] && echo "PASS  quick_check ($QUICK_CHECK)" || { echo "FAIL  quick_check ($QUICK_CHECK)"; FAIL=1; }
[ "$USER_VERSION" = "26" ] && echo "PASS  user_version ($USER_VERSION)" || { echo "FAIL  user_version ($USER_VERSION, want 26)"; FAIL=1; }

echo "== /api/about =="
ABOUT=$(curl -fsS "$BASE/api/about")
echo "$ABOUT"
echo "$ABOUT" | grep -q "9498c0f" && echo "PASS  commit 9498c0f" || { echo "FAIL  commit (want 9498c0f)"; FAIL=1; }
echo "$ABOUT" | grep -q '"schema":[[:space:]]*26\|"schema_version":[[:space:]]*26' && echo "PASS  schema 26" || echo "CHECK schema field name/value by hand: $ABOUT"

echo "== no experiment running =="
RUNNING=$(curl -fsS "$BASE/api/experiments" | python3 -c "import json,sys; d=json.load(sys.stdin); print(any(e.get('state')=='running' for e in d))")
[ "$RUNNING" = "False" ] && echo "PASS  nothing running" || { echo "FAIL  an experiment is running: $RUNNING"; FAIL=1; }

echo "== dry run count =="
PLAN=$(curl -fsS -X POST "$BASE/api/experiments/${EXPERIMENT_ID}/reprocess?dry_run=true")
echo "$PLAN"
echo "$PLAN" | python3 -c "
import json, sys
d = json.load(sys.stdin)
n = d.get('photos')
ok = n == 47457
print('PASS  47457 photos' if ok else f'FAIL  {n} photos (want 47457)')
sys.exit(0 if ok else 1)
" || FAIL=1

echo "== every capture path exists under the copied photos =="
"$REPO_ROOT/.venv/bin/python" "$(dirname "$0")/check_capture_files.py" "$NPEC_RIG_DB_PATH" "$NPEC_RIG_PHOTOS_DIR" "$NPEC_RIG_EXPERIMENTS_DIR" "$EXPERIMENT_ID"
[ $? -eq 0 ] && echo "PASS  no missing capture files" || { echo "FAIL  missing capture files (see above)"; FAIL=1; }

echo "=================="
[ "$FAIL" -eq 0 ] && echo "ALL CHECKS PASSED" || echo "SOME CHECKS FAILED -- do not start the full run"
exit "$FAIL"
