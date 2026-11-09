"""Undisturbed pairs per 16.3 + 16.9 rules, exp 18, from the read-only rig.db copy."""
import csv, json, sqlite3, sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, "/home/pi/wt/npec-223-area-jumps/experiments/round2-run")
import analysis
from zoneinfo import ZoneInfo

DB = "file:/home/pi/scratch/223-shuffle-check/prod2/rig.db?mode=ro"
REC = "/home/pi/wt/npec-223-area-jumps/experiments/round2-run/sessions/shuffle-record-2026-10-22.csv"
CH = ZoneInfo("Europe/Amsterdam")
END = datetime(2026, 11, 9, 10, 40, 59, tzinfo=timezone.utc)
SKIP = (datetime(2026,10,28,8,47,53,tzinfo=timezone.utc), datetime(2026,10,28,8,50,2,tzinfo=timezone.utc))
BAD_WARN = {"no tag", "tag seen, tray not found in the photo", "two tags in one tray outline"}

def utc(t): return datetime.fromisoformat(t)

def shuffles():
    out = []
    for r in csv.DictReader(open(REC)):
        fin = datetime.fromisoformat(f"{r['date']}T{r['finish']}").replace(tzinfo=CH).astimezone(timezone.utc)
        st = (datetime.fromisoformat(f"{r['date']}T{r['start']}").replace(tzinfo=CH).astimezone(timezone.utc)
              if r["start"] else fin - timedelta(minutes=60))
        out.append((st - timedelta(minutes=15), fin + timedelta(minutes=15)))
    return out

def load():
    c = sqlite3.connect(DB, uri=True); c.row_factory = sqlite3.Row
    starts = [utc(r[0]) for r in c.execute("select started_at from app_start")]
    cam = [utc(r[0]) for r in c.execute("select time_utc from camera_events where coalesce(detail,'') not like '%synthetic camera%'")]
    photos = []
    for r in c.execute("""select c.*, t.status, e.name excl from capture c left join tray_read t on t.capture_id=c.id
                          left join exclusion e on e.capture_id=c.id where c.experiment_id=18 order by c.taken_at"""):
        t = utc(r["taken_at"])
        if t > END: continue
        photos.append(dict(capture_id=r["id"], path=r["path"], taken_at=t, status=r["status"] or "not read",
                           calibration=r["calibration"], lens_position=r["lens_position"],
                           flags=json.loads(r["flags"] or "[]"), excl=r["excl"]))
    return c, photos, starts, cam

def photo_pairs(photos, starts, cam):
    br = shuffles()
    out = []
    for a, b in zip(photos, photos[1:]):
        # app uptime: rows in app_start (from 2 Nov) stand in for the sidecar's app_up_s
        a2 = dict(a); b2 = dict(b)
        gap = (b["taken_at"] - a["taken_at"]).total_seconds()
        restarted = any(a["taken_at"] < s <= b["taken_at"] for s in starts)
        b2["app_up_s"] = 0 if restarted else gap + 1
        reason = analysis._reason(a2, b2, br, cam)
        if reason is None and (a["excl"] or b["excl"]): reason = "exclusion"
        if reason is None and any(SKIP[0] <= p["taken_at"] <= SKIP[1] for p in (a, b)): reason = "17.12 left out"
        out.append((a, b, reason))
    return out

def tray_rows(c):
    d = {}
    for r in c.execute("""select t.* from tray_reading t join capture c on c.id=t.capture_id
                          where c.experiment_id=18 and t.tray_id is not null"""):
        d.setdefault((r["capture_id"], r["tray_id"]), []).append(dict(r))
    return d

def tray_ok(ra, rb):
    """rule 8; returns (ok, partly_outside)"""
    if not ra or not rb or len(ra) != 1 or len(rb) != 1: return False, False
    ra, rb = ra[0], rb[0]
    wa, wb = set(json.loads(ra["warnings"] or "[]")), set(json.loads(rb["warnings"] or "[]"))
    if ra["placement"] != "placed" or rb["placement"] != "placed": return False, False
    if ra["slot"] != rb["slot"] or (wa | wb) & BAD_WARN: return False, False
    if ra["area_mm2"] is None or rb["area_mm2"] is None: return False, False
    return True, "partly outside the photo" in (wa | wb)
