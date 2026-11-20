"""Each photo the camera called searching with E under 200,000, with the photos within N minutes
of it: [state E exclusion A=summed grow-from-leaf-cores area], * marks the photo (#293, log 42).
Read only.

    python3 dark_neighbours.py RIG_DB MINUTES
"""
import sqlite3, sys
from datetime import datetime, timedelta
c=sqlite3.connect(f"file:{sys.argv[1]}?mode=ro",uri=True)
rows=c.execute("select id, experiment_id, taken_at from capture where purpose='capture' and ae_state='searching' and exposure_us*analogue_gain<200000 order by taken_at").fetchall()
for cid,exp,t in rows:
    d=datetime.fromisoformat(t); a=(d-timedelta(minutes=int(sys.argv[2]))).isoformat(); b=(d+timedelta(minutes=int(sys.argv[2]))).isoformat()
    nb=c.execute("select id, ae_state, exposure_us*analogue_gain, (select name from exclusion e where e.capture_id=capture.id), (select round(sum(grown_area_mm2)) from tray_reading r where r.capture_id=capture.id) from capture where experiment_id=? and purpose='capture' and taken_at between ? and ? order by taken_at",(exp,a,b)).fetchall()
    print(t[5:16], " ".join(f"[{'*' if i==cid else ''}{(s or '-')[:4]} E{int(e or 0)} {(x or 'ok')[:6]} A{int(ar or 0)}]" for i,s,e,x,ar in nb))
