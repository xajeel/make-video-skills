"""Animate scene images into 8 s clips on the Flow website (image-to-video, "Frames" mode).

gflow's own i2v is refused on this account (Flow "agent-only composer"), so this drives the Flow web
composer in the Chrome opened by launch_flow_chrome.sh (CDP port 9333).

Usage (run with ~/.local/share/uv/tools/gflow-cli/bin/python):
  flow_animate.py --project <flow_project_id> --part parts/partNN [--upload] [--prefix rh_p2_] 1 2 3 5 8

What it does (Flow UI as of Nov 2026):
  1. --upload: uploads parts/partNN/images/sceneNN.jpg as "<prefix>sceneNN.jpg" (top "+" -> Upload).
     Needed when the images were not made inside this Flow project (e.g. the user's own extension).
  2. Composer settings: Video tab -> Frames (start frame = the exact image) -> x1 (one take).
     Default model Omni 1.2 Flash, 720p, 8 s = 24 credits per clip. Prints the "Generating will use N credits" line.
  3. Per scene: Start slot -> search "<prefix>sceneNN" -> click the row (sets the frame), type the motion prompt
     from scenes.json, press Start generation. No approval dialog any more.
Costs Flow credits. Check gflow_get_credits before and after (free).
Gotchas: the composer defaults to Image / Nano Banana x2 - submitting there makes 2 free IMAGES, not video.
The asset rows also exist as hidden grid titles, so match with ">> visible=true".
"""
import argparse, json, glob, os, re, shutil, tempfile, time
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--project", required=True)
ap.add_argument("--part", required=True)
ap.add_argument("--prefix", default="scene_")
ap.add_argument("--upload", action="store_true")
ap.add_argument("numbers", nargs="+", type=int)
a = ap.parse_args()
part = os.path.abspath(a.part)
scenes = {s["n"]: s for s in json.load(open(f"{part}/scenes.json"))["scenes"]}
URL = f"https://flow.google.com/project/{a.project}"
name = lambda n: f"{a.prefix}scene{n:02d}"

with sync_playwright() as p:
    ctx = p.chromium.connect_over_cdp("http://127.0.0.1:9333").contexts[0]
    page = [pg for pg in ctx.pages if "flow.google.com" in pg.url][-1]
    page.set_default_timeout(30000)
    page.goto(URL, wait_until="domcontentloaded"); time.sleep(6)

    if a.upload:
        tmp = tempfile.mkdtemp()
        files = []
        for n in a.numbers:
            f = f"{tmp}/{name(n)}.jpg"; shutil.copy(f"{part}/images/scene{n:02d}.jpg", f); files.append(f)
        page.locator('button[aria-label="Add media menu"]').click(); time.sleep(2)
        with page.expect_file_chooser() as fc:
            page.locator("flow-menu-item button", has_text="Upload").first.click()
        fc.value.set_files(files); time.sleep(20)
        print("uploaded", len(files), flush=True)
        page.goto(URL, wait_until="domcontentloaded"); time.sleep(6)

    page.locator('button[aria-label="Settings trigger"]').last.click(); time.sleep(2)
    page.get_by_text("Video", exact=True).last.click(); time.sleep(1.5)
    page.get_by_text("Frames", exact=True).last.click(); time.sleep(1.5)
    page.get_by_text("x1", exact=True).last.click(); time.sleep(1.5)
    cost = re.search(r"Generating will use (\d+) credits", page.inner_text("body"))
    print("per clip:", cost.group(1) if cost else "?", "credits", flush=True)
    page.keyboard.press("Escape"); time.sleep(1.5)

    for n in a.numbers:
        page.locator("text=Start >> visible=true").last.click(); time.sleep(3)
        page.get_by_placeholder("Search assets").fill(name(n)); time.sleep(3)
        page.locator(f"text={name(n)}.jpg >> visible=true").first.click(); time.sleep(3)
        page.locator('[contenteditable="true"]').last.click(); time.sleep(0.5)
        page.keyboard.type("Animate this exact image into an 8-second video. Keep the hand-embroidered tapestry look, stitched "
                           "thread texture and composition exactly. Motion: " + scenes[n]["motion"] + ". Natural ambient "
                           "sound only, no speech, no music. Do not show any time, numbers, labels or text.", delay=4)
        time.sleep(1)
        btn = page.locator('button[aria-label="Start generation"]').last
        for _ in range(30):
            if btn.is_enabled(): break
            time.sleep(1)
        btn.click(); time.sleep(8)
        print(f"scene {n}: submitted", flush=True)

    for _ in range(60):   # wait until nothing is generating
        if not re.search(r"\b\d{1,3}%", page.inner_text("body")): break
        time.sleep(15)
    print("done", flush=True)
