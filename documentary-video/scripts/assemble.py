"""Build one ~2-minute part (or a whole short video).

Usage:
  python3 assemble.py <part_dir> --draft            # quick 720p review render, no Flow clips needed
  python3 assemble.py <part_dir> [--out partNN.mp4] # final 1080p render
Expects in <part_dir>: scenes.json, timing.json, voiceover.mp3, images/sceneNN.jpg,
and clips/sceneNN.mp4 for the scenes animated in Flow (final render).

- Animated scenes: the Flow clip, speed-fitted to that scene's narration.
- Other scenes: the image with a VERY subtle slow zoom (~3%), alternating in/out.
  Keep it barely noticeable - the user wants "very little", not a Ken Burns slideshow.
- 0.5 s dissolves between scenes.
- Every part gets the SAME edges so parts join smoothly later (join_parts.py):
  LEAD s of picture before the first word, TAIL s of quiet picture after the last word.
- Voiceover is loudness-normalised (-16 LUFS) to 48 kHz stereo so every part sounds the same.
"""
import argparse, json, subprocess, pathlib

ZOOM = 0.03   # total zoom change over a still scene (0.03 = 3%)
LEAD = 0.4    # seconds before the first word
TAIL = 1.2    # seconds of quiet picture after the last word (join_parts crossfades inside this)
X = 0.5       # dissolve between scenes
FPS = 30

ap = argparse.ArgumentParser()
ap.add_argument("part_dir")
ap.add_argument("--draft", action="store_true", help="fast 720p review render; ignores missing clips")
ap.add_argument("--out")
a = ap.parse_args()
d = pathlib.Path(a.part_dir).resolve()
W, H = (1280, 720) if a.draft else (1920, 1080)
out_name = a.out or ("draft.mp4" if a.draft else f"{d.name}.mp4")
preset, crf = ("veryfast", 23) if a.draft else ("medium", 19)

t = json.load(open(d / "timing.json"))
durs = list(t["durs"]); N = len(durs)
durs[0] += LEAD; durs[-1] += TAIL
seg = d / ("seg_draft" if a.draft else "seg"); seg.mkdir(exist_ok=True)

def smooth_zoom(img_path, out, frames, zoom_in, crf, preset):
    """Render a still with a slow centred zoom using sub-pixel crop boxes (no jitter)."""
    from PIL import Image
    src = Image.open(img_path).convert("RGB")
    iw, ih = src.size
    # crop the source to the output aspect first
    ar = W / H
    if iw / ih > ar: cw, ch = ih * ar, ih
    else: cw, ch = iw, iw / ar
    cx, cy = iw / 2, ih / 2
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
                          "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    for f in range(frames):
        t = f / max(frames - 1, 1)
        t = t * t * (3 - 2 * t)                      # ease in/out
        z = 1 + ZOOM * (t if zoom_in else 1 - t)
        w, h = cw / z, ch / z
        box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        p.stdin.write(src.transform((W, H), Image.Transform.EXTENT, box, resample=Image.Resampling.BICUBIC).tobytes())
    p.stdin.close(); p.wait()
    if p.returncode: raise SystemExit(f"ffmpeg failed for {img_path}")

def probe(f):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                                capture_output=True, text=True).stdout)

still_count = 0
for i, dur in enumerate(durs):
    n = i + 1; L = dur + (X if n < N else 0)
    clip, img, out = d / f"clips/scene{n:02d}.mp4", d / f"images/scene{n:02d}.jpg", seg / f"s{n:02d}.mp4"
    frames = int(round(L * FPS))
    if clip.exists():
        vf = f"setpts={L / probe(clip):.4f}*PTS,scale={W}:{H}:flags=lanczos,fps={FPS},format=yuv420p"
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-vf", vf, "-frames:v", str(frames), "-an",
               "-c:v", "libx264", "-crf", str(crf), "-preset", preset, str(out)]
        kind = "flow clip"
    else:
        # Smooth sub-pixel zoom rendered with Pillow (ffmpeg zoompan snaps to whole pixels -> visible shake).
        zoom_in = still_count % 2 == 0
        still_count += 1
        smooth_zoom(img, out, frames, zoom_in, crf, preset)
        print(f"scene {n}: image + subtle zoom {L:.2f}s", flush=True)
        continue
    subprocess.run(cmd, check=True)
    print(f"scene {n}: {kind} {L:.2f}s", flush=True)

ins = []
for n in range(1, N + 1): ins += ["-i", str(seg / f"s{n:02d}.mp4")]
fc, prev, off = [], "[0:v]", 0.0
for i in range(1, N):
    off += durs[i - 1]; o = f"[v{i}]"
    fc.append(f"{prev}[{i}:v]xfade=transition=fade:duration={X}:offset={off:.3f}{o}"); prev = o
total = sum(durs)
fc.append(f"[{N}:a]aresample=48000,aformat=channel_layouts=stereo,loudnorm=I=-16:TP=-1.5:LRA=11,"
          f"adelay={int(LEAD*1000)}:all=1,apad,atrim=0:{total:.3f},asetpts=PTS-STARTPTS[a]")
subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-i", str(d / "voiceover.mp3"), "-filter_complex", ";".join(fc),
                "-map", prev, "-map", "[a]", "-r", str(FPS), "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{total:.3f}",
                "-movflags", "+faststart", str(d / out_name)], check=True)
print("wrote", d / out_name, f"({total:.2f}s)")
