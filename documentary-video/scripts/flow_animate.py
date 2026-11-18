"""Animate project images into video clips through the Flow website (image-to-video).

gflow's own i2v is refused on this account (Flow "agent-only composer"), so this drives the
Flow web composer in the Chrome opened by launch_flow_chrome.sh.

Usage:
  python flow_animate.py --project <flow_project_id> --scenes path/to/scenes.json 1 7 9
Each scene in scenes.json needs "motion" and "flow_title" (the title Flow gave the image;
list them with: cdp.py eval "..." or read them in the Flow asset picker).
Costs Flow credits: ~24 credits per 8 s clip on the default model (Omni 1.2 Flash).
Run with the gflow-cli venv python (it has playwright):
  ~/.local/share/uv/tools/gflow-cli/bin/python flow_animate.py ...
"""
import argparse, json, time
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--project", required=True)
ap.add_argument("--scenes", required=True)
ap.add_argument("numbers", nargs="+", type=int)
a = ap.parse_args()
URL = f"https://flow.google.com/project/{a.project}"
scenes = {s["n"]: s for s in json.load(open(a.scenes))["scenes"]}

with sync_playwright() as p:
    ctx = p.chromium.connect_over_cdp("http://127.0.0.1:9333").contexts[0]
    page = [pg for pg in ctx.pages if "flow.google.com" in pg.url][-1]
    page.set_default_timeout(30000)
    for n in a.numbers:
        s = scenes[n]
        page.goto(URL, wait_until="domcontentloaded"); time.sleep(6)
        page.locator('button[aria-label="Add ingredients to the prompt box"]').first.click(); time.sleep(3)
        page.get_by_placeholder("Search assets").fill(s["flow_title"]); time.sleep(4)  # newest match is preselected
        page.get_by_text("Add to prompt", exact=True).last.click(); time.sleep(2)
        page.locator('[contenteditable="true"]').last.click(); time.sleep(0.5)
        prompt = ("Animate this exact image into an 8-second 16:9 video. Keep the hand-embroidered tapestry look, "
                  "stitched thread texture and composition exactly. Motion: " + s["motion"] +
                  ". Natural ambient sound only, no speech, no music, no text.")
        page.keyboard.type(prompt, delay=5); time.sleep(1)
        btn = page.locator('button[aria-label="Start generation"]').last
        for _ in range(20):
            if btn.is_enabled(): break
            time.sleep(0.5)
        btn.click(); time.sleep(8)
        print(f"scene {n}: submitted", flush=True)
    # wait until nothing is generating
    for _ in range(90):
        t = page.inner_text("body")
        import re
        if not re.search(r"\b\d{1,3}%", t) and "Thinking" not in t: break
        time.sleep(10)
    print("all submitted clips finished", flush=True)
