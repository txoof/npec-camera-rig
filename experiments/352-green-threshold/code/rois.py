"""Read ImageJ .roi files (polygon type 0 with sub-pixel coords, rectangle type 1) and rasterise them
the ImageJ way: a pixel is inside when its centre is inside the polygon."""
import struct, zipfile, csv
import numpy as np


def read_roi(d):
    typ = d[6]
    top, left, bottom, right, n = struct.unpack('>hhhhH', d[8:18])
    opts = struct.unpack('>h', d[50:52])[0]
    if typ == 1:
        return typ, np.array([[left, top], [right, top], [right, bottom], [left, bottom]], float)
    xs = np.array(struct.unpack(f'>{n}h', d[64:64 + 2 * n]), float) + left
    ys = np.array(struct.unpack(f'>{n}h', d[64 + 2 * n:64 + 4 * n]), float) + top
    if opts & 128:  # sub-pixel: float coordinates follow the integer ones
        o = 64 + 4 * n
        xs = np.array(struct.unpack(f'>{n}f', d[o:o + 4 * n]), float)
        ys = np.array(struct.unpack(f'>{n}f', d[o + 4 * n:o + 8 * n]), float)
    return typ, np.stack([xs, ys], 1)


def read_zip(path):
    z = zipfile.ZipFile(path)
    return [(nm,) + read_roi(z.read(nm)) for nm in z.namelist()]


def raster(poly, w, h):
    """True where the pixel centre (x + 0.5, y + 0.5) is inside `poly` (even-odd rule)."""
    yy, xx = np.mgrid[0:h, 0:w]
    px, py = xx.ravel() + 0.5, yy.ravel() + 0.5
    inside = np.zeros(px.shape, bool)
    x0, y0 = poly[:, 0], poly[:, 1]
    x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
    for a, b, c, e in zip(x0, y0, x1, y1):
        if b == e:
            continue
        cond = (b > py) != (e > py)
        xc = a + (py - b) * (c - a) / (e - b)
        inside ^= cond & (px < xc)
    return inside.reshape(h, w)


def shoelace(p):
    x, y = p[:, 0], p[:, 1]
    return abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2


def read_results(path):
    with open(path) as f:
        rows = [r for r in csv.reader(l for l in f if not l.startswith('#'))]
    h = rows[0]
    return [dict(zip(h, r)) for r in rows[1:]]
