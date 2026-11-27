"""Metrology log 41: every tray reading and cell reading of experiment 18, as stored, written to
stdout as CSV. Run on ac-testing before and after the Reprocess; read only (mode=ro).

    ssh pi@ac-testing python3 - tray < snapshot.py | gzip > before_tray.csv.gz
    ssh pi@ac-testing python3 - cell < snapshot.py | gzip > before_cell.csv.gz
"""
import csv, sqlite3, sys

KIND = sys.argv[1]
c = sqlite3.connect('file:/var/lib/npec-rig/rig.db?mode=ro', uri=True)
if KIND == 'tray':
    q = """select tr.capture_id, tr.tray_id, round(tr.centre_x_px), round(tr.centre_y_px), tr.area_mm2, tr.grown_area_mm2, tr.grown_plant_px,
        tr.grown_soil_level, tr.grown_lower_cutoff, tr.warnings from tray_reading tr
        join capture c on c.id = tr.capture_id where c.experiment_id = 18 order by 1, 2, 3"""
    head = ['capture_id', 'tray_id', 'centre_x_px', 'centre_y_px', 'area_mm2', 'grown_area_mm2', 'grown_plant_px',
            'grown_soil_level', 'grown_lower_cutoff', 'warnings']
else:
    q = """select cr.capture_id, cr.tray_id, cr.cell, cr.area_mm2, cr.grown_area_mm2 from cell_reading cr
        join capture c on c.id = cr.capture_id where c.experiment_id = 18 order by 1, 2, 3"""
    head = ['capture_id', 'tray_id', 'cell', 'area_mm2', 'grown_area_mm2']
w = csv.writer(sys.stdout)
w.writerow(head)
for row in c.execute(q):
    w.writerow(row)
