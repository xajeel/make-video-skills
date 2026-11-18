"""Join finished parts into the long-form video with smooth, jerk-free connections.

Usage: python3 join_parts.py <project_dir>
Reads project.json -> parts (in order) with status "final", uses parts/partNN/partNN.mp4,
writes final/<slug>_full.mp4.

How the join stays smooth:
- Every part was rendered by assemble.py with identical format (1920x1080, 30 fps, yuv420p,
  AAC 48 kHz stereo, -16 LUFS) and identical edges (LEAD before first word, TAIL quiet after last).
- Picture: a JOIN-second dissolve from part N's quiet tail into part N+1's opening.
- Sound: part N's audio is cut inside its silent tail and part N+1's audio follows directly,
  so no words overlap and there's no level jump; a tiny 30 ms fade on each cut avoids clicks.
"""
import json, subprocess, sys, pathlib

JOIN = 1.0   # must be < assemble.py TAIL (1.2 s)

d = pathlib.Path(sys.argv[1])
proj = json.load(open(d / "project.json"))
parts = [p for p in proj["parts"] if p.get("status") == "final"]
files = [d / "parts" / f"part{p['n']:02d}" / f"part{p['n']:02d}.mp4" for p in parts]
missing = [str(f) for f in files if not f.exists()]
if missing: sys.exit(f"missing part renders: {missing}")
if len(files) < 2: sys.exit("need at least 2 final parts to join")

def dur(f):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                                capture_output=True, text=True).stdout)
D = [dur(f) for f in files]
ins = []
for f in files: ins += ["-i", str(f)]
fc, prev, off = [], "[0:v]", 0.0
for i in range(1, len(files)):
    off += D[i - 1] - JOIN; o = f"[v{i}]"
    fc.append(f"{prev}[{i}:v]xfade=transition=fade:duration={JOIN}:offset={off:.3f}{o}"); prev = o
alabels = []
for i, L in enumerate(D):
    keep = L - JOIN if i < len(D) - 1 else L
    fc.append(f"[{i}:a]atrim=0:{keep:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.03,afade=t=out:st={keep-0.03:.3f}:d=0.03[a{i}]")
    alabels.append(f"[a{i}]")
fc.append("".join(alabels) + f"concat=n={len(D)}:v=0:a=1[a]")
(d / "final").mkdir(exist_ok=True)
out = d / "final" / f"{proj['slug']}_full.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(fc), "-map", prev, "-map", "[a]",
                "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out)], check=True)
print("wrote", out, f"({sum(D) - JOIN * (len(D) - 1):.2f}s from {len(D)} parts)")
