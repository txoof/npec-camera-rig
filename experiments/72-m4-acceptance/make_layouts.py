"""Draws layout-1.png and layout-2.png from the layouts in m4.py (so the pictures cannot disagree with the checker)."""
from PIL import Image, ImageDraw, ImageFont
import m4
IDS = dict(zip("ABCDEF", m4.parse_spares(None)))

F = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
font = lambda n, b=False: ImageFont.truetype(FB if b else F, n)
CW, CH, X0, Y0 = 215, 270, 110, 150

def draw(layout, title, note, out, swapped=()):
    img = Image.new("RGB", (X0 + 6 * CW + 40, Y0 + 2 * CH + 130), "white")
    d = ImageDraw.Draw(img)
    d.text((20, 14), title, fill="black", font=font(30, True))
    d.text((20, 54), note, fill=(60, 60, 60), font=font(20))
    for i, (name, a, b) in enumerate((("NW", 0, 2), ("NM", 2, 4), ("NE", 4, 6))):
        d.rectangle([X0 + a * CW + 4, 92, X0 + b * CW - 4, 128], outline=(90, 90, 90), width=2)
        d.text((X0 + (a + b) / 2 * CW - 14, 96), name, fill=(60, 60, 60), font=font(24, True))
    for r, row in enumerate("NS"):
        d.text((24, Y0 + r * CH + CH / 2 - 22), f"{row} row", fill=(60, 60, 60), font=font(26, True))
        for n in range(1, 7):
            slot = f"{row}{n}"
            name, rot = layout[slot]
            x, y = X0 + (n - 1) * CW, Y0 + r * CH
            fixed = name.startswith("X")
            fill = (200, 215, 235) if fixed else (252, 226, 180)
            hot = slot in swapped
            d.rectangle([x + 6, y + 6, x + CW - 6, y + CH - 6], fill=fill, outline=(200, 30, 30) if hot else (40, 40, 40), width=6 if hot else 2)
            tag = 70
            tx = x + 12 if rot == 0 else x + CW - 12 - tag          # A1 at the west (rot 0) or east (rot 180) ...
            ty = y + CH - 12 - tag if rot == 0 else y + 12          # ... and south or north
            d.rectangle([tx, ty, tx + tag, ty + tag], fill="white", outline="black", width=3)
            d.text((tx + 14, ty + 20), "A1", fill="black", font=font(24, True))
            label = f"Tray {name[1:]}" if fixed else f"Spare {name} ({IDS[name]})"
            d.text((x + 16, y + (CH / 2 - 40 if rot == 0 else CH / 2 - 10)), label, fill="black", font=font(26, True))
            d.text((x + 16, y + (CH / 2 - 8 if rot == 0 else CH / 2 + 22)), "experiment 4" if fixed else f"tag {IDS[name]}", fill=(70, 70, 70), font=font(20))
            d.text((x + 16, y + (CH / 2 + 24 if rot == 0 else CH / 2 - 42)), f"{rot} deg", fill=(70, 70, 70), font=font(22))
            d.text((x + CW - 52, y + CH - 40 if rot == 180 else y + 10), slot, fill=(90, 90, 90), font=font(20))
    d.text((20, Y0 + 2 * CH + 20), "North is the top of the photo. West is the left. White square = where cell A1 (and the tag) sits: south-west corner at 0 deg, north-east corner at 180 deg.",
           fill=(60, 60, 60), font=font(18))
    d.text((20, Y0 + 2 * CH + 48), "Blue = experiment 4's trays (leave their tags alone). Orange = spare trays. Trays touch side by side; keep every tray off the four corner tags.",
           fill=(60, 60, 60), font=font(18))
    img.save(out)

draw(m4.LAYOUT_1, "Layout 1: the start (12 trays)", "Experiment 4's trays barely move: each stays in the same table location.", "layout-1.png")
draw(m4.LAYOUT_2, "Layout 2: after the swap (E and F trade places, each turned 180 deg)", "Only E and F move. Everything else stays exactly where it is for the next hour.", "layout-2.png", swapped=("S3", "S6"))
