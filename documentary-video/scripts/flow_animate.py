"""Animate project images into video clips through the Flow website (image-to-video).

gflow's own i2v is refused on this account (Flow "agent-only composer"), so this drives the
Flow web composer in the Chrome opened by launch_flow_chrome.sh.

Usage:
  ~/.local/share/uv/tools/gflow-cli/bin/python flow_animate.py --project <flow_project_id> --scenes parts/partNN/scenes.json 1 2 3 5 8
Each scene in scenes.json needs "motion" and "flow_title" (the title Flow gave the image - read them with
  cdp.py eval "JSON.stringify([...document.querySelectorAll('.footer-title')].map(e=>e.textContent.trim()))"
on the project page; the grid is newest-first).
Costs Flow credits: 24 credits per 8 s clip on the default model (Omni 1.2 Flash).

How it works (learned the hard way):
- Load the project ONCE and start a fresh agent chat session ("Start new session"); a session full of
  old/expired requests answers "Something went wrong".
- New projects ask "kick off this 1 video generation, costing N credits?". The clips are the user's
  request, so approve exactly these (never "Always approve in project"). The options go dim (expire)
  if the page reloads, so approve immediately and never reload between scenes.
"""
import argparse, json, re, time
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--project", required=True)
ap.add_argument("--scenes", required=True)
ap.add_argument("numbers", nargs="+", type=int)
a = ap.parse_args()
URL = f"https://flow.google.com/project/{a.project}"
scenes = {s["n"]: s for s in json.load(open(a.scenes))["scenes"]}
APPROVE = re.compile(r"^\s*Approve\s*$")
spent = 0

with sync_playwright() as p:
    ctx = p.chromium.connect_over_cdp("http://127.0.0.1:9333").contexts[0]
    page = [pg for pg in ctx.pages if "flow.google.com" in pg.url][-1]
    page.set_default_timeout(30000)
    page.goto(URL, wait_until="domcontentloaded"); time.sleep(6)
    new = page.locator('button[aria-label="Start new session"]')
    if new.count(): new.first.click(); time.sleep(3)
    for n in a.numbers:
        s = scenes[n]
        add = page.locator('button[aria-label="Add ingredients to the prompt box"]').first
        for _ in range(180):          # the composer is disabled while the agent handles the previous clip
            if add.is_enabled(): break
            time.sleep(1)
        add.click(); time.sleep(3)
        page.get_by_placeholder("Search assets").fill(s["flow_title"]); time.sleep(4)   # newest match is preselected
        page.get_by_text("Add to prompt", exact=True).last.click(); time.sleep(2)
        page.locator('[contenteditable="true"]').last.click(); time.sleep(0.5)
        page.keyboard.type("Animate this exact image into an 8-second 16:9 video. Keep the hand-embroidered tapestry look, "
                           "stitched thread texture and composition exactly. Motion: " + s["motion"] +
                           ". Natural ambient sound only, no speech, no music, no text.", delay=5)
        time.sleep(1)
        btn = page.locator('button[aria-label="Start generation"]').last
        for _ in range(30):
            if btn.is_enabled(): break
            time.sleep(1)
        btn.click()
        result = "no answer in 90 s"
        for _ in range(90):
            body = page.inner_text("body")
            # earlier, already-used Approve options stay in the chat (disabled) - only click an enabled one
            opts = page.locator("span.option-label").filter(has_text=APPROVE)
            en = [i for i in range(opts.count()) if opts.nth(i).is_enabled()]
            if en:
                c = re.findall(r"costing (\d+) credits", body)
                c = re.match(r"\d+", c[-1]) if c else None
                opts.nth(en[-1]).click(); spent += int(c.group(0)) if c else 0
                result = f"approved ({c.group(0) if c else "?"} credits)"; break
            if "Something went wrong" in body[-2000:]:
                result = "FLOW AGENT ERROR - start a new session and retry this scene"; break
            time.sleep(1)
        print(f"scene {n}: {result}", flush=True)
        time.sleep(8)
    for _ in range(90):   # wait until nothing is generating
        t = page.inner_text("body")
        if not re.search(r"\b\d{1,3}%", t) and "Thinking" not in t: break
        time.sleep(10)
    print(f"done - approved about {spent} credits", flush=True)
