"""Download the newest Flow videos (720p original) and file each one under the scene it animates.

Flow gives the clips near-identical titles ("Animate embroidered tapestry int..."), so instead of titles this
downloads the N newest videos and matches each clip's first frame to parts/partNN/images/sceneNN.jpg.

Usage (run with ~/.local/share/uv/tools/gflow-cli/bin/python; free, no credits):
  flow_download.py --project <flow_project_id> --part parts/partNN 1 2 4 6   # scenes from: project.py clips <project> N
Writes parts/partNN/clips/sceneNN.mp4 and prints the match distance (small = sure, ~4; others ~35+).
"""
import argparse, os, subprocess, tempfile, time
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--project", required=True)
ap.add_argument("--part", required=True)
ap.add_argument("numbers", nargs="+", type=int)
a = ap.parse_args()
part = os.path.abspath(a.part)
tmp = tempfile.mkdtemp()

def gray(src, seek=None):
    cmd = ["ffmpeg", "-v", "error"] + (["-ss", seek] if seek else []) + ["-i", src, "-frames:v", "1",
           "-vf", "scale=64:36", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    return subprocess.run(cmd, capture_output=True, check=True).stdout

with sync_playwright() as p:
    ctx = p.chromium.connect_over_cdp("http://127.0.0.1:9333").contexts[0]
    page = [pg for pg in ctx.pages if "flow.google.com" in pg.url][-1]
    page.set_default_timeout(60000)
    page.goto(f"https://flow.google.com/project/{a.project}", wait_until="domcontentloaded"); time.sleep(5)
    page.get_by_text("Videos", exact=True).first.click(); time.sleep(4)
    page.locator('img[alt="Generated video thumbnail"]').first.click(force=True); time.sleep(6)  # editor, newest first
    for i in range(len(a.numbers)):
        if i:
            page.keyboard.press("ArrowRight"); time.sleep(4)
        page.locator('button[aria-label*="ownload" i]').first.click(); time.sleep(2)
        with page.expect_download(timeout=120000) as d:
            page.get_by_text("Original size").first.click()
        d.value.save_as(f"{tmp}/v{i}.mp4"); time.sleep(2)

imgs = {n: gray(f"{part}/images/scene{n:02d}.jpg") for n in a.numbers}
os.makedirs(f"{part}/clips", exist_ok=True)
for i in range(len(a.numbers)):
    f = gray(f"{tmp}/v{i}.mp4", "0.1")
    dist = sorted((sum(abs(x - y) for x, y in zip(f, im)) / len(f), n) for n, im in imgs.items())
    d, n = dist[0]
    os.replace(f"{tmp}/v{i}.mp4", f"{part}/clips/scene{n:02d}.mp4")
    print(f"video {i} -> scene{n:02d}.mp4  (distance {d:.1f}, next {dist[1][0]:.1f})", flush=True)
