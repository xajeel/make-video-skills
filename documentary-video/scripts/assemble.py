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

def draw_route(img, pts, frac):
    """Rust 'thread' stitched along pts (0-1 coords) up to fraction frac of its length, as dashes."""
    iw, ih = img.size; P = [(x * iw, y * ih) for x, y in pts]
    seglen = [((P[i+1][0]-P[i][0])**2 + (P[i+1][1]-P[i][1])**2) ** 0.5 for i in range(len(P) - 1)]
    total = sum(seglen) or 1; goal = total * frac; dr = ImageDraw.Draw(img)
    st, gap, w = iw * 0.020, iw * 0.010, max(6, int(iw * 0.010)); walked = 0.0
    for i, L in enumerate(seglen):
        pos = 0.0
        while pos < L and walked + pos < goal:
            e = min(pos + st, L, goal - walked)
            ax, ay = P[i][0] + (P[i+1][0]-P[i][0]) * pos / L, P[i][1] + (P[i+1][1]-P[i][1]) * pos / L
            bx, by = P[i][0] + (P[i+1][0]-P[i][0]) * e / L, P[i][1] + (P[i+1][1]-P[i][1]) * e / L
            dr.line([(ax + 2, ay + 3), (bx + 2, by + 3)], fill=INK, width=w)     # thread shadow
            dr.line([(ax, ay), (bx, by)], fill=RUST, width=w)
            pos = e + gap
        walked += L
        if walked >= goal: break
    if frac >= 0.999:
        x, y = P[-1]; r = w * 1.6; dr.ellipse([x - r, y - r, x + r, y + r], fill=RUST, outline=INK, width=2)

def render_still(sc, img_path, out, frames, shot):
    """Still with a smooth sub-pixel camera move (no jitter) + optional overlay."""
    src = Image.open(img_path).convert("RGB")
    iw, ih = src.size; ar = W / H
    cw, ch = (ih * ar, ih) if iw / ih > ar else (iw, iw / ar)
    fx, fy = sc.get("focus", [0.5, 0.5])
    ov = sc.get("overlay") or {}
    layer = overlay_png(ov); route = ov.get("points") if ov.get("type") == "route" else None
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
        if route:
            base = src.copy(); draw_route(base, route, min(1.0, max(0.0, (u - 0.08) / 0.75)))
        fr = base.transform((W, H), Image.Transform.EXTENT, (cx - w/2, cy - h/2, cx + w/2, cy + h/2),
                            resample=Image.Resampling.BICUBIC)
        if layer is not None:
            alpha = min(1.0, max(0.0, (f / FPS - 0.5) / 0.6))           # fade the overlay in after 0.5 s
            if alpha > 0:
                lay = layer
                if alpha < 1:
                    r, g, b, al = layer.split(); al = al.point(lambda v: int(v * alpha)); lay = Image.merge("RGBA", (r, g, b, al))
                fr = Image.alpha_composite(fr.convert("RGBA"), lay).convert("RGB")
        p.stdin.write(fr.tobytes())
    p.stdin.close(); p.wait()
    if p.returncode: raise SystemExit(f"ffmpeg failed for {img_path}")

def probe(f):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                                capture_output=True, text=True).stdout)

alt = 0
for i, dur in enumerate(durs):
    n = i + 1; sc = scenes[i]
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
        print(f"scene {n}: flow clip {L:.2f}s", flush=True)
    else:
        shot = sc.get("shot")
        if not shot:
            shot = "zoom_in" if alt % 2 == 0 else "zoom_out"; alt += 1
        render_still(sc, img, out, frames, shot)
        ov = (sc.get("overlay") or {}).get("type")
        print(f"scene {n}: image + {shot}{' + ' + ov if ov else ''} {L:.2f}s", flush=True)

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
