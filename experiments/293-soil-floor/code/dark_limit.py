"""Dark limit against the camera's auto-exposure state (#293, metrology log 42). Read only.

Photos without a state (the fallback's photos), and on photos with one: state against E = exposure x
gain at the 200,000 limit, and the E bands of photos not searching.

    python3 dark_limit.py RIG_DB
"""
import sqlite3, sys, collections
c=sqlite3.connect(f"file:{sys.argv[1]}?mode=ro",uri=True)
print("photos without ae_state, by experiment:", c.execute("select coalesce(experiment_id,0), count(*), min(taken_at), max(taken_at) from capture where purpose='capture' and ae_state is null group by 1").fetchall())
print("first photo with ae_state:", c.execute("select min(taken_at) from capture where ae_state is not null").fetchone())
t=collections.Counter()
for st,e in c.execute("select ae_state, exposure_us*analogue_gain from capture where purpose='capture' and ae_state is not null"):
    t[(st, "E>=200000" if e is not None and e>=200000 else ("E none" if e is None else "E<200000"))]+=1
print("state vs limit:", sorted(t.items()))
b=collections.Counter()
for (e,) in c.execute("select exposure_us*analogue_gain from capture where purpose='capture' and ae_state is not null and ae_state!='searching'"):
    if e is None: continue
    b["<10k" if e<1e4 else "10k-30k" if e<3e4 else "30k-100k" if e<1e5 else "100k-200k" if e<2e5 else ">=200k"]+=1
print("not searching, E bands:", dict(b))
print("largest E not searching:", c.execute("select max(exposure_us*analogue_gain) from capture where purpose='capture' and ae_state is not null and ae_state!='searching'").fetchone())
print("smallest E searching:", c.execute("select min(exposure_us*analogue_gain) from capture where purpose='capture' and ae_state='searching'").fetchone())
