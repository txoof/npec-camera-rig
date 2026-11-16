import cell_pairs as P, numpy as np, json, collections
from datetime import datetime, timezone
CELLS_FROM = datetime(2026,11,6,12,28,0,tzinfo=timezone.utc)
c, ph, st, cam = P.load(); pp = P.photo_pairs(ph, st, cam); tr = P.tray_rows(c)
cells = collections.defaultdict(dict)
for r in c.execute("""select r.capture_id, r.tray_id, r.cell, r.area_mm2, r.over_other_cells, r.plant_px from cell_reading r
     join capture c on c.id=r.capture_id where c.experiment_id=18 and r.holds='plant' and r.tray_id between 1 and 7
     and c.taken_at >= '2026-11-06T12:28'"""):
    cells[r[0]][(r[1], r[2])] = (r[3], r[4], r[5])
rows = []
for a, b, reason in pp:
    if reason or a["taken_at"] < CELLS_FROM: continue
    for tray in range(1, 8):
        ok, outside = P.tray_ok(tr.get((a["capture_id"], tray)), tr.get((b["capture_id"], tray)))
        if not ok: continue
        for key, va in cells[a["capture_id"]].items():
            if key[0] != tray or key not in cells[b["capture_id"]]: continue
            vb = cells[b["capture_id"]][key]
            if va[0] is None or vb[0] is None: continue
            rows.append(dict(tray=tray, cell=key[1], a=va[0], b=vb[0], over=bool(va[1] or vb[1]), outside=outside,
                             pa=va[2], pb=vb[2], ta=a["taken_at"].isoformat(), ca=a["capture_id"], cb=b["capture_id"]))
json.dump(rows, open("cell_pairs.json", "w"))
print(len(rows), sum(r["outside"] for r in rows))
# mm2 per px
r0 = [r for r in rows if r["pa"]][:5]; print([r["a"]/r["pa"] for r in r0])
m = np.array([(r["a"]+r["b"])/2 for r in rows]); d = np.array([r["b"]-r["a"] for r in rows])
ov = np.array([r["over"] for r in rows])
for lo, hi in [(0,0.001),(0.001,1),(1,5),(5,10),(10,20),(20,50),(50,100),(100,200),(200,500),(500,1000),(1000,5000)]:
    s = (m>=lo)&(m<hi)&~ov
    if s.sum()==0: continue
    pc = np.abs(d[s])/m[s]*100 if lo>0 else np.zeros(s.sum())
    print(f"{lo:>6}-{hi:<6} n={s.sum():6d} med|d|mm2={np.median(np.abs(d[s])):.2f} p95|d|={np.percentile(np.abs(d[s]),95):.2f} med%={np.median(pc):.2f} p95%={np.percentile(pc,95):.1f}")
