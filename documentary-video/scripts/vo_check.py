"""Check a part's voiceover against its script and save word times for timing.py.

Usage: ~/myrepo/videostst/.venv/bin/python vo_check.py <part_dir>
Transcribes voiceover.mp3 locally with faster-whisper (medium.en, free), prints every difference
from the narration in scenes.json (number formatting like "1992" vs "nineteen ninety-two" is
expected and harmless) plus words with low confidence, and writes words.json
[{"w": word, "s": start, "e": end, "p": probability}, ...] next to the voiceover.
"""
import json, re, sys, difflib, pathlib
from faster_whisper import WhisperModel

d = pathlib.Path(sys.argv[1])
m = WhisperModel("medium.en", device="cpu", compute_type="int8")
segs, _ = m.transcribe(str(d / "voiceover.mp3"), word_timestamps=True)
words = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3), "p": round(w.probability, 3)}
         for s in segs for w in s.words]
json.dump(words, open(d / "words.json", "w"), indent=0)
norm = lambda t: re.sub(r"[^a-z0-9']", "", t.lower())
ref = [x for x in (norm(t) for s in json.load(open(d / "scenes.json"))["scenes"] for t in s["narration"].split()) if x]
heard = [x for x in (norm(w["w"]) for w in words) if x]
for op, a1, a2, b1, b2 in difflib.SequenceMatcher(a=ref, b=heard, autojunk=False).get_opcodes():
    if op != "equal":
        print(f"{op}: {' '.join(ref[a1:a2])!r} -> {' '.join(heard[b1:b2])!r}")
print("low confidence:", [(float(w["s"]), w["w"], float(w["p"])) for w in words if w["p"] < 0.5])
print(f"wrote {d / 'words.json'} ({len(words)} words)")
