"""Round-trip checks for mask_rois.py (#402). Plain asserts, run directly:

  uv run --no-project --python /usr/bin/python3 --with numpy --with pillow --with roifile \
      python -I experiments/round3-classifier/code/test_mask_rois.py

Not collected by the project's pytest (pyproject.toml testpaths = ["tests"]).
roifile is optional: when present, every written zip is also read with it as an outside check
of the file format.
"""
import csv
import os
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
IJ = os.path.join(REPO, 'experiments', '352-green-threshold', 'data', 'imagej')
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, 'experiments', '352-green-threshold', 'code'))
import mask_rois  # noqa: E402
import rois  # noqa: E402  (the #352 reader, used as the reference fill)

try:
    import roifile
except ImportError:
    roifile = None

TMP = tempfile.mkdtemp(prefix='mask_rois_')


def roifile_mask(path, w, h):
    """Independent read of a zip with roifile, filled with the #352 rule (rois.raster)."""
    out = np.zeros((h, w), bool)
    for r in roifile.roiread(path):
        paths = r.coordinates(multi=True)
        if paths is None:
            continue
        if isinstance(paths, np.ndarray):
            paths = [paths]
        m = np.zeros((h, w), bool)
        for p in paths:
            m ^= rois.raster(np.asarray(p, float), w, h)
        out |= m
    return out


def round_trip(mask, label):
    mask = np.asarray(mask, bool)
    h, w = mask.shape
    path = os.path.join(TMP, label + '.zip')
    names = mask_rois.mask_to_roi_zip(mask, path, label)
    back = mask_rois.roi_zip_to_mask(path, w, h)
    assert back.shape == mask.shape
    assert np.array_equal(back, mask), f'{label}: {int((back ^ mask).sum())} pixels differ'
    if roifile is not None:
        assert np.array_equal(roifile_mask(path, w, h), mask), f'{label}: roifile read differs'
    kinds = [k for _, k, _, _ in mask_rois.read_roi_zip(path)]
    return names, kinds


def test_synthetic():
    m = np.zeros((7, 9), bool)
    m[3, 4] = True
    names, kinds = round_trip(m, 'single')
    assert names == ['single_p001'] and kinds == ['traced']

    m = np.zeros((6, 6), bool)
    m[1, 1] = m[2, 2] = m[3, 3] = True  # diagonal chain: one 8-connected piece
    m[1, 4] = m[2, 3] = True            # anti-diagonal touching the chain at a corner
    names, kinds = round_trip(m, 'diagonal')
    assert len(names) == 1 and kinds == ['traced']

    m = np.zeros((4, 4), bool)
    m[0, 0] = m[1, 1] = True
    m[0, 3] = True  # separate piece in a crop corner
    names, _ = round_trip(m, 'diag_pair')
    assert len(names) == 2

    m = np.zeros((9, 9), bool)
    m[1:8, 1:8] = True
    m[3:6, 3:6] = False
    m[4, 4] = True  # island in the hole: its own piece
    names, kinds = round_trip(m, 'ring')
    assert kinds == ['composite', 'traced'], kinds

    m = np.zeros((5, 5), bool)  # hole touching the outline only at a corner (4-connected hole)
    m[1:4, 1:4] = True
    m[2, 2] = False   # hole
    m[1, 1] = False   # notch: the hole meets the outside at the corner (2, 2)
    names, kinds = round_trip(m, 'pinched_hole')
    assert kinds == ['composite'], kinds

    m = np.zeros((8, 8), bool)  # background diagonal gap inside a piece: two holes
    m[1:7, 1:7] = True
    m[3, 3] = m[4, 4] = False
    names, kinds = round_trip(m, 'two_diag_holes')
    assert kinds == ['composite']

    m = np.zeros((10, 12), bool)
    m[2, 1:11] = True      # 1 px horizontal line
    m[3:9, 5] = True       # 1 px vertical line joined to it
    for i in range(5):
        m[3 + i, 7 + i] = True  # 1 px diagonal, touching the horizontal line at a corner
    round_trip(m, 'lines')

    m = np.zeros((6, 7), bool)
    m[:, 0] = True     # touches left, top and bottom borders
    m[0, :] = True
    m[5, 3:] = True    # touches bottom and right
    m[2:4, 6] = True
    round_trip(m, 'border')

    round_trip(np.ones((5, 4), bool), 'full')
    names, _ = round_trip(np.zeros((5, 4), bool), 'empty')
    assert names == []

    rng = np.random.default_rng(402)
    for i in range(40):
        m = rng.random((25, 30)) < rng.uniform(0.2, 0.7)
        round_trip(m, f'random{i:02d}')
    m = np.indices((20, 20)).sum(0) % 2 == 0  # checkerboard: all corner touches
    names, _ = round_trip(m, 'checker')
    assert len(names) == 1


