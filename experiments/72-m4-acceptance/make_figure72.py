"""timeline-54.png: every photo of the #72 session, tag 49 read or not, and the other 11 trays as planned or not.
Made from photos72.csv (analyse72.py). Shape and word as well as colour: a circle is read, a cross is not read."""
import csv
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

rows = list(csv.DictReader(open("photos72.csv")))
F = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
f = lambda n, b=False: ImageFont.truetype(FB if b else F, n)
W, H = 1600, 1300
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)
GREEN, RED, GREY, INK = (20, 110, 60), (190, 30, 30), (120, 120, 120), (0, 0, 0)


def minutes(s, day="2026-11-27"):
    t = s[11:19] if len(s) > 8 else s
    h, m, sec = map(int, t.split(":"))
    return h * 60 + m + sec / 60


def panel(y0, t0, t1, title, bars, notes, vlines=()):
    L, R = 230, 40
    x = lambda t: L + (minutes(t) - minutes(t0)) / (minutes(t1) - minutes(t0)) * (W - L - R)
    d.text((20, y0), title, font=f(26, True), fill=INK)
    # axis
    ya = y0 + 490
    d.line([L, ya, W - R, ya], fill=INK, width=2)
    step = 5
    m = int(minutes(t0) // step * step)
    while m <= minutes(t1):
        if m >= minutes(t0):
            xx = L + (m - minutes(t0)) / (minutes(t1) - minutes(t0)) * (W - L - R)
            d.line([xx, ya, xx, ya + 8], fill=INK, width=2)
            d.text((xx - 24, ya + 12), f"{m // 60:02d}:{m % 60:02d}", font=f(20), fill=INK)
        m += step
    d.text((L, ya + 42), "UTC, 27 November 2026 (chamber time is one hour later)", font=f(18), fill=GREY)
    # bars with labels
    for i, (a, b, label) in enumerate(bars):
        xa, xb = x(a), x(b)
        d.rectangle([xa, y0 + 60 + (i % 3) * 0, max(xb, xa + 4), y0 + 84], fill=(215, 215, 215), outline=GREY)
        d.text((xa, y0 + 36 - 0 + 0), "", font=f(16), fill=INK)
    for (a, label, lvl) in notes:
        xx = x(a)
        d.line([xx, y0 + 88, xx, y0 + 104 + lvl * 24], fill=GREY, width=1)
        d.text((xx + 4, y0 + 96 + lvl * 24), label, font=f(18), fill=INK)
    for v, label in vlines:
        xx = x(v)
        for yy in range(y0 + 240, ya, 12):
            d.line([xx, yy, xx, yy + 6], fill=INK, width=2)
        d.text((xx + 6, ya - 26), label, font=f(18, True), fill=INK)
    # rows
    ry = {"tag": y0 + 300, "others": y0 + 410}
    d.text((20, ry["tag"] - 18), "Tag 49", font=f(22, True), fill=INK)
    d.text((20, ry["tag"] + 8), "covered tray", font=f(18), fill=GREY)
    d.text((20, ry["others"] - 26), "Other 11 trays", font=f(22, True), fill=INK)
    d.text((20, ry["others"] + 0), "all as planned", font=f(18), fill=GREY)
    bins = {}
    for r in rows:
        if r["state"].startswith(("before the spares", "spares being removed")):
            continue
        tm = r["time_utc"][11:19]
        if not (minutes(t0) <= minutes(tm) < minutes(t1)):
            continue
        k = int(minutes(tm))
        n = bins.get(k, 0)
        bins[k] = n + 1
        xx = x(tm) + n * 0
        yy = ry["tag"] - n * 0
        off = n * 15
        for key, ok in (("tag", r["tag49"] == "read"), ("others", r["other_trays_as_planned"] == "yes")):
            cx, cy = xx, ry[key] + off - 15
            if ok:
                d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=GREEN)
            else:
                d.line([cx - 6, cy - 6, cx + 6, cy + 6], fill=RED, width=3)
                d.line([cx - 6, cy + 6, cx + 6, cy - 6], fill=RED, width=3)
    return x


P1 = ("08:55:00", "09:21:00")
panel(20, *P1, "1. Layout, swap and the first covers (08:55 to 09:21)",
      bars=[("09:01:40", "09:06:30", ""), ("09:07:30", "09:07:50", ""), ("09:08:30", "09:08:55", ""), ("09:10:00", "09:10:15", ""),
            ("09:10:45", "09:11:20", ""), ("09:12:10", "09:12:30", "")],
      notes=[("09:03:30", "clear plastic", 0), ("09:07:40", "9.3%", 1), ("09:08:40", "27.7%", 2), ("09:10:05", "59.1%", 3),
             ("09:11:00", "99.5%", 4), ("09:12:20", "9.3%, edge", 5)],
      vlines=[("09:01:18", "swap")])
panel(640, "09:14:00", "10:30:00", "2. No cover for an hour, the small pieces, put-back (09:14 to 10:30)",
      bars=[("09:13:00", "10:18:30", ""), ("10:18:50", "10:19:20", ""), ("10:19:40", "10:20:10", ""), ("10:20:30", "10:21:30", "")],
      notes=[("09:50:00", "no cover on tag 49 (13 scheduled photos)", 0), ("10:19:05", "1.5%", 1), ("10:19:55", "3.1%", 2), ("10:21:00", "5.7%", 3)])
# legend
d.ellipse([240, 1230, 252, 1242], fill=GREEN)
d.text((262, 1226), "read / as planned", font=f(20), fill=INK)
d.line([500, 1230, 512, 1242], fill=RED, width=3)
d.line([500, 1242, 512, 1230], fill=RED, width=3)
d.text((522, 1226), "not read / not as planned", font=f(20), fill=INK)
d.text((240, 1262), "Photos in one minute stack downwards. Grey bar: something on tag 49. The photo at 10:26, during put-back, is left out.", font=f(18), fill=GREY)
img.save("timeline-54.png")
