"""Build one ~2-minute part (or a whole short video).

Usage:
  python3 assemble.py <part_dir> --draft            # quick 720p review render, no Flow clips needed
  python3 assemble.py <part_dir> [--out partNN.mp4] # final 1080p render
Expects in <part_dir>: scenes.json, timing.json, voiceover.mp3, images/sceneNN.jpg,
and clips/sceneNN.mp4 for the scenes animated in Flow (final render).

VARIETY (monetisation rule, 2026-11-26): no two parts should look machine-made from one template.
Every scene in scenes.json may set (all optional):
  "animate": true                 -> a Flow clip (clips/sceneNN.mp4) is used for this scene
  "shot": "zoom_in" | "zoom_out" | "pan_left" | "pan_right" | "pan_up" | "pan_down" | "push" | "hold"
          default: alternate zoom_in / zoom_out (~3%)
  "focus": [x, y]                 -> 0-1 point a "push" moves into (a detail), default centre
  "transition": "dissolve" (0.5 s, default) | "cut" | "slow" (1.0 s)   - transition INTO this scene
  "overlay": {"type": "quote",   "text": "...", "cite": "A Gest of Robyn Hode, c.1500"}
             {"type": "caption", "text": "SANTA CLARA, 1993"}              (place / date)
             {"type": "route",   "points": [[x, y], ...]}                   (rust thread stitches itself
                                                                             along the path; stills only)
  "marks": [ ... ]                -> hand-made B-roll style annotations, stitched in thread (stills only):
             {"type": "circle", "at": [x, y], "r": 0.07, "word": "graveyard"}
             {"type": "arrow",  "from": [x, y], "to": [x, y], "word": "President"}
             {"type": "label",  "text": "Jensen Huang", "at": [x, y], "tag": [x, y], "from": [x, y], "word": "Jensen"}
                 -> a cream name tag pops up at "tag" with a short stitched arrow down to "at" (a head)
             {"type": "card",   "text": "Why couldn't Nvidia let him go?", "word": "why"}
                 -> the frame dims and the line comes up big and centred (fixed on screen, not on the image)
             optional "color": "rust" (default) | "ochre" | "cream"; "t": seconds into the scene
             instead of "word". "word" = the mark stitches itself on as the narrator says that word
             (first match inside the scene, from words.json). Circles wobble and overshoot like a
             hand-drawn loop; arrows curve. Coordinates 0-1 of the image; r is a fraction of width.
             Keep them RARE and natural: 1-2 per part at most, on the strongest beat only (user rule).
  "chart": {"title": "NVIDIA MARKET VALUE", "points": [[2016, 57], [2018, 81], ...], "xticks": [2016, 2018, ...],
            "yticks": [[0, "$0"], [500, "$500B"], [1000, "$1T"]], "ymax": 1100, "note": "approximate",
            "milestones": [{"at": [2023.4, 1000], "text": "$1 TRILLION", "word": "trillion"}]}
                                  -> replaces the image with a plain linen cloth and a stitched line chart: axes and
                                     labels in the caption serif, the rust line stitches itself on until the first
                                     milestone word, then each milestone pops a dot + tag on its word. Use real data.
Overlays are drawn in the tapestry palette (cream text, rust/ochre accents, soft dark shade).

- Animated scenes: the Flow clip, speed-fitted to that scene's narration.
- Every part gets the SAME edges so parts join smoothly later (join_parts.py):
  LEAD s of picture before the first word, TAIL s of quiet picture after the last word.
- Voiceover is loudness-normalised (-16 LUFS) to 48 kHz stereo so every part sounds the same.
"""
import argparse, json, subprocess, pathlib, textwrap

ZOOM = 0.03   # zoom change for zoom_in / zoom_out (0.03 = 3%)
PAN = 0.06    # pans travel across a frame cropped 6% tighter
PUSH = 0.12   # push into a detail: 12%
LEAD = 0.4    # seconds before the first word
TAIL = 1.2    # seconds of quiet picture after the last word (join_parts crossfades inside this)
XF = {"dissolve": 0.5, "slow": 1.0, "cut": 0.04}
FPS = 30
CREAM, RUST, OCHRE, INK = (238, 228, 205), (158, 52, 34), (200, 150, 70), (22, 18, 14)
FONT_DIR = "/usr/share/fonts/truetype/noto/"

