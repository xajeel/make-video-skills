"""Put bold, readable thumbnail text on a text-free Flow image -> 1280x720 JPEG.

Flow (nano2) misspells text, so the picture is generated WITHOUT text and the words are added here.

  python3 thumbnail.py base.jpg out.jpg \
      --text "LEGEND|318|92|118|cream" --text "REALITY|965|92|118|red"
  python3 thumbnail.py base.jpg out.jpg --darken left \
      --text "WAS HE|40|250|130|cream|lm" --text "REAL?|40|400|175|red|lm"

--text "WORDS|x|y|size|color[|anchor]"  (1280x720 coordinates; anchor is a Pillow anchor, default mm = centre)
colors: cream, red, gold, white, or #rrggbb.  --darken left|right|top|bottom adds a soft dark gradient behind text.
Rules: 2-3 words total, huge, high contrast; keep the bottom-right corner clear (YouTube draws the duration there).
"""
import argparse
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT = "/usr/share/fonts/truetype/noto/NotoSans-CondensedBlack.ttf"
COLORS = {"cream": (250, 236, 200), "red": (235, 70, 50), "gold": (245, 190, 60), "white": (255, 255, 255)}
W, H = 1280, 720

def color(c):
    if c.startswith("#"): return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) + (255,)
    return COLORS[c] + (255,)

def darken(im, side, depth=560, strength=150):
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    n = depth if side in ("left", "right") else depth * H // W
    for i in range(n):
        a = int(strength * (1 - i / n))
        if side == "left": d.line([(i, 0), (i, H)], fill=(0, 0, 0, a))
        elif side == "right": d.line([(W - 1 - i, 0), (W - 1 - i, H)], fill=(0, 0, 0, a))
        elif side == "top": d.line([(0, i), (W, i)], fill=(0, 0, 0, a))
        else: d.line([(0, H - 1 - i), (W, H - 1 - i)], fill=(0, 0, 0, a))
    im.alpha_composite(ov)

def label(im, s, x, y, size, fill, anchor="mm"):
    f = ImageFont.truetype(FONT, size); stroke = max(6, size // 12)
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))   # soft drop shadow
    ImageDraw.Draw(sh).text((x + 6, y + 8), s, font=f, fill=(0, 0, 0, 200), anchor=anchor, stroke_width=stroke, stroke_fill=(0, 0, 0, 200))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
    ImageDraw.Draw(im).text((x, y), s, font=f, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=(15, 12, 10, 255))

ap = argparse.ArgumentParser()
ap.add_argument("base"); ap.add_argument("out")
ap.add_argument("--text", action="append", default=[]); ap.add_argument("--darken", choices=["left", "right", "top", "bottom"])
a = ap.parse_args()
im = Image.open(a.base).convert("RGBA").resize((W, H), Image.LANCZOS)
if a.darken: darken(im, a.darken)
for t in a.text:
    p = t.split("|")
    label(im, p[0], int(p[1]), int(p[2]), int(p[3]), color(p[4]), p[5] if len(p) > 5 else "mm")
im.convert("RGB").save(a.out, quality=92)
print(a.out)
