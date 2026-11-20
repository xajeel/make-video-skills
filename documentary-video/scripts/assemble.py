"""Build one ~2-minute part (or a whole short video).

Usage:
  python3 assemble.py <part_dir> --draft            # quick 720p review render, no Flow clips needed
  python3 assemble.py <part_dir> [--out partNN.mp4] # final 1080p render
Expects in <part_dir>: scenes.json, timing.json, voiceover.mp3, images/sceneNN.jpg,
and clips/sceneNN.mp4 for the scenes animated in Flow (final render).

- Animated scenes: the Flow clip, speed-fitted to that scene's narration.
- ~30% of each part's scenes (picked at random among the non-Flow scenes, saved in motion3d.json so
  re-renders keep the same picks; edit or delete that file to change them): a free 3D camera move
  (parallax.py: depth map + push-in/slide with parallax). Needs setup_3d.sh once; falls back to zoom if missing.
- Other scenes: the image with a VERY subtle slow zoom (~3%), alternating in/out.
  Keep it barely noticeable - the user wants "very little", not a Ken Burns slideshow.
- 0.5 s dissolves between scenes.
- Every part gets the SAME edges so parts join smoothly later (join_parts.py):
  LEAD s of picture before the first word, TAIL s of quiet picture after the last word.
- Voiceover is loudness-normalised (-16 LUFS) to 48 kHz stereo so every part sounds the same.
"""
import argparse, json, os, random, subprocess, pathlib

ZOOM = 0.03   # total zoom change over a still scene (0.03 = 3%)
LEAD = 0.4    # seconds before the first word
TAIL = 1.2    # seconds of quiet picture after the last word (join_parts crossfades inside this)
X = 0.5       # dissolve between scenes
FPS = 30
SHARE_3D = 0.30   # share of each part's scenes that get the 3D camera move (user rule, 2026-11-20)
HERE = pathlib.Path(__file__).resolve().parent
DOCVID = pathlib.Path(os.environ.get("DOCVID_HOME", pathlib.Path.home() / ".local/share/documentary-video"))
PY3D, MODEL3D = DOCVID / "depthenv/bin/python", DOCVID / "models/depth_anything_v2_small.onnx"
MOVES_3D = ["push_slide", "push", "slide_right", "slide_left"]

ap = argparse.ArgumentParser()
ap.add_argument("part_dir")
ap.add_argument("--draft", action="store_true", help="fast 720p review render; ignores missing clips")
ap.add_argument("--out")
ap.add_argument("--no-3d", action="store_true", help="plain zoom on every still (no 3D camera moves)")
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

def pattern_scenes(part_dir):
    """Scenes the project animates in Flow for this part (from ../../project.json), so draft renders
    without clips still keep those scenes free of 3D moves."""
    pj = part_dir.parent.parent / "project.json"
    if not pj.exists() or not part_dir.name.startswith("part"): return set()
    p = json.load(open(pj)); pat = p["decisions"].get("animation_pattern", [])
    if isinstance(pat, list): return set(pat)
    n, total = int(part_dir.name[4:]), len(p["parts"])
    return set(pat.get("first" if n == 1 else "last" if n == total else "middle", []))

def plan_3d(part_dir, N):
    """{scene: move} for ~SHARE_3D of the scenes, random among stills; saved so re-renders are stable."""
    f = part_dir / "motion3d.json"
    if f.exists(): return {int(k): v for k, v in json.load(open(f))["scenes"].items()}
    skip = pattern_scenes(part_dir) | {n for n in range(1, N + 1) if (part_dir / f"clips/scene{n:02d}.mp4").exists()}
    cand = [n for n in range(1, N + 1) if n not in skip]
    rng = random.Random(f"{part_dir.parent.parent.name}/{part_dir.name}")
    picks = sorted(rng.sample(cand, min(len(cand), int(N * SHARE_3D + 0.5))))
    moves = MOVES_3D[:]; rng.shuffle(moves)
    plan = {n: moves[i % len(moves)] for i, n in enumerate(picks)}
    json.dump({"note": "3D camera move scenes (assemble.py). Edit or delete to change.", "scenes": plan}, open(f, "w"), indent=1)
    return plan

def probe(f):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                                capture_output=True, text=True).stdout)

have_3d = PY3D.exists() and MODEL3D.exists()
plan = {} if a.no_3d else plan_3d(d, N)
if plan and not have_3d:
    print("WARNING: 3D move not set up (run setup_3d.sh) - using plain zoom for", sorted(plan)); plan = {}
if plan: print("3D camera move on scenes:", ", ".join(f"{n} ({m})" for n, m in plan.items()), flush=True)
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
    elif n in plan:
        subprocess.run([str(PY3D), "-I", str(HERE / "parallax.py"), str(img), str(out), "--frames", str(frames),
                        "--move", plan[n], "--size", f"{W}x{H}", "--fps", str(FPS), "--crf", str(crf), "--preset", preset],
                       check=True, stdout=subprocess.DEVNULL)
        print(f"scene {n}: image + 3D camera move ({plan[n]}) {L:.2f}s", flush=True)
        continue
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
