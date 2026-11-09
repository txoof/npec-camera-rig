"""Plant masks to ImageJ ROI zips and back, pixel for pixel (#402).

mask_to_roi_zip(mask, path, name_prefix) writes one ROI per 8-connected piece of a bool mask,
outlined along pixel edges (integer pixel-corner coordinates, collinear points merged):
  - a piece with no hole is a "traced" ROI (type 8), the type the Wand tool makes;
  - a piece with holes is a composite ROI (ImageJ ShapeRoi), outer outline plus one closed
    outline per hole, the type ImageJ makes for Alt + polygon (subtract) or the selection brush.
Names are <prefix>_p001, <prefix>_p002, ... in the order the pieces are found (row by row).
A crop with no plant pixels gives a zip with no ROIs.

roi_zip_to_mask(path, w, h) reads a ROI Manager zip back: the union of every ROI's mask.
Each ROI is filled the ImageJ way (ij.process.PolygonFiller): a pixel is inside when its centre
(x + 0.5, y + 0.5) is inside the outline, even-odd over all the outlines of that ROI. That is how
a composite ROI's holes come out. Types read:
  polygon (0), freehand (7), traced (8), integer or sub-pixel float coordinates;
  rectangle (1) without rounded corners; composite (rectangle type with a shape array).
Lines, polylines, angles and points have no area: they are skipped with a warning.
Ovals, rounded rectangles and spline-fitted polygons are refused (ValueError), because ImageJ
fills them from a polygon it computes itself, which this module does not reproduce.

How to edit in ImageJ: open the crop, ROI Manager > More > Open the zip, select a piece, change it
(selection brush, or Shift / Alt with the polygon or freehand tool to add or cut), then ROI Manager
> Update. A piece with holes is one composite ROI: edit it as a whole; do not use More > Split,
which turns each hole into a filled ROI of its own. More > Save writes the zip back.
"""
import struct
import warnings
import zipfile

import numpy as np

# ImageJ ROI type codes (ij.io.RoiDecoder)
POLYGON, RECT, OVAL, LINE, FREELINE, POLYLINE, NOROI, FREEHAND, TRACED, ANGLE, POINT = range(11)
_NO_AREA = {LINE: 'line', FREELINE: 'freehand line', POLYLINE: 'polyline', ANGLE: 'angle',
            POINT: 'point', NOROI: 'no roi'}
_SPLINE_FIT, _SUB_PIXEL = 1, 128
_VERSION = 228
_HEADER, _HEADER2 = 64, 64
# java.awt.geom.PathIterator segment codes, as stored in a composite ROI
_MOVETO, _LINETO, _QUADTO, _CUBICTO, _CLOSE = range(5)


# ---------------------------------------------------------------- mask to outlines

def _pieces(mask):
    """Label 8-connected pieces. Returns (labels, n); labels are 1..n in row-major order of
    each piece's first pixel."""
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    n = 0
    for y0, x0 in zip(*np.nonzero(mask)):
        if lab[y0, x0]:
            continue
        n += 1
        lab[y0, x0] = n
        stack = [(y0, x0)]
        while stack:
            y, x = stack.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not lab[yy, xx]:
                        lab[yy, xx] = n
                        stack.append((yy, xx))
    return lab, n


def _loops(piece):
    """Closed outlines along pixel edges of one 8-connected piece (bool array).
    Edges run with the piece on the right (y down). Where two piece pixels touch only at a
    corner, the outline turns left there, so both stay on one outline (8-connected piece,
    4-connected holes). Returns a list of vertex lists, collinear points merged."""
    p = np.pad(piece, 1)
    out = {}  # vertex -> list of next vertices

    def add(a, b):
        out.setdefault(a, []).append(b)

    ys, xs = np.nonzero(p[1:-1, 1:-1])
    for y, x in zip(ys.tolist(), xs.tolist()):
        py, px = y + 1, x + 1
        if not p[py - 1, px]:
            add((x, y), (x + 1, y))
        if not p[py, px + 1]:
            add((x + 1, y), (x + 1, y + 1))
        if not p[py + 1, px]:
            add((x + 1, y + 1), (x, y + 1))
        if not p[py, px - 1]:
            add((x, y + 1), (x, y))
    loops = []
    while out:
        start = min(out)
        a, b = start, out[start].pop()
        if not out[a]:
            del out[a]
        loop = [a]
        while b != start:
            loop.append(b)
            nxt = out[b]
            if len(nxt) == 1:
                c = nxt.pop()
            else:  # corner touch: take the left turn
                dx, dy = b[0] - a[0], b[1] - a[1]
                left = (b[0] + dy, b[1] - dx)
                c = left if left in nxt else nxt[0]
                nxt.remove(c)
            if not nxt:
                del out[b]
            a, b = b, c
        loops.append(_merge_collinear(loop))
    return loops


