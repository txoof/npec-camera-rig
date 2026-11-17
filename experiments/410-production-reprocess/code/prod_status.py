# Read-only status of production experiment 18 (#410). Piped over ssh: ssh pi@ac-testing python3 - < prod_status.py
import sqlite3, datetime
c = sqlite3.connect("file:/var/lib/npec-rig/rig.db?mode=ro", uri=True)
q = lambda s, *a: c.execute(s, a).fetchall()
print("now", datetime.datetime.utcnow().isoformat(timespec="seconds"), "user_version", q("pragma user_version")[0][0])
print("photos", q("select count(*) from capture where experiment_id=18")[0][0])
print("tray_read", q("select status, count(*) from tray_read join capture on capture.id=capture_id where experiment_id=18 group by status"))
print("photos with grown", q("select count(distinct r.capture_id) from tray_reading r join capture p on p.id=r.capture_id where p.experiment_id=18 and r.grown_method is not null")[0][0])
print("photos with cells", q("select count(distinct r.capture_id) from cell_reading r join capture p on p.id=r.capture_id where p.experiment_id=18")[0][0])
print("last 3 photos", q("select p.id, p.taken_at, e.name, t.read_at, t.status from capture p left join exclusion e on e.capture_id=p.id left join tray_read t on t.capture_id=p.id where experiment_id=18 order by p.id desc limit 3"))
