"""Long-form project state: create, inspect and update. Everything a fresh session needs lives in
<project_dir>/project.json (machine state) and <project_dir>/PROGRESS.md (human log).

  python3 project.py new  <videos_root> --title "The Viking Age" --minutes 8
  python3 project.py status <project_dir>
  python3 project.py set <project_dir> <part_n> <status> [--note "..."] [--credits 120]
  python3 project.py decide <project_dir> <key> <value> [--note "why"]
  python3 project.py log <project_dir> "free-text note"
  python3 project.py clips <project_dir> <part_n>      # prints the scenes to animate in Flow for that part

Part status flow (one part = ~2 min = 15 scenes):
  planned -> script_review -> draft_review -> final_review -> final
  script_review : script written, waiting for the user's OK
  draft_review  : voiceover + images + draft.mp4 (720p, no Flow clips) sent for review
  final_review  : Flow clips made, partNN.mp4 rendered at 1080p, sent for review
  final         : approved; ready for join_parts.py
"""
import argparse, datetime, json, pathlib, re, shutil, sys

SKILL = pathlib.Path(__file__).resolve().parent.parent
STATUSES = ["planned", "script_review", "draft_review", "final_review", "final"]
NEXT = {"planned": "write this part's scenes.json (continue from previous part's last line), then set script_review",
        "script_review": "wait for the user's OK on the script; then voiceover + images + timing + Flow clips ({clips}) + final assemble, send the path, set final_review",
        "draft_review": "wait for the user's OK on the draft; then animate the pattern scenes in Flow, download clips, final assemble, set final_review",
        "final_review": "wait for the user's OK on the final part render; then set final",
        "final": "done - when all parts are final run join_parts.py"}

# Default Flow clip pattern (user rule, 2026-11-20): first part 5 clips, middle parts 2 clips, last part none.
DEFAULT_PATTERN = {"first": [1, 2, 4, 6], "middle": [1, 4], "last": []}
VOICE_SETTINGS = {"stability": 0.8, "similarity": 0.9}   # eleven_v4: steady, consistent narrator across parts

def clips_for(p, n):
    """Scenes to animate in part n. animation_pattern may be the old flat list (same for every part)
    or a dict {first, middle, last}; a single-part video uses "first"."""
    pat = p["decisions"].get("animation_pattern", DEFAULT_PATTERN)
    if isinstance(pat, list): return pat
    total = len(p["parts"])
    key = "first" if n == 1 else "last" if n == total else "middle"
    return pat.get(key, [])

def now(): return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
def load(d): return json.load(open(d / "project.json"))
def save(d, p): json.dump(p, open(d / "project.json", "w"), indent=1)
def log(d, line):
    with open(d / "PROGRESS.md", "a") as f: f.write(f"- {now()} - {line}\n")

ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
a1 = sub.add_parser("new"); a1.add_argument("root"); a1.add_argument("--title", required=True); a1.add_argument("--minutes", type=float, required=True)
a2 = sub.add_parser("status"); a2.add_argument("dir")
a3 = sub.add_parser("set"); a3.add_argument("dir"); a3.add_argument("part", type=int); a3.add_argument("status", choices=STATUSES)
a3.add_argument("--note", default=""); a3.add_argument("--credits", type=int, default=0)
a4 = sub.add_parser("decide"); a4.add_argument("dir"); a4.add_argument("key"); a4.add_argument("value"); a4.add_argument("--note", default="")
a5 = sub.add_parser("log"); a5.add_argument("dir"); a5.add_argument("text")
a6 = sub.add_parser("clips"); a6.add_argument("dir"); a6.add_argument("part", type=int)
a = ap.parse_args()