ap = argparse.ArgumentParser()
ap.add_argument("part_dir")
ap.add_argument("--draft", action="store_true", help="fast 720p review render; ignores missing clips")
ap.add_argument("--out")
a = ap.parse_args()
d = pathlib.Path(a.part_dir).resolve()
W, H = (1280, 720) if a.draft else (1920, 1080)
out_name = a.out or ("draft.mp4" if a.draft else f"{d.name}.mp4")
preset, crf = ("veryfast", 23) if a.draft else ("medium", 19)

from PIL import Image, ImageDraw, ImageFont, ImageFilter

scenes = json.load(open(d / "scenes.json"))["scenes"]
t = json.load(open(d / "timing.json"))
durs = list(t["durs"]); N = len(durs)
assert len(scenes) == N, f"scenes.json has {len(scenes)} scenes but timing.json has {N}"
durs[0] += LEAD; durs[-1] += TAIL
xin = [XF.get(s.get("transition", "dissolve"), 0.5) for s in scenes]   # transition INTO scene i
seg = d / ("seg_draft" if a.draft else "seg"); seg.mkdir(exist_ok=True)

def font(name, size):
    for f in (name, "NotoSerif-Regular.ttf", "NotoSans-Regular.ttf"):
        try: return ImageFont.truetype(FONT_DIR + f, size)
        except OSError: pass
    return ImageFont.load_default()

def overlay_png(ov):
    """Static RGBA layer for quote / caption overlays, or None."""
    if not ov or ov.get("type") not in ("quote", "caption"): return None
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); s = W / 1920
    if ov["type"] == "quote":
        shade = Image.new("L", (W, H), 0); g = ImageDraw.Draw(shade)
        for y in range(int(H * 0.52), H):                      # soft dark shade over the lower part
            g.line([(0, y), (W, y)], fill=int(190 * max(0.0, (y - H * 0.52) / (H * 0.48)) ** 0.8))
        layer.paste((*INK, 255), (0, 0), shade)
        dr = ImageDraw.Draw(layer)
        fq, fc = font("NotoSerif-Italic.ttf", int(64 * s)), font("NotoSerif-Regular.ttf", int(40 * s))
        lines = textwrap.wrap(f"“{ov['text']}”", 46)
        y = H - int(110 * s) - len(lines) * int(80 * s)
        for ln in lines:
            dr.text((W / 2, y), ln, font=fq, fill=(*CREAM, 255), anchor="mt", stroke_width=max(2, int(3 * s)), stroke_fill=(*INK, 255))
            y += int(80 * s)
        if ov.get("cite"):
            dr.text((W / 2, y + int(14 * s)), "— " + ov["cite"], font=fc, fill=(*OCHRE, 255), anchor="mt",
                    stroke_width=max(2, int(2 * s)), stroke_fill=(*INK, 255))
    else:
        dr = ImageDraw.Draw(layer); f = font("NotoSerif-SemiBold.ttf", int(52 * s))
        x, y = int(70 * s), int(60 * s)
        box = dr.textbbox((x, y), ov["text"], font=f)
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rectangle([box[0] - 24 * s, box[1] - 16 * s, box[2] + 24 * s, box[3] + 18 * s], fill=(*INK, 150))
        layer = Image.alpha_composite(layer, sh.filter(ImageFilter.GaussianBlur(10 * s))); dr = ImageDraw.Draw(layer)
        dr.text((x, y), ov["text"], font=f, fill=(*CREAM, 255), stroke_width=max(2, int(2 * s)), stroke_fill=(*INK, 255))
        dr.line([(x, box[3] + 10 * s), (box[2], box[3] + 10 * s)], fill=(*RUST, 255), width=max(3, int(5 * s)))
    return layer

