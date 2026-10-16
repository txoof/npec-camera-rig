"""Top-down area and lengths of the Benchy Yellow-4 benchmark from a photogrammetry mesh (issue #206).

Reads the STL (and, if given, the USDZ to check it holds the same mesh), casts rays straight down
the up axis (Y) at 0.2 mm spacing, fits the board top as a plane, and reports for every object
standing on the board: area seen from above, height above the local board top, widest span
(max Feret diameter) and smallest enclosing rectangle. Results go to stdout; nothing is written.

    python3 -m venv venv
    venv/bin/pip install trimesh numpy scipy rtree tinyusdz
    venv/bin/python mesh_area.py photogrammetry_mesh.stl [photogrammetry_mesh.usdz]
"""

import re
import sys

import numpy as np
import trimesh
from scipy import ndimage
from scipy.spatial import ConvexHull
from scipy.spatial.distance import pdist

RES = 0.0002  # ray spacing, m (0.2 mm)
THRESHOLDS_MM = (1.0, 2.0, 3.0, 5.0)  # height above the board plane that counts as an object
MIN_AREA_MM2 = 20.0


def usd_mesh(path):
    """Points and triangles of the single mesh in a USDZ, via tinyusdz's text export."""
    import tinyusdz

    text = tinyusdz.load(path).export_to_string()

    def numbers(name, cast):
        body = re.search(name + r" = \[(.*?)\]\n", text, re.S).group(1)
        return np.array([cast(n) for n in re.findall(r"-?[0-9.]+(?:e-?[0-9]+)?", body)])

    meta = re.search(r"metersPerUnit = (\S+)", text).group(1), re.search(r'upAxis = "(\w)"', text).group(1)
    creator = re.search(r'string creator = "(.*?)"', text).group(1)
    config = re.search(r'string config = "(.*?)"', text).group(1)
    pts = numbers(r"point3f\[\] points", float).reshape(-1, 3)
    tri = numbers(r"int\[\] faceVertexIndices", int).reshape(-1, 3)
    return pts, tri, meta, creator, config


def min_rect(points):
    """Sides of the smallest-area rectangle around 2D points (rotating calipers on the hull)."""
    hull = points[ConvexHull(points).vertices]
    best = None
    for i in range(len(hull)):
        edge = hull[(i + 1) % len(hull)] - hull[i]
        u = edge / np.linalg.norm(edge)
        q = hull @ np.array([u, [-u[1], u[0]]]).T
        w, d = np.ptp(q[:, 0]), np.ptp(q[:, 1])
        if best is None or w * d < best[0]:
            best = (w * d, min(w, d), max(w, d))
    return best[1], best[2]


def main(stl_path, usdz_path=None):
    mesh = trimesh.load(stl_path)
    print(f"STL header: {open(stl_path, 'rb').read(80).rstrip(bytes(1)).decode(errors='replace')}")
    print(f"STL: {len(mesh.vertices)} vertices, {len(mesh.faces)} triangles, "
          f"surface {mesh.area * 1e6:.0f} mm2, watertight {mesh.is_watertight}, "
          f"mean triangle {mesh.area / len(mesh.faces) * 1e6:.2f} mm2")
    if usdz_path:
        pts, tri, (mpu, up), creator, config = usd_mesh(usdz_path)
        # trimesh renumbers STL vertices on load, so compare the triangles, not the indices.
        a = np.sort(pts[tri].reshape(-1, 9), axis=0)
        b = np.sort(mesh.triangles.reshape(-1, 9), axis=0)
        same = a.shape == b.shape and np.allclose(a, b, atol=1e-6)
        print(f"USDZ: metersPerUnit {mpu}, upAxis {up}, creator {creator!r}")
        print(f"USDZ config: {config!r}")
        print(f"USDZ mesh identical to STL: {same}")

    lo, hi = mesh.bounds
    xs = np.arange(lo[0], hi[0], RES) + RES / 2
    zs = np.arange(lo[2], hi[2], RES) + RES / 2
    X, Z = np.meshgrid(xs, zs)
    origins = np.column_stack([X.ravel(), np.full(X.size, hi[1] + 0.01), Z.ravel()])
    loc, ray, _ = mesh.ray.intersects_location(origins, np.tile([0, -1.0, 0], (X.size, 1)),
                                               multiple_hits=False)
    H = np.full(X.size, np.nan)
    H[ray] = loc[:, 1]
    H = H.reshape(X.shape) * 1000  # top surface height, mm
    cell = (RES * 1e3) ** 2

    board = np.isfinite(H)
    w, d = min_rect(np.column_stack([X[board], Z[board]]) * 1e3)
    print(f"board seen from above: {board.sum() * cell:.0f} mm2, rectangle {w:.1f} x {d:.1f} mm")

    # Board top as a plane: least squares on the lower cells, then 3 passes dropping cells
    # more than 3 SD from it.
    yy, xx = np.nonzero(board)
    h = H[yy, xx]
    A = np.column_stack([xx, yy, np.ones(len(xx))])
    keep = h < np.percentile(h, 60)
    for _ in range(3):
        coef, *_ = np.linalg.lstsq(A[keep], h[keep], rcond=None)
        resid = h - A @ coef
        keep = np.abs(resid) < 3 * np.std(resid[keep])
    tilt = coef[:2] / (RES * 1e3) * 1000  # mm per pixel -> mm per metre
    print(f"board plane: tilt {tilt[0]:.1f} and {tilt[1]:.1f} mm per m, "
          f"spread of board cells about it {np.std(resid[keep]):.2f} mm (SD)")
    above = np.full(H.shape, np.nan)
    above[yy, xx] = resid
    above0 = np.nan_to_num(above, nan=0)

    for thr in THRESHOLDS_MM:
        lab, n = ndimage.label(ndimage.binary_fill_holes(above0 > thr))
        print(f"\nobjects more than {thr} mm above the board plane:")
        for i in range(1, n + 1):
            obj = lab == i
            area = obj.sum() * cell
            if area < MIN_AREA_MM2:
                continue
            ring = ndimage.binary_dilation(obj, iterations=50) & ~ndimage.binary_dilation(obj, iterations=20)
            top = np.nanmax(H[obj]) - np.nanmedian(H[ring & board])
            edge = obj & ~ndimage.binary_erosion(obj)
            ey, ex = np.nonzero(edge)
            e = np.column_stack([xs[ex], zs[ey]]) * 1e3
            feret = pdist(e[ConvexHull(e).vertices]).max()
            rw, rd = min_rect(e)
            cy, cx = ndimage.center_of_mass(obj)
            print(f"  centre x {xs[int(cx)] * 1e3:7.1f} z {zs[int(cy)] * 1e3:7.1f} mm: "
                  f"area {area:7.1f} mm2, top {top:5.2f} mm above board, "
                  f"widest span {feret:5.2f} mm, rectangle {rw:5.2f} x {rd:5.2f} mm")


if __name__ == "__main__":
    main(*sys.argv[1:3])
