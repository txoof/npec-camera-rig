"""Metrology log 39.2: readings of experiment 18 that Reprocess would grow again from the photo
(soil level in the top bin, cutoff above the floor), per tray. Run on ac-testing; read only."""
import sqlite3
c = sqlite3.connect('file:/var/lib/npec-rig/rig.db?mode=ro', uri=True)
q = """select tr.tray_id, count(*), min(c.taken_at), max(c.taken_at) from tray_reading tr
 join capture c on c.id = tr.capture_id where c.experiment_id = 18
 and tr.grown_soil_level >= 0.04 - 1e-9 and tr.grown_lower_cutoff > -0.045 + 1e-9 group by 1"""
for row in c.execute(q):
    print(*row, sep='|')
