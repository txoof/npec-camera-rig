"""#402, metrology log 33: per-pixel features for the random forest (the ilastik standard set).

features(rgb, sigmas) -> (h, w, n) float32 array and the list of feature names.

Colour channels (10): R, G, B (0 to 255), greenness (2G-R-B)/(R+G+B), HSV (skimage, 0 to 1; hue is
not unwrapped), CIE L*a*b* (skimage rgb2lab, sRGB D65).
  - each colour channel smoothed with a Gaussian at every sigma                  10 per sigma
  - on L*, a* and greenness only, at every sigma: gradient magnitude of Gaussian,
    Laplacian of Gaussian, structure tensor eigenvalues (inner scale sigma, outer
    scale sigma / 2, as ilastik), Hessian of Gaussian eigenvalues                6 x 3 per sigma
Borders: mirror (scipy 'reflect'). No unsmoothed raw channel is included (sigma 0.7 is the finest).
"""
import numpy as np
from scipy import ndimage as ndi
from skimage.color import rgb2hsv, rgb2lab

COLOUR = ['R', 'G', 'B', 'greenness', 'H', 'S', 'V', 'L', 'a', 'b']
EDGE_CHANNELS = ['L', 'a', 'greenness']
EDGE = ['gradmag', 'LoG', 'st_ev1', 'st_ev2', 'hess_ev1', 'hess_ev2']
SIGMAS_ALL = (0.7, 1.0, 2.0, 4.0, 8.0)
SIGMAS_NO8 = (0.7, 1.0, 2.0, 4.0)
MODE = 'reflect'


def colour_channels(rgb):
    rgb = np.asarray(rgb)
    f = rgb.astype(np.float32)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    exg = (2 * g - r - b) / (r + g + b + 1e-6)
    u = f / 255.0
    hsv = rgb2hsv(u).astype(np.float32)
    lab = rgb2lab(u).astype(np.float32)
    return {'R': r, 'G': g, 'B': b, 'greenness': exg.astype(np.float32),
            'H': hsv[..., 0], 'S': hsv[..., 1], 'V': hsv[..., 2],
            'L': lab[..., 0], 'a': lab[..., 1], 'b': lab[..., 2]}


def _eig2(a, b, c):
    """Eigenvalues of [[a, b], [b, c]], larger first."""
    m = (a + c) / 2
    d = np.sqrt(((a - c) / 2) ** 2 + b * b)
    return m + d, m - d


def names(sigmas):
    out = []
    for s in sigmas:
        out += [f'{c}_s{s:g}' for c in COLOUR]
        out += [f'{c}_{e}_s{s:g}' for c in EDGE_CHANNELS for e in EDGE]
    return out


def features(rgb, sigmas=SIGMAS_ALL):
    ch = colour_channels(rgb)
    h, w = ch['R'].shape
    nm = names(sigmas)
    out = np.empty((h, w, len(nm)), np.float32)
    k = 0
    for s in sigmas:
        for c in COLOUR:
            out[..., k] = ndi.gaussian_filter(ch[c], s, mode=MODE); k += 1
        for c in EDGE_CHANNELS:
            x = ch[c]
            gy = ndi.gaussian_filter(x, s, order=(1, 0), mode=MODE)
            gx = ndi.gaussian_filter(x, s, order=(0, 1), mode=MODE)
            out[..., k] = np.hypot(gx, gy); k += 1
            out[..., k] = ndi.gaussian_laplace(x, s, mode=MODE); k += 1
            so = s / 2
            e1, e2 = _eig2(ndi.gaussian_filter(gx * gx, so, mode=MODE),
                           ndi.gaussian_filter(gx * gy, so, mode=MODE),
                           ndi.gaussian_filter(gy * gy, so, mode=MODE))
            out[..., k] = e1; out[..., k + 1] = e2; k += 2
            hyy = ndi.gaussian_filter(x, s, order=(2, 0), mode=MODE)
            hxx = ndi.gaussian_filter(x, s, order=(0, 2), mode=MODE)
            hxy = ndi.gaussian_filter(x, s, order=(1, 1), mode=MODE)
            e1, e2 = _eig2(hxx, hxy, hyy)
            out[..., k] = e1; out[..., k + 1] = e2; k += 2
    assert k == len(nm)
    return out, nm


def column_index(all_names, sigmas):
    """Columns of a SIGMAS_ALL feature array that make up the feature set of `sigmas`."""
    want = names(sigmas)
    pos = {n: i for i, n in enumerate(all_names)}
    return np.array([pos[n] for n in want]), want
