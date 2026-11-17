# Read-only checks after the Reprocess of experiment 18 (#410), against the backup taken before it.
# Run on ac-testing: ssh pi@ac-testing python3 - < final_checks.py
import sqlite3
BACKUP = "/var/lib/npec-rig/backups/before-reprocess-410-a6632d6-20261114T003144Z/rig.db"
c = sqlite3.connect("file:/var/lib/npec-rig/rig.db?mode=ro", uri=True)
c.execute(f"attach database 'file:{BACKUP}?mode=ro' as b")
q = lambda s, *a: c.execute(s, a).fetchall()
CUT = "2026-11-14T00:31:44"  # backup time; Reprocess covered photos up to its start
print("== 1. photos of experiment 18 and grow from leaf cores")
print("photos", q("select count(*) from capture where experiment_id=18")[0][0])
print("tray_read status", q("select t.status, count(*) from tray_read t join capture p on p.id=t.capture_id where p.experiment_id=18 group by t.status"))
print("read photos with every tray carrying grown", q("""select count(*) from tray_read t join capture p on p.id=t.capture_id
  where p.experiment_id=18 and t.status='read' and exists(select 1 from tray_reading r where r.capture_id=t.capture_id)
  and not exists(select 1 from tray_reading r where r.capture_id=t.capture_id and r.grown_method is null)""")[0][0])
nog = q("""select p.id, p.taken_at, t.status, (select count(*) from tray_reading r where r.capture_id=p.id),
  (select count(*) from tray_reading r where r.capture_id=p.id and r.grown_method is null),
  (select count(*) from tray_reading r where r.capture_id=p.id and r.area_mm2 is null), e.name
  from tray_read t join capture p on p.id=t.capture_id left join exclusion e on e.capture_id=p.id
  where p.experiment_id=18 and t.status='read' and exists(select 1 from tray_reading r where r.capture_id=p.id and r.grown_method is null)""")
print("read photos with a tray lacking grown:", len(nog))
for r in nog[:30]: print("  ", r)
print("read photos with no tray rows", q("select count(*) from tray_read t join capture p on p.id=t.capture_id where p.experiment_id=18 and t.status='read' and not exists(select 1 from tray_reading r where r.capture_id=p.id)")[0][0])
print("== 2. fixed green cutoff tray areas, backup vs now (photos taken before the backup)")
from collections import defaultdict
def areas(db):
    d = defaultdict(list)
    for cid, a in q(f"select r.capture_id, r.area_mm2 from {db}.tray_reading r join {db}.capture p on p.id=r.capture_id where p.experiment_id=18 and p.taken_at<?", CUT):
        d[cid].append(a)
    return d
before, after = areas("b"), areas("main")
n_rows = sum(len(v) for v in before.values())
n_area = sum(a is not None for v in before.values() for a in v)
key = lambda a: (a is None, a or 0)
bad, worst = [], 0.0
for cid, bl in before.items():
    al = after.get(cid, [])
    bs, as_ = sorted(bl, key=key), sorted(al, key=key)
    if len(bs) != len(as_) or [a is None for a in bs] != [a is None for a in as_]:
        bad.append((cid, "rows or empty areas differ", bs, as_)); continue
    d = max([abs(x - y) for x, y in zip(bs, as_) if x is not None] or [0])
    worst = max(worst, d)
    if d > 0.01: bad.append((cid, "max diff mm2", round(d, 4)))
print("photos", len(before), "tray rows", n_rows, "with area", n_area, "| photos whose fixed cutoff areas differ by > 0.01 mm2 or whose rows differ:", len(bad), "| largest difference", round(worst, 6))
for r in bad[:10]: print("  ", r)
print("tray rows per photo, backup vs now (photos with a different count):",
  q("""select count(*) from (select p.id from b.capture p where p.experiment_id=18 and
  (select count(*) from b.tray_reading r where r.capture_id=p.id) != (select count(*) from main.tray_reading r where r.capture_id=p.id))""")[0][0])
print("== 3. cells")
print("photos before 6 Nov with cells: backup", q("select count(distinct r.capture_id) from b.cell_reading r join b.capture p on p.id=r.capture_id where p.experiment_id=18 and p.taken_at<'2026-11-06'")[0][0],
  "now", q("select count(distinct r.capture_id) from cell_reading r join capture p on p.id=r.capture_id where p.experiment_id=18 and p.taken_at<'2026-11-06'")[0][0],
  "of read photos before 6 Nov", q("select count(*) from tray_read t join capture p on p.id=t.capture_id where p.experiment_id=18 and t.status='read' and p.taken_at<'2026-11-06'")[0][0])
print("cells with grown area / all plant cells now", q("select sum(grown_area_mm2 is not null), count(*) from cell_reading r join capture p on p.id=r.capture_id where p.experiment_id=18 and r.holds='plant'"))
print("== new photos since the backup that are not read")
print(q("select p.id, p.taken_at, t.status from capture p left join tray_read t on t.capture_id=p.id where p.experiment_id=18 and p.taken_at>? and (t.status is null or t.status not in ('read','no trays found'))", CUT))