if a.cmd == "new":
    slug = re.sub(r"[^a-z0-9]+", "_", a.title.lower()).strip("_")
    d = pathlib.Path(a.root) / slug
    if (d / "project.json").exists(): sys.exit(f"already exists: {d}")
    n_parts = max(1, round(a.minutes / 2))
    tmpl = json.load(open(SKILL / "templates" / "scenes.example.json"))
    p = {"title": a.title, "slug": slug, "created": now(), "target_minutes": a.minutes, "part_minutes": 2,
         "decisions": {"voice_id": "QngvLQR8bsLR5bzoa6Vv", "voice_name": "Michael Dan - British Documentary Narrator",
                       "tts_model": "eleven_v4", "style": tmpl["style"], "image_model": "nano2", "aspect": "16:9",
                       "flow_project_id": None, "gflow_profile": "sajeel135", "animation_pattern": DEFAULT_PATTERN,
                       "voice_settings": VOICE_SETTINGS, "eleven_flow_id": None, "eleven_tts_node_id": None,
                       "flow_video_model": "Omni 1.2 Flash (default, 24 credits/clip)", "zoom": 0.03, "scenes_per_part": 15},
         "parts": [{"n": i + 1, "status": "planned", "summary": "", "credits": 0, "notes": []} for i in range(n_parts)],
         "credits_total": 0}
    for i in range(n_parts): (d / "parts" / f"part{i + 1:02d}" / "images").mkdir(parents=True, exist_ok=True); (d / "parts" / f"part{i + 1:02d}" / "clips").mkdir(exist_ok=True)
    save(d, p)
    (d / "outline.md").write_text(f"# {a.title} - outline\n\nWhole-video arc first, then one section per part (~2 min, 15 scenes each).\n"
        "For each part: what it covers, its opening line (must pick up from the previous part's closing line), its closing line (hand-off).\n\n"
        + "".join(f"## Part {i + 1}\n- Covers:\n- Opens with:\n- Closes with (hand-off):\n\n" for i in range(n_parts)))
    (d / "PROGRESS.md").write_text(f"# {a.title} - progress\n\nRead this first in a new session, then `project.py status`.\n"
        f"Skill: {SKILL}\n\n## Decisions\nSee project.json -> decisions (voice, style, Flow project, animation pattern...).\n\n## Log\n")
    log(d, f"project created: {a.minutes} min -> {n_parts} parts of ~2 min")
    print(d)

elif a.cmd == "status":
    d = pathlib.Path(a.dir); p = load(d)
    print(f"{p['title']}  ({p['target_minutes']} min, {len(p['parts'])} parts)  credits spent: {p['credits_total']}")
    print("decisions:", json.dumps({k: v for k, v in p["decisions"].items() if k != "style"}, ensure_ascii=False))
    for part in p["parts"]:
        c = clips_for(p, part["n"])
        print(f"  part {part['n']:02d}: {part['status']:<13} {part['summary'][:50]}  clips={' '.join(map(str, c)) or 'none'}  credits={part['credits']}")
    cur = next((x for x in p["parts"] if x["status"] != "final"), None)
    if cur:
        c = " ".join(map(str, clips_for(p, cur["n"]))) or "none - images only"
        print("NEXT:", f"part {cur['n']:02d} - {NEXT[cur['status']].format(clips=c)}")
    else: print("NEXT:", NEXT["final"])

elif a.cmd == "set":
    d = pathlib.Path(a.dir); p = load(d); part = p["parts"][a.part - 1]
    part["status"] = a.status; part["credits"] += a.credits; p["credits_total"] += a.credits
    if a.note: part["notes"].append(f"{now()} {a.note}")
    save(d, p); log(d, f"part {a.part:02d} -> {a.status}" + (f" (+{a.credits} credits)" if a.credits else "") + (f": {a.note}" if a.note else ""))
    print("ok")

elif a.cmd == "decide":
    d = pathlib.Path(a.dir); p = load(d)
    try: val = json.loads(a.value)
    except Exception: val = a.value
    p["decisions"][a.key] = val; save(d, p); log(d, f"decision: {a.key} = {a.value}" + (f" ({a.note})" if a.note else "")); print("ok")

elif a.cmd == "clips":
    d = pathlib.Path(a.dir); print(" ".join(map(str, clips_for(load(d), a.part))))

elif a.cmd == "log":
    d = pathlib.Path(a.dir); log(d, a.text); print("ok")