def _merge_collinear(loop):
    n = len(loop)
    keep = []
    for i in range(n):
        a, b, c = loop[i - 1], loop[i], loop[(i + 1) % n]
        if (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) != 0:
            keep.append(b)
    return keep


def _signed_area2(loop):
    x = np.array([v[0] for v in loop], np.int64)
    y = np.array([v[1] for v in loop], np.int64)
    return int(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


# ---------------------------------------------------------------- .roi encoding

def _header(typ, bounds, n=0, shape_size=0):
    left, top, right, bottom = bounds
    d = bytearray(_HEADER)
    d[0:4] = b'Iout'
    struct.pack_into('>h', d, 4, _VERSION)
    d[6] = typ
    struct.pack_into('>hhhhH', d, 8, top, left, bottom, right, n)
    struct.pack_into('>i', d, 36, shape_size)
    return d


def _header2(name, offset):
    """Header 2 at `offset`, followed by the name in UTF-16 big-endian."""
    d = bytearray(_HEADER2)
    struct.pack_into('>ii', d, 16, offset + _HEADER2, len(name))
    return d + name.encode('utf-16-be')


def _encode_traced(loop, name):
    xs = [v[0] for v in loop]
    ys = [v[1] for v in loop]
    left, top = min(xs), min(ys)
    d = _header(TRACED, (left, top, max(xs), max(ys)), n=len(loop))
    d += struct.pack(f'>{len(xs)}h', *[x - left for x in xs])
    d += struct.pack(f'>{len(ys)}h', *[y - top for y in ys])
    struct.pack_into('>i', d, 60, len(d))
    return bytes(d + _header2(name, len(d)))


def _encode_composite(loops, name):
    arr = []
    for loop in loops:
        arr += [_MOVETO, *loop[0]]
        for v in loop[1:]:
            arr += [_LINETO, *v]
        arr.append(_CLOSE)
    xs = [v[0] for lp in loops for v in lp]
    ys = [v[1] for lp in loops for v in lp]
    d = _header(RECT, (min(xs), min(ys), max(xs), max(ys)), shape_size=len(arr))
    d += struct.pack(f'>{len(arr)}f', *arr)
    struct.pack_into('>i', d, 60, len(d))
    return bytes(d + _header2(name, len(d)))


def mask_to_roi_zip(mask, path, name_prefix):
    """Write `mask` (2-D bool) as an ImageJ ROI Manager zip at `path`. Returns the ROI names."""
    mask = np.asarray(mask, bool)
    if mask.ndim != 2:
        raise ValueError('mask must be 2-D')
    if max(mask.shape) > 32767:
        raise ValueError('ImageJ ROI coordinates are 16-bit: crop must be under 32768 px')
    lab, n = _pieces(mask)
    names = []
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for k in range(1, n + 1):
            loops = _loops(lab == k)
            outer = [lp for lp in loops if _signed_area2(lp) > 0]
            holes = [lp for lp in loops if _signed_area2(lp) < 0]
            assert len(outer) == 1, f'piece {k}: {len(outer)} outer outlines'
            name = f'{name_prefix}_p{k:03d}'
            if holes or len(outer[0]) > 65535:
                data = _encode_composite(outer + holes, name)
            else:
                data = _encode_traced(outer[0], name)
            z.writestr(name + '.roi', data)
            names.append(name)
    return names


# ---------------------------------------------------------------- .roi decoding

def _name(d):
    off = struct.unpack('>i', d[60:64])[0]
    if off <= 0 or off + 24 > len(d):
        return None
    no, nl = struct.unpack('>ii', d[off + 16:off + 24])
    if no <= 0 or nl <= 0 or no + 2 * nl > len(d):
        return None
    return d[no:no + 2 * nl].decode('utf-16-be')


def _shape_paths(arr, curve_steps=16):
    """Composite ROI segment array to a list of closed (k, 2) float vertex arrays (image
    coordinates). Curves are flattened into `curve_steps` straight pieces (approximate; ImageJ
    flattens with its own tolerance)."""
    paths, cur, i = [], [], 0
    pen = None
    while i < len(arr):
        t = int(arr[i])
        if t == _MOVETO:
            if len(cur) > 2:
                paths.append(np.array(cur))
            cur = [(arr[i + 1], arr[i + 2])]
            pen = cur[0]
            i += 3
        elif t == _LINETO:
            cur.append((arr[i + 1], arr[i + 2]))
            i += 3
        elif t in (_QUADTO, _CUBICTO):
            k = 2 if t == _QUADTO else 3
            ctrl = [cur[-1]] + [(arr[i + 1 + 2 * j], arr[i + 2 + 2 * j]) for j in range(k)]
            s = np.linspace(0, 1, curve_steps + 1)[1:, None]
            c = np.array(ctrl)
            if k == 2:
                pts = (1 - s) ** 2 * c[0] + 2 * (1 - s) * s * c[1] + s ** 2 * c[2]
            else:
                pts = ((1 - s) ** 3 * c[0] + 3 * (1 - s) ** 2 * s * c[1]
                       + 3 * (1 - s) * s ** 2 * c[2] + s ** 3 * c[3])
            cur += [tuple(p) for p in pts]
            i += 1 + 2 * k
        elif t == _CLOSE:
            if len(cur) > 2:
                paths.append(np.array(cur))
            cur = [pen] if pen is not None else []
            i += 1
        else:
            raise ValueError(f'unknown composite segment type {t}')
    if len(cur) > 2:
        paths.append(np.array(cur))
    return paths


def read_roi(data):
    """One .roi file's bytes to (type, name, list of closed outlines as (k, 2) float arrays in
    image coordinates). Outlines of one ROI are filled even-odd together. Returns outlines=None
    for types with no area."""
    d = data
    if d[:4] != b'Iout':
        raise ValueError('not an ImageJ .roi file')
    version = struct.unpack('>h', d[4:6])[0]
    typ = d[6]
    top, left, bottom, right = struct.unpack('>hhhh', d[8:16])
    n = struct.unpack('>H', d[16:18])[0]
    shape_size = struct.unpack('>i', d[36:40])[0]
    opts = struct.unpack('>h', d[50:52])[0]
    name = _name(d)
    sub_pixel = bool(opts & _SUB_PIXEL) and version >= 222
    if shape_size > 0:
        arr = struct.unpack(f'>{shape_size}f', d[64:64 + 4 * shape_size])
        return 'composite', name, _shape_paths(arr)
    if typ in _NO_AREA:
        return _NO_AREA[typ], name, None
    if typ == RECT:
        if struct.unpack('>h', d[54:56])[0] > 0:
            raise ValueError(f'{name}: rounded rectangle not supported')
        return 'rectangle', name, [np.array([[left, top], [right, top], [right, bottom],
                                             [left, bottom]], float)]
    if typ == OVAL:
        raise ValueError(f'{name}: oval ROI not supported; convert it first '
                         '(Edit > Selection > Interpolate, or brush it into a traced ROI)')
    if typ not in (POLYGON, FREEHAND, TRACED):
        raise ValueError(f'{name}: ROI type {typ} not supported')
    if opts & _SPLINE_FIT:
        raise ValueError(f'{name}: spline-fitted ROI not supported; undo Fit Spline')
    if sub_pixel:
        o = 64 + 4 * n
        xs = np.array(struct.unpack(f'>{n}f', d[o:o + 4 * n]), float)
        ys = np.array(struct.unpack(f'>{n}f', d[o + 4 * n:o + 8 * n]), float)
    else:
        xs = np.maximum(np.array(struct.unpack(f'>{n}h', d[64:64 + 2 * n]), float), 0) + left
        ys = np.maximum(np.array(struct.unpack(f'>{n}h', d[64 + 2 * n:64 + 4 * n]), float), 0) + top
    kind = {POLYGON: 'polygon', FREEHAND: 'freehand', TRACED: 'traced'}[typ]
    return kind, name, [np.stack([xs, ys], 1)]


def read_roi_zip(path):
    """List of (entry name, type, roi name, outlines) for every .roi in a ROI Manager zip."""
    with zipfile.ZipFile(path) as z:
        return [(e,) + read_roi(z.read(e)) for e in z.namelist() if e.endswith('.roi')]


def _jround(v):
    """Java Math.round for doubles: floor(v + 0.5)."""
    return int(np.floor(v + 0.5))


def fill(outlines, w, h):
    """Bool (h, w) mask of the outlines, even-odd over all of them, as ij.process.PolygonFiller
    (ImageJ 1.54) computes it, ties included: a pixel is inside when its centre
    (x + 0.5, y + 0.5) is inside; a centre exactly on a left edge is outside, on a right edge
    inside; exactly on a top edge outside, on a bottom edge inside. Integer outlines (traced,
    or polygons stored without sub-pixel floats) use PolygonFiller's integer path, the others
    its float path with Java rounding and the same 1e-8 shift and row-by-row accumulation."""
    cnt = np.zeros((h, w + 1), np.int32)
    for poly in outlines:
        poly = np.asarray(poly, np.float64)
        integer = np.all(poly == np.round(poly))
        xs, ys = poly[:, 0], poly[:, 1]
        for i in range(len(poly)):
            j = (i + 1) % len(poly)
            if integer:
                y1, y2, x1, x2 = int(ys[i]), int(ys[j]), xs[i], xs[j]
                if y1 == y2:
                    continue
                if y1 > y2:
                    y1, y2, x1, x2 = y2, y1, x2, x1
                slope = (x2 - x1) / (y2 - y1)
                ex = x1 + 0.5 * slope + 1e-8
            else:
                y1f, y2f, x1f, x2f = ys[i], ys[j], xs[i], xs[j]
                y1, y2 = _jround(y1f), _jround(y2f)
                if y1 == y2 or (y1 <= 0 and y2 <= 0):
                    continue
                if y1 > y2:
                    y1, y2, y1f, y2f, x1f, x2f = y2, y1, y2f, y1f, x2f, x1f
                slope = (x2f - x1f) / (y2f - y1f)
                ex = x1f + (y1 - y1f + 0.5) * slope + 1e-8
            start = y1
            if y1 < 0:  # PolygonFiller.shiftXValuesAndActivate
                ex += slope * (0 - y1)
                start = 0
            stop = min(y2, h)  # active on rows y1 <= y < y2
            if stop <= start:
                continue
            steps = np.full(stop - start, slope)
            steps[0] = ex
            exs = np.add.accumulate(steps)  # sequential, as ex += slope row by row
            k = np.clip(np.floor(exs + 0.5), 0, w).astype(int)  # pixels c < k are left of the edge
            np.add.at(cnt, (np.arange(start, stop), k), 1)
    below = np.cumsum(cnt, 1)[:, :w]  # crossings with k <= c, i.e. not to the right of pixel c
    return ((cnt.sum(1, keepdims=True) - below) % 2).astype(bool)


def roi_zip_to_mask(path, w, h):
    """Union of the masks of every area ROI in the zip, as a (h, w) bool array."""
    mask = np.zeros((h, w), bool)
    for entry, kind, name, outlines in read_roi_zip(path):
        if outlines is None:
            warnings.warn(f'{entry}: {kind} ROI has no area, skipped')
            continue
        mask |= fill(outlines, w, h)
    return mask
