"""Issue #511, Part 3: compare two rig.db files reading for reading, over one list of photos.

Used for A (the Pi's result against this box's) and for B (serial against parallel). Compares
`tray_reading.area_mm2` / `grown_area_mm2` and `cell_reading.area_mm2` / `grown_area_mm2`, which
are what the pass rule names, and reports every reading outside the tolerance per tray and photo.
Reads both databases; writes neither.

Exit 0 when every compared reading is inside the tolerance, 1 when any is outside.

Usage: compare_runs.py <reference rig.db> <candidate rig.db> <paths file> [tolerance_mm2]
"""

import sqlite3
import sys

DEFAULT_TOLERANCE = 0.01  # mm², the pass rule in log 41


def load(db_path: str, paths: list[str]) -> tuple[dict, dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ids = {}
    for path in paths:
        row = conn.execute("SELECT id FROM capture WHERE path = ?", (path,)).fetchone()
        if row:
            ids[row["id"]] = path

    trays, cells = {}, {}
    for capture_id, path in ids.items():
        for r in conn.execute(
            "SELECT tray_id, slot, area_mm2, grown_area_mm2 FROM tray_reading WHERE capture_id = ?",
            (capture_id,),
        ):
            trays[(path, r["tray_id"], r["slot"])] = (r["area_mm2"], r["grown_area_mm2"])
        for r in conn.execute(
            "SELECT tray_id, cell, centre_x_px, area_mm2, grown_area_mm2 FROM cell_reading"
            " WHERE capture_id = ?",
            (capture_id,),
        ):
            # centre_x_px disambiguates two trays carrying one tag in the same photo, the way
            # `slot` does for tray readings: without it the second tray overwrites the first.
            cells[(path, r["tray_id"], r["cell"], r["centre_x_px"])] = (r["area_mm2"], r["grown_area_mm2"])
    conn.close()
    return trays, cells


def compare(name: str, ref: dict, cand: dict, tolerance: float) -> tuple[int, list, float]:
    def order(key):  # tray_id and slot are None for a tray with no tag (#302)
        return tuple("" if part is None else str(part) for part in key)

    outside, worst = [], 0.0
    only_ref = set(ref) - set(cand)
    only_cand = set(cand) - set(ref)
    shared = set(ref) & set(cand)
    for key in sorted(shared, key=order):
        for field, i in (("area_mm2", 0), ("grown_area_mm2", 1)):
            a, b = ref[key][i], cand[key][i]
            if a is None and b is None:
                continue
            if a is None or b is None:
                outside.append((key, field, a, b, None))
                continue
            diff = abs(a - b)
            worst = max(worst, diff)
            if diff > tolerance:
                outside.append((key, field, a, b, diff))
    print(f"\n== {name} ==")
    print(f"  compared:            {len(shared)}")
    print(f"  only in reference:   {len(only_ref)}")
    print(f"  only in candidate:   {len(only_cand)}")
    print(f"  largest difference:  {worst:.6f} mm²   (tolerance {tolerance} mm²)")
    print(f"  outside tolerance:   {len(outside)}")
    for key, field, a, b, diff in outside[:40]:
        path, tray, part = key
        shown = f"{diff:.6f}" if diff is not None else "one side missing"
        print(f"    {path}  tray {tray}  {part}  {field}: ref={a} cand={b} diff={shown}")
    if len(outside) > 40:
        print(f"    ... and {len(outside) - 40} more")
    if only_ref:
        print("  readings the candidate does not have (first 10):")
        for key in sorted(only_ref, key=order)[:10]:
            print(f"    {key}")
    return len(shared), outside, worst


def main() -> int:
    ref_db, cand_db, paths_file = sys.argv[1], sys.argv[2], sys.argv[3]
    tolerance = float(sys.argv[4]) if len(sys.argv) > 4 else DEFAULT_TOLERANCE
    paths = [line.strip() for line in open(paths_file) if line.strip()]

    print(f"photos: {len(paths)}")
    print(f"reference: {ref_db}")
    print(f"candidate: {cand_db}")

    ref_trays, ref_cells = load(ref_db, paths)
    cand_trays, cand_cells = load(cand_db, paths)

    n_t, out_t, worst_t = compare("tray readings", ref_trays, cand_trays, tolerance)
    n_c, out_c, worst_c = compare("cell readings", ref_cells, cand_cells, tolerance)

    # A reading present on one side only is a failure too: a worker that died before writing a
    # photo leaves the candidate short, and counting only differing values would pass it.
    missing = len(set(ref_trays) ^ set(cand_trays)) + len(set(ref_cells) ^ set(cand_cells))
    passed = not out_t and not out_c and missing == 0
    print("\n" + "=" * 60)
    print(f"tray readings compared: {n_t}, outside: {len(out_t)}, worst {worst_t:.6f} mm²")
    print(f"cell readings compared: {n_c}, outside: {len(out_c)}, worst {worst_c:.6f} mm²")
    print(f"readings on one side only: {missing}")
    print("RESULT:", "PASS — every reading within tolerance" if passed else "FAIL — readings outside tolerance listed above")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
