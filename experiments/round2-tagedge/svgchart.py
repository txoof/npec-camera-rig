"""Small SVG charts (no matplotlib on the Pi) and PNG output through headless Chromium."""

import subprocess
import tempfile
from html import escape
from pathlib import Path

INK, MUTED, GRID = "#1f1f1d", "#6b6a64", "#e4e3dd"
# Categorical order of the dataviz reference palette, light mode.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#e87ba4", "#eda100", "#6250d6"]
MARKERS = ["circle", "square", "triangle", "diamond", "circle", "square"]


def _ticks(lo, hi, n=5):
    import math

    span = hi - lo or 1.0
    step = 10 ** math.floor(math.log10(span / n))
    for m in (1, 2, 5, 10):
        if span / (step * m) <= n:
            step *= m
            break
    first = math.ceil(lo / step) * step
    return [round(first + i * step, 10) for i in range(int((hi - first) / step) + 1)]


def _marker(kind, x, y, colour, size=4.5):
    if kind == "square":
        return f'<rect x="{x - size:.1f}" y="{y - size:.1f}" width="{2 * size}" height="{2 * size}" fill="{colour}" stroke="white" stroke-width="1"/>'
    if kind == "triangle":
        return f'<path d="M{x:.1f},{y - size - 1:.1f} L{x + size + 1:.1f},{y + size:.1f} L{x - size - 1:.1f},{y + size:.1f} Z" fill="{colour}" stroke="white" stroke-width="1"/>'
    if kind == "diamond":
        return f'<path d="M{x:.1f},{y - size - 1:.1f} L{x + size + 1:.1f},{y:.1f} L{x:.1f},{y + size + 1:.1f} L{x - size - 1:.1f},{y:.1f} Z" fill="{colour}" stroke="white" stroke-width="1"/>'
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{size}" fill="{colour}" stroke="white" stroke-width="1"/>'