def stitch(img, P, frac, color=RUST, w=None, st=None, gap=None):
    """Thread stitched along pixel polyline P up to fraction frac of its length, as running-stitch dashes
    (shadow + wool + a lighter twist highlight). Returns the walked length."""
    iw = img.size[0]; dr = ImageDraw.Draw(img)
    w = w or max(6, int(iw * 0.010)); st = st or iw * 0.020; gap = gap or iw * 0.010
    hi = tuple(min(255, int(c * 1.35 + 25)) for c in color)
    seglen = [((P[i+1][0]-P[i][0])**2 + (P[i+1][1]-P[i][1])**2) ** 0.5 for i in range(len(P) - 1)]
    total = sum(seglen) or 1; goal = total * frac; walked, pos = 0.0, 0.0   # pos carries across segments
    dashes, cur, guard = [], [], 0
    for i, L in enumerate(seglen):
        if L == 0: continue
        a = 0.0; lim = min(L, goal - walked)                # stop at the end of this segment or at the goal
        while lim - a > 1e-6:                              # tolerance: exact float compare looped forever (OOM)
            guard += 1
            if guard > 200000: raise SystemExit("stitch(): runaway loop")   # never eat the machine's RAM again
            if pos < st - 1e-6:                            # inside a dash
                e = min(a + (st - pos), lim)
                cur.append((P[i][0] + (P[i+1][0]-P[i][0]) * a / L, P[i][1] + (P[i+1][1]-P[i][1]) * a / L))
                cur.append((P[i][0] + (P[i+1][0]-P[i][0]) * e / L, P[i][1] + (P[i+1][1]-P[i][1]) * e / L))
                pos += e - a; a = e
                if pos >= st - 1e-6: dashes.append(cur); cur = []; pos = st
            else:                                          # inside a gap
                e = min(a + (st + gap - pos), lim); pos += e - a; a = e
                if pos >= st + gap - 1e-6: pos = 0.0
        walked += L
        if walked >= goal: break
    if cur: dashes.append(cur)
    for dsh in dashes:
        dr.line([(x + w * 0.3, y + w * 0.45) for x, y in dsh], fill=INK, width=w, joint="curve")   # shadow
    for dsh in dashes:
        dr.line(dsh, fill=color, width=w, joint="curve")
        dr.line([(x - w * 0.18, y - w * 0.18) for x, y in dsh], fill=hi, width=max(1, w // 3), joint="curve")
    return total

def draw_route(img, pts, frac):
    """Rust 'thread' stitched along pts (0-1 coords) up to fraction frac of its length."""
    iw, ih = img.size; P = [(x * iw, y * ih) for x, y in pts]
    stitch(img, P, frac)
    if frac >= 0.999:
        dr = ImageDraw.Draw(img); w = max(6, int(iw * 0.010))
        x, y = P[-1]; r = w * 1.6; dr.ellipse([x - r, y - r, x + r, y + r], fill=RUST, outline=INK, width=2)

COLORS = {"rust": RUST, "ochre": OCHRE, "cream": CREAM}

def mark_paths(m, iw, ih, seed):
    """Pixel polylines for one mark (drawn in order)."""
    import math, random
    rnd = random.Random(seed)
    if m["type"] == "circle":
        cx, cy = m["at"][0] * iw, m["at"][1] * ih; r = m.get("r", 0.07) * iw
        a0 = rnd.uniform(-2.6, -1.6); turn = rnd.uniform(1.08, 1.16); ph = rnd.uniform(0, 6.3)
        ax, ay = rnd.uniform(1.08, 1.2), rnd.uniform(0.9, 1.0)          # a little wider than tall, like a quick loop
        pts = []
        for k in range(97):
            u = k / 96; th = a0 + u * turn * 2 * math.pi
            rr = r * (0.95 + 0.10 * u + 0.035 * math.sin(2 * th + ph))   # spirals outward slightly: overshoot
            pts.append((cx + rr * ax * math.cos(th), cy + rr * ay * math.sin(th)))
        return [pts]
    if m["type"] == "card": return []
    if m["type"] == "label":
        tag = m.get("tag", [m["at"][0], m["at"][1] - 0.09])
        frm, to = m.get("from", [tag[0], tag[1] + 0.03]), m["at"]
    else:
        frm, to = m["from"], m["to"]
    (x0, y0), (x1, y1) = [(p[0] * iw, p[1] * ih) for p in (frm, to)]
    dx, dy = x1 - x0, y1 - y0; L = (dx * dx + dy * dy) ** 0.5 or 1
    bend = rnd.choice((-1, 1)) * rnd.uniform(0.10, 0.18) * L * (0.5 if m["type"] == "label" else 1)
    mx, my = (x0 + x1) / 2 - dy / L * bend, (y0 + y1) / 2 + dx / L * bend
    shaft = [((1-u)**2 * x0 + 2*(1-u)*u * mx + u*u * x1, (1-u)**2 * y0 + 2*(1-u)*u * my + u*u * y1)
             for u in (k / 40 for k in range(41))]
    tx, ty = x1 - shaft[-4][0], y1 - shaft[-4][1]; tl = (tx * tx + ty * ty) ** 0.5 or 1
    tx, ty = tx / tl, ty / tl; hl = max(L * 0.22, iw * (0.022 if m["type"] == "label" else 0.035))
    heads = []
    for s in (1, -1):
        c, sn = math.cos(2.6 * s), math.sin(2.6 * s)                       # ~150 deg back from the tip
        heads.append([(x1, y1), (x1 + hl * (tx * c - ty * sn), y1 + hl * (tx * sn + ty * c))])
    return [shaft] + heads

def draw_marks(img, marks, tsec):
    """Stitch each mark on over ~0.9 s starting at its time m['_t']."""
    iw, ih = img.size
    for j, m in enumerate(marks):
        if m["type"] == "card": continue
        frac = (tsec - m["_t"]) / (0.9 if m["type"] == "circle" else 0.5 if m["type"] == "label" else 0.8)
        if frac <= 0: continue
        if m["type"] == "label": paste_tag(img, m, min(1.0, (tsec - m["_t"]) / 0.3))
        frac = min(1.0, frac); frac = frac * frac * (3 - 2 * frac)
        paths = m["_paths"]; lens = [sum(((p[i+1][0]-p[i][0])**2 + (p[i+1][1]-p[i][1])**2) ** 0.5
                                         for i in range(len(p) - 1)) for p in paths]
        goal = sum(lens) * frac; col = COLORS.get(m.get("color", "rust"), RUST)
        w = max(5, int(iw * 0.0075))
        for p, L in zip(paths, lens):
            if goal <= 0: break
            stitch(img, p, min(1.0, goal / L), col, w=w, st=iw * 0.016, gap=iw * 0.007); goal -= L

def linen_bg(w, h, seed=7):
    """Plain woven linen cloth (no numpy): noise + warp/weft threads, light vignette."""
    import random
    rnd = random.Random(seed)
    v = Image.new("L", (w, h), 128); dv = ImageDraw.Draw(v)
    for x in range(0, w, 3): dv.line([(x, 0), (x, h)], fill=128 + rnd.randint(-22, 22))
    hz = Image.new("L", (w, h), 128); dh = ImageDraw.Draw(hz)
    for y in range(0, h, 3): dh.line([(0, y), (w, y)], fill=128 + rnd.randint(-22, 22))
    tex = Image.blend(Image.blend(v, hz, 0.5), Image.effect_noise((w, h), 26).convert("L"), 0.35).filter(ImageFilter.GaussianBlur(0.7))
    base = (226, 214, 190)
    dark = Image.new("RGB", (w, h), tuple(int(c * 0.86) for c in base))
    light = Image.new("RGB", (w, h), tuple(min(255, int(c * 1.06)) for c in base))
    out = Image.composite(light, dark, tex)
    vig = Image.new("L", (w, h), 0); ImageDraw.Draw(vig).ellipse([-w * 0.25, -h * 0.35, w * 1.25, h * 1.35], fill=255)
    return Image.composite(out, Image.new("RGB", (w, h), tuple(int(c * 0.78) for c in base)), vig.filter(ImageFilter.GaussianBlur(w * 0.08)))

def chart_setup(ch, w=1920, h=1080):
    """Static chart cloth + a mapper from data to pixels + the smooth line polyline (pixels)."""
    img = linen_bg(w, h); dr = ImageDraw.Draw(img)
    L, R, T, B = w * 0.13, w * 0.88, h * 0.24, h * 0.82
    xs = [p[0] for p in ch["points"]] + list(ch.get("xticks", []))
    x0, x1 = min(xs), max(xs); ymax = ch.get("ymax") or max(p[1] for p in ch["points"]) * 1.1
    M = lambda x, y: (L + (x - x0) / (x1 - x0) * (R - L), B - y / ymax * (B - T))
    ft, fl, fn = font("NotoSerif-SemiBold.ttf", int(h * 0.062)), font("NotoSerif-Regular.ttf", int(h * 0.032)), font("NotoSerif-Italic.ttf", int(h * 0.024))
    INKS, MUTE = (52, 40, 30), (150, 132, 108)
    dr.text((w * 0.07, h * 0.07), ch.get("title", ""), font=ft, fill=INKS)
    tb = dr.textbbox((w * 0.07, h * 0.07), ch.get("title", ""), font=ft)
    stitch(img, [(tb[0], tb[3] + h * 0.018), (tb[2], tb[3] + h * 0.018)], 1.0, RUST, w=max(4, int(w * 0.004)), st=w * 0.012, gap=w * 0.005)
    for yv, lab in ch.get("yticks", []):
        _, yy = M(x0, yv)
        if yv: stitch(img, [(L, yy), (R, yy)], 1.0, MUTE, w=max(2, int(w * 0.0016)), st=w * 0.008, gap=w * 0.008)
        dr.text((L - w * 0.015, yy), lab, font=fl, fill=INKS, anchor="rm")
    for xv in ch.get("xticks", []):
        xx, _ = M(xv, 0); dr.text((xx, B + h * 0.025), str(xv), font=fl, fill=INKS, anchor="mt")
        stitch(img, [(xx, B), (xx, B + h * 0.012)], 1.0, INKS, w=max(3, int(w * 0.002)), st=w * 0.02, gap=1)
    stitch(img, [(L, T - h * 0.03), (L, B), (R + w * 0.02, B)], 1.0, INKS, w=max(4, int(w * 0.003)), st=w * 0.014, gap=w * 0.004)
    if ch.get("note"): dr.text((R + w * 0.02, h * 0.93), ch["note"], font=fn, fill=MUTE, anchor="rm")
    P = [M(*p) for p in ch["points"]]; line = []
    for i in range(len(P) - 1):                       # Catmull-Rom: a smooth hand-stitched curve through the data
        p0, p1, p2, p3 = P[max(i - 1, 0)], P[i], P[i + 1], P[min(i + 2, len(P) - 1)]
        for k in range(16):
            t_ = k / 16
            line.append(tuple(0.5 * (2 * p1[j] + (-p0[j] + p2[j]) * t_ + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t_ ** 2
                                     + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t_ ** 3) for j in (0, 1)))
    line.append(P[-1])
    return img, M, line

def tag_png(m, iw, ih):
    """Cream serif name tag on a soft dark plate (tapestry caption style), RGBA, plus its top-left in px."""
    f = font("NotoSerif-SemiBold.ttf", max(14, int(iw * 0.024)))
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    b = tmp.textbbox((0, 0), m["text"], font=f); tw_, th_ = b[2] - b[0], b[3] - b[1]
    px, py = int(iw * 0.012), int(iw * 0.008); bw, bh = tw_ + 2 * px, th_ + 2 * py
    im = Image.new("RGBA", (bw + 24, bh + 24), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([12, 12, 12 + bw, 12 + bh], radius=bh // 3, fill=(*INK, 175))
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(4)))
    dr = ImageDraw.Draw(im)
    dr.text((12 + px - b[0], 12 + py - b[1]), m["text"], font=f, fill=(*CREAM, 255), stroke_width=2, stroke_fill=(*INK, 255))
    dr.line([(12 + px, 12 + bh - 4), (12 + bw - px, 12 + bh - 4)], fill=(*RUST, 255), width=max(2, int(iw * 0.002)))
    tag = m.get("tag", [m["at"][0], m["at"][1] - 0.09])
    return im, (int(tag[0] * iw - im.size[0] / 2), int(tag[1] * ih - im.size[1] / 2))

def paste_tag(img, m, k):
    if k <= 0: return
    if "_tag" not in m: m["_tag"] = tag_png(m, *img.size)
    im, (x, y) = m["_tag"]; k = min(1.0, k)
    al = im.split()[3].point(lambda v: int(v * k))
    img.paste(im.convert("RGB"), (x, y + int((1 - k) * 8)), al)

def card_layer(m):
    """Frame-space layer for a "card" mark: dims the picture and shows one big centred line."""
    lay = Image.new("RGBA", (W, H), (*INK, 140)); dr = ImageDraw.Draw(lay); s = W / 1920
    f = font("NotoSerif-SemiBold.ttf", int(84 * s))
    lines = textwrap.wrap(m["text"], 36); lh = int(110 * s); y = H / 2 - len(lines) * lh / 2
    for ln_ in lines:
        dr.text((W / 2, y), ln_, font=f, fill=(*CREAM, 255), anchor="mt", stroke_width=max(2, int(3 * s)), stroke_fill=(*INK, 255))
        y += lh
    bw = dr.textlength(max(lines, key=len), font=f)
    dr.line([(W / 2 - bw / 2, y + 8 * s), (W / 2 + bw / 2, y + 8 * s)], fill=(*RUST, 255), width=max(3, int(6 * s)))
    return lay

WORDS = json.load(open(d / "words.json")) if (d / "words.json").exists() else []
CUTS = t.get("cuts") or [sum(t["durs"][:i]) for i in range(N + 1)]
def norm(x): return "".join(c for c in x.lower() if c.isalnum() or c == "'")

def mark_times(i, marks):
    """Seconds into scene i at which each mark starts stitching."""
    for m in marks:
        tt = m.get("t", 0.8)
        if m.get("word"):
            hit = [w for w in WORDS if norm(w["w"]) == norm(m["word"]) and CUTS[i] - 0.05 <= w["s"] < CUTS[i + 1]]
            if hit: tt = hit[0]["s"] - CUTS[i] + (LEAD if i == 0 else 0) - 0.1
            else: print(f"  ! scene {i + 1}: word {m['word']!r} not heard in this scene, using t={tt}")
        m["_t"] = max(0.2, tt)

def render_still(sc, img_path, out, frames, shot):
    """Still with a smooth sub-pixel camera move (no jitter) + optional overlay."""
    chart = sc.get("chart")
    if chart:
        src, cmap, cline = chart_setup(chart)
    else:
        src = Image.open(img_path).convert("RGB")
    iw, ih = src.size; ar = W / H
    cw, ch = (ih * ar, ih) if iw / ih > ar else (iw, iw / ar)
    fx, fy = sc.get("focus", [0.5, 0.5])
    ov = sc.get("overlay") or {}
    layer = overlay_png(ov); route = ov.get("points") if ov.get("type") == "route" else None
    marks = [dict(m) for m in sc.get("marks", [])]
    if chart:
        cw_, ch_ = src.size
        for ms in chart.get("milestones", []):
            px, py = cmap(*ms["at"])
            marks.append({"type": "label", "text": ms["text"], "word": ms.get("word"), "t": ms.get("t", 3.0),
                          "at": [px / cw_ - 0.006, py / ch_ - 0.012], "from": [px / cw_ - 0.05, py / ch_ - 0.05],
                          "tag": [px / cw_ - 0.12, py / ch_ - 0.085], "_dot": (px, py)})
    if marks:
        mark_times(sc["_i"], marks)
        for j, m in enumerate(marks): m["_paths"] = mark_paths(m, iw, ih, seed=sc["_i"] * 31 + j)
    cards = [(m["_t"], card_layer(m)) for m in marks if m["type"] == "card"]
    marks = [m for m in marks if m["type"] != "card"]
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
                          "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    for f in range(frames):
        u = f / max(frames - 1, 1); e = u * u * (3 - 2 * u)            # eased 0..1
        z, cx, cy = 1.0, iw / 2, ih / 2
        if shot == "zoom_in": z = 1 + ZOOM * e
        elif shot == "zoom_out": z = 1 + ZOOM * (1 - e)
        elif shot == "push":
            z = 1 + PUSH * e; cx += (fx - 0.5) * iw * e * 0.6; cy += (fy - 0.5) * ih * e * 0.6
        elif shot.startswith("pan_"):
            z = 1 + PAN; slack_x, slack_y = (cw - cw / z) / 2, (ch - ch / z) / 2
            k = (2 * e - 1)
            if shot == "pan_right": cx += slack_x * k
            elif shot == "pan_left": cx -= slack_x * k
            elif shot == "pan_down": cy += slack_y * k
            elif shot == "pan_up": cy -= slack_y * k
        w, h = cw / z, ch / z
        cx = min(max(cx, w / 2), iw - w / 2); cy = min(max(cy, h / 2), ih - h / 2)
        base = src
        if route or marks or chart:
            base = src.copy()
            if chart:
                ends = [m["_t"] for m in marks if "_dot" in m] or [frames / FPS * 0.8]
                k = min(1.0, max(0.0, (f / FPS - 0.5) / max(0.5, ends[0] - 0.5)))
                stitch(base, cline, k * (2 - k), RUST, w=max(6, int(base.size[0] * 0.0055)), st=base.size[0] * 0.014, gap=base.size[0] * 0.005)
                bd = ImageDraw.Draw(base)
                for m in marks:
                    if "_dot" in m and f / FPS >= m["_t"]:
                        x_, y_ = m["_dot"]; r_ = base.size[0] * 0.009
                        bd.ellipse([x_ - r_, y_ - r_, x_ + r_, y_ + r_], fill=RUST, outline=INK, width=3)
            if route: draw_route(base, route, min(1.0, max(0.0, (u - 0.08) / 0.75)))
            if marks: draw_marks(base, marks, f / FPS)
        fr = base.transform((W, H), Image.Transform.EXTENT, (cx - w/2, cy - h/2, cx + w/2, cy + h/2),
                            resample=Image.Resampling.BICUBIC)
        if layer is not None:
            alpha = min(1.0, max(0.0, (f / FPS - 0.5) / 0.6))           # fade the overlay in after 0.5 s
            if alpha > 0:
                lay = layer
                if alpha < 1:
                    r, g, b, al = layer.split(); al = al.point(lambda v: int(v * alpha)); lay = Image.merge("RGBA", (r, g, b, al))
                fr = Image.alpha_composite(fr.convert("RGBA"), lay).convert("RGB")
        for t0, cl in cards:
            k = min(1.0, max(0.0, (f / FPS - t0) / 0.45))
            if k > 0:
                r_, g_, b_, a_ = cl.split(); a_ = a_.point(lambda v: int(v * k))
                fr = Image.alpha_composite(fr.convert("RGBA"), Image.merge("RGBA", (r_, g_, b_, a_))).convert("RGB")
        p.stdin.write(fr.tobytes())
    p.stdin.close(); p.wait()
    if p.returncode: raise SystemExit(f"ffmpeg failed for {img_path}")

def probe(f):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                                capture_output=True, text=True).stdout)

