import sqlite3, sys, json
db = sys.argv[1]
c = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
q = c.execute
HELIOS = {2688:1, 2689:2, 2690:3, 2691:4, 2692:5, 2693:6, 2694:7}
SCANS = [  # (helios_tray, filename local time)
 (2688,'2026-11-06T10:49:49'),(2689,'2026-11-06T10:50:27'),(2690,'2026-11-06T10:52:15'),
 (2692,'2026-11-06T10:54:48'),(2693,'2026-11-06T10:56:05'),(2691,'2026-11-06T11:10:14'),
 (2694,'2026-11-06T11:11:26'),
 (2693,'2026-11-12T11:29:11'),(2692,'2026-11-12T11:29:50'),(2689,'2026-11-12T11:31:38'),
 (2688,'2026-11-12T11:34:14'),(2691,'2026-11-12T11:35:26'),(2690,'2026-11-12T11:36:34'),
 (2694,'2026-11-12T11:40:10'),
]
out = []
for helios, local in SCANS:
    tag = HELIOS[helios]
    day = local[:10]
    rows = q("""select c.id, c.taken_at, c.path, e.name,
                   (select 1 from tray_reading r where r.capture_id=c.id and r.tray_id=?) seen
                from capture c left join exclusion e on e.capture_id=c.id
                where c.experiment_id=? and c.taken_at between ? and ?
                order by c.taken_at""",
             (tag, 18, day+'T06:00', day+'T14:00')).fetchall()
    rows = [r for r in rows if r[3] is None]   # lit, not excluded only
    # first photo of the removal gap: tag absent and stays absent for >=10 photos
    gap_i = None
    for i, r in enumerate(rows):
        if r[4] is None and all(x[4] is None for x in rows[i:i+10]):
            gap_i = i
            break
    if gap_i is None:
        out.append({'helios': helios, 'tag': tag, 'error': 'no removal gap'})
        continue
    paired = None
    for r in reversed(rows[:gap_i]):
        if r[4] is not None:
            paired = r
            break
    back = rows[gap_i][1]
    ret = next((r[1] for r in rows[gap_i:] if r[4] is not None), None)
    out.append({'helios': helios, 'tag': tag, 'scan_local': local,
                'capture_id': paired[0], 'paired_utc': paired[1], 'path': paired[2],
                'gone_from_utc': back, 'back_utc': ret})
print(json.dumps(out, indent=1))