def test_vertex_count():
    m = np.zeros((40, 50), bool)
    m[5:30, 10:45] = True
    path = os.path.join(TMP, 'rect.zip')
    mask_rois.mask_to_roi_zip(m, path, 'rect')
    (_, kind, name, outl), = mask_rois.read_roi_zip(path)
    assert kind == 'traced' and name == 'rect_p001' and len(outl[0]) == 4


def test_crops():
    tifs = sorted(f for f in os.listdir(IJ) if f.endswith('.tif'))
    assert len(tifs) == 16
    total = 0
    for f in tifs:
        rgb = np.asarray(Image.open(os.path.join(IJ, f)).convert('RGB')).astype(np.float64)
        r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        exg = (2 * g - r - b) / np.maximum(r + g + b, 1e-6)
        m = exg > 0
        names, kinds = round_trip(m, f[:-4])
        total += len(names)
        print(f'  {f}: {int(m.sum())} px, {len(names)} pieces, '
              f'{kinds.count("composite")} with holes')
    assert total > 16


def test_pass1_against_rois_py():
    """Pass 1 read with mask_rois against rois.py + raster (polygon ROIs), and every ROI's pixel
    count (composite included) against the Area ImageJ itself measured (Results.csv).
    rois.raster counts a pixel centre lying exactly on a top edge as inside; ImageJ's
    PolygonFiller counts it outside. The polygon tool at 800% puts vertices on 1/8 px, so such
    ties happen: there the two readers may differ, and ImageJ's Area decides."""
    zp = os.path.join(IJ, 'pass_1_2026.11.04_Results.roi.zip')
    man = {r['file']: r for r in csv.DictReader(open(os.path.join(IJ, 'manifest.csv')))}
    res = rois.read_results(os.path.join(IJ, 'pass_1_2026.11.04_Results.csv'))
    res = res[:15] + [res[16]]  # as in 352 compare.py: row 16 was an unsaved outline
    old = rois.read_zip(zp)
    new = mask_rois.read_roi_zip(zp)
    same, tie = 0, []
    for (nm, typ, poly), (entry, kind, _, outl), r in zip(old, new, res):
        assert nm == entry
        lab = r['Label'].split(':')[0]
        w, h = int(man[lab]['width']), int(man[lab]['height'])
        m = mask_rois.fill(outl, w, h)
        assert int(m.sum()) == int(r['Area']), (nm, kind, int(m.sum()), r['Area'])
        if typ == 0:
            ref = rois.raster(poly, w, h)
            if np.array_equal(m, ref):
                same += 1
            else:
                assert np.any(poly[:, 1] % 1 == 0.5), f'{nm}: differs with no vertex on a centre row'
                tie.append((nm, int(ref.sum()) - int(m.sum())))
    print(f'  pass 1: {same} polygons equal to rois.raster, {len(tie)} differ at ties '
          f'(rois.raster minus ImageJ, px): {tie}')
    assert same + len(tie) == 15


def test_pass2_imagej_area():
    zp = os.path.join(IJ, 'pass_2_2026.11.05_Results.roi.zip')
    man = {r['file']: r for r in csv.DictReader(open(os.path.join(IJ, 'manifest.csv')))}
    res = rois.read_results(os.path.join(IJ, 'pass_2_2026.11.05_Results.csv'))
    new = mask_rois.read_roi_zip(zp)
    assert len(new) == len(res)
    for (entry, kind, _, outl), r in zip(new, res):
        lab = r['Label'].split(':')[0]
        w, h = int(man[lab]['width']), int(man[lab]['height'])
        assert int(mask_rois.fill(outl, w, h).sum()) == int(r['Area']), (entry, kind)


if __name__ == '__main__':
    print('roifile', 'present' if roifile else 'absent (outside format check skipped)')
    for name, fn in list(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print('ok', name)
    print('all passed')