alt = 0
for i, dur in enumerate(durs):
    n = i + 1; sc = scenes[i]; sc["_i"] = i
    L = dur + (xin[i + 1] if n < N else 0)
    clip, img, out = d / f"clips/scene{n:02d}.mp4", d / f"images/scene{n:02d}.jpg", seg / f"s{n:02d}.mp4"
    frames = int(round(L * FPS))
    if clip.exists():
        vf = f"setpts={L / probe(clip):.4f}*PTS,scale={W}:{H}:flags=lanczos,fps={FPS},format=yuv420p"
        layer = overlay_png(sc.get("overlay"))
        if layer is not None:
            png = seg / f"ov{n:02d}.png"; layer.save(png)
            cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-loop", "1", "-i", str(png), "-filter_complex",
                   f"[0:v]{vf}[b];[1:v]format=rgba,fade=in:st=0.5:d=0.6:alpha=1[o];[b][o]overlay=0:0:shortest=1,format=yuv420p",
                   "-frames:v", str(frames), "-an", "-c:v", "libx264", "-crf", str(crf), "-preset", preset, str(out)]
        else:
            cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-vf", vf, "-frames:v", str(frames), "-an",
                   "-c:v", "libx264", "-crf", str(crf), "-preset", preset, str(out)]
        subprocess.run(cmd, check=True)
        print(f"scene {n}: flow clip {L:.2f}s{'  (marks ignored: stills only)' if sc.get('marks') else ''}", flush=True)
    else:
        shot = sc.get("shot")
        if not shot:
            shot = "zoom_in" if alt % 2 == 0 else "zoom_out"; alt += 1
        render_still(sc, img, out, frames, shot)
        ov = (sc.get("overlay") or {}).get("type")
        mk = f" + {len(sc['marks'])} mark(s)" if sc.get("marks") else ""
        print(f"scene {n}: image + {shot}{' + ' + ov if ov else ''}{mk} {L:.2f}s", flush=True)

ins = []
for n in range(1, N + 1): ins += ["-i", str(seg / f"s{n:02d}.mp4")]
fc, prev, off = [], "[0:v]", 0.0
for i in range(1, N):
    off += durs[i - 1]; o = f"[v{i}]"
    fc.append(f"{prev}[{i}:v]xfade=transition=fade:duration={xin[i]}:offset={off:.3f}{o}"); prev = o
total = sum(durs)
fc.append(f"[{N}:a]aresample=48000,aformat=channel_layouts=stereo,loudnorm=I=-16:TP=-1.5:LRA=11,"
          f"adelay={int(LEAD*1000)}:all=1,apad,atrim=0:{total:.3f},asetpts=PTS-STARTPTS[a]")
subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-i", str(d / "voiceover.mp3"), "-filter_complex", ";".join(fc),
                "-map", prev, "-map", "[a]", "-r", str(FPS), "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{total:.3f}",
                "-movflags", "+faststart", str(d / out_name)], check=True)
print("wrote", d / out_name, f"({total:.2f}s)")
