"""Work out where each scene starts in the voiceover.

Usage: python3 timing.py <project_dir>      (needs voiceover.mp3 + scenes.json there)
Writes timing.json {"cuts": [...], "durs": [...]} and prints the durations.
Method: detect pauses with ffmpeg silencedetect, estimate each boundary from cumulative word
count, snap it to the nearest LONG pause (paragraph breaks are ~0.6-0.9 s, sentence breaks shorter).
Always eyeball the printed durations: scenes now vary on purpose (about 3-12 s); one outside that range usually means a wrong snap -
fix it by hand in timing.json using the printed pause list.
"""
import json, re, subprocess, sys, pathlib

d = pathlib.Path(sys.argv[1])
vo = d / "voiceover.mp3"
out = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(vo), "-af", "silencedetect=noise=-35dB:d=0.35", "-f", "null", "-"],
                     capture_output=True, text=True).stderr
starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
sil = list(zip(starts, ends))
total = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(vo)],
                             capture_output=True, text=True).stdout)
scenes = json.load(open(d / "scenes.json"))["scenes"]
words = [len(s["narration"].split()) for s in scenes]
W = sum(words)
speech_start = sil[0][1] if sil and sil[0][0] < 0.1 else 0.0
long_pauses = [((a + b) / 2, b - a) for a, b in sil if b - a >= 0.5 and a > 0.1]
print("long pauses (mid, len):", " ".join(f"{m:.2f}({l:.2f})" for m, l in long_pauses))
cuts, acc = [0.0], 0
for w in words[:-1]:
    acc += w
    est = speech_start + (total - speech_start) * acc / W
    cand = [m for m, _ in long_pauses if m > cuts[-1] + 3]
    cuts.append(round(min(cand, key=lambda m: abs(m - est)) if cand else est, 2))
cuts.append(round(total, 2))
durs = [round(cuts[i + 1] - cuts[i], 2) for i in range(len(scenes))]
json.dump({"cuts": cuts, "durs": durs}, open(d / "timing.json", "w"))
print("cuts:", cuts)
print("durs:", durs)