def panel(series, *, title, xlabel, ylabel, width=560, height=380, xlim=None, ylim=None, hlines=(), vlines=(), xticks=None):
    """One chart as an SVG string. series: [{label, points: [(x, y)], line: bool, dash: str}], in
    fixed palette order. hlines/vlines: [(value, label)] drawn as thin grey references."""
    left, right, bottom = 70, 20, 52
    top = 40 + 18 * len(series)
    xs = [p[0] for s in series for p in s["points"]] + [v for v, _ in vlines]
    ys = [p[1] for s in series for p in s["points"]] + [v for v, _ in hlines]
    x0, x1 = xlim or (min(xs), max(xs))
    y0, y1 = ylim or (min(ys), max(ys))
    if not xlim:
        pad = (x1 - x0) * 0.04 or 1
        x0, x1 = x0 - pad, x1 + pad
    if not ylim:
        pad = (y1 - y0) * 0.06 or 0.01
        y0, y1 = y0 - pad, y1 + pad
    pw, ph = width - left - right, height - top - bottom
    sx = lambda x: left + (x - x0) / (x1 - x0) * pw  # noqa: E731
    sy = lambda y: top + (1 - (y - y0) / (y1 - y0)) * ph  # noqa: E731
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="DejaVu Sans, sans-serif" font-size="12">',
           f'<rect width="{width}" height="{height}" fill="white"/>',
           f'<text x="{left}" y="22" font-size="14" font-weight="bold" fill="{INK}">{escape(title)}</text>']
    for t in _ticks(y0, y1):
        out.append(f'<line x1="{left}" x2="{left + pw}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" stroke="{GRID}"/>')
        out.append(f'<text x="{left - 6}" y="{sy(t) + 4:.1f}" text-anchor="end" fill="{MUTED}">{t:g}</text>')
    if xticks:
        for v, lab in xticks:
            out.append(f'<text x="{sx(v):.1f}" y="{top + ph + 16}" text-anchor="middle" fill="{MUTED}">{escape(lab)}</text>')
    else:
        for t in _ticks(x0, x1, 6):
            out.append(f'<text x="{sx(t):.1f}" y="{top + ph + 16}" text-anchor="middle" fill="{MUTED}">{t:g}</text>')
    out.append(f'<line x1="{left}" x2="{left + pw}" y1="{top + ph}" y2="{top + ph}" stroke="{MUTED}"/>')
    for v, lab in hlines:
        out.append(f'<line x1="{left}" x2="{left + pw}" y1="{sy(v):.1f}" y2="{sy(v):.1f}" stroke="{MUTED}" stroke-dasharray="5,4"/>')
        out.append(f'<text x="{left + pw - 4}" y="{sy(v) - 5:.1f}" text-anchor="end" fill="{MUTED}">{escape(lab)}</text>')
    for j, (v, lab) in enumerate(vlines):
        out.append(f'<line x1="{sx(v):.1f}" x2="{sx(v):.1f}" y1="{top}" y2="{top + ph}" stroke="{MUTED}" stroke-dasharray="5,4"/>')
        out.append(f'<text x="{sx(v) + 4:.1f}" y="{top + ph - 8 - 16 * j}" fill="{MUTED}">{escape(lab)}</text>')
    for i, s in enumerate(series):
        colour = s.get("colour", SERIES[i])
        pts = [(sx(x), sy(y)) for x, y in s["points"]]
        if s.get("line"):
            d = " ".join(f"{'M' if j == 0 else 'L'}{x:.1f},{y:.1f}" for j, (x, y) in enumerate(pts))
            dash = f' stroke-dasharray="{s["dash"]}"' if s.get("dash") else ""
            out.append(f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="2"{dash}/>')
        else:
            out += [_marker(s.get("marker", MARKERS[i]), x, y, colour) for x, y in pts]
    # Legend, top right inside the plot, one row per series.
    for i, s in enumerate(series):
        colour = s.get("colour", SERIES[i])
        ly = 44 + i * 18
        lx = left + 8
        out.append(_marker(s.get("marker", MARKERS[i]), lx, ly - 4, colour) if not s.get("line")
                   else f'<line x1="{lx - 8}" x2="{lx + 8}" y1="{ly - 4}" y2="{ly - 4}" stroke="{colour}" stroke-width="2"/>')
        out.append(f'<text x="{lx + 14}" y="{ly}" fill="{INK}">{escape(s["label"])}</text>')
    out.append(f'<text x="{left + pw / 2}" y="{height - 12}" text-anchor="middle" fill="{INK}">{escape(xlabel)}</text>')
    out.append(f'<text transform="translate(16,{top + ph / 2}) rotate(-90)" text-anchor="middle" fill="{INK}">{escape(ylabel)}</text>')
    out.append("</svg>")
    return "\n".join(out)


def to_png(panels, out_png, *, columns=2, heading=""):
    """Panels (SVG strings) in a grid, rendered to PNG with headless Chromium."""
    html = ['<html><body style="margin:0;background:white;font-family:DejaVu Sans, sans-serif">']
    if heading:
        html.append(f'<div style="padding:10px 16px;font-size:16px;font-weight:bold">{escape(heading)}</div>')
    html.append(f'<div style="display:grid;grid-template-columns:repeat({columns}, max-content);gap:4px">')
    html += [f"<div>{p}</div>" for p in panels]
    html.append("</div></body></html>")
    widths = [int(p.split('width="')[1].split('"')[0]) for p in panels[:columns]]
    heights = [int(p.split('height="')[1].split('"')[0]) for p in panels]
    rows = -(-len(panels) // columns)
    width = sum(widths) + 4 * (columns - 1)
    height = max(heights) * rows + 4 * (rows - 1) + (40 if heading else 0)
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "chart.html"
        page.write_text("\n".join(html))
        subprocess.run(["/usr/lib/chromium/chromium", "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                        f"--screenshot={Path(out_png).resolve()}", f"--window-size={width},{height}", page.as_uri()],
                       check=True, capture_output=True, timeout=120)
