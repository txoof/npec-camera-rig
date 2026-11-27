"""#406 stage 1: load a rig's iterdump() SQL text into a local SQLite file (no sqlite3 CLI here).
  load_dump.py DUMP.sql OUT.db"""
import sqlite3
import sys
import time

dump, out = sys.argv[1:3]
con = sqlite3.connect(out)
con.execute('PRAGMA journal_mode=OFF')
con.execute('PRAGMA synchronous=OFF')
t0 = time.time()
buf, n = [], 0
with open(dump, encoding='utf-8') as fh:
    for line in fh:
        if line.startswith(('BEGIN TRANSACTION', 'COMMIT')) and not buf:
            continue
        buf.append(line)
        if line.rstrip().endswith(';') and sqlite3.complete_statement(''.join(buf)):
            con.execute(''.join(buf))
            buf = []
            n += 1
            if n % 500000 == 0:
                con.commit()
                print(n, round(time.time() - t0), flush=True)
con.commit()
print('statements', n, 'seconds', round(time.time() - t0))
