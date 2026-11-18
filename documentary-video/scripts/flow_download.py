"""Download finished Flow videos (720p original) by their Flow title.

Usage:
  python flow_download.py --project <id> "Monks walk toward church=clips/scene01.mp4" "Tide water flows=clips/scene02.mp4"
Titles are the names Flow gives each video (shown in the editor's top strip); a prefix is enough.
Run with ~/.local/share/uv/tools/gflow-cli/bin/python. Free (no credits).
"""
import argparse, time
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--project", required=True)
ap.add_argument("pairs", nargs="+")
a = ap.parse_args()

with sync_playwright() as p:
    ctx = p.chromium.connect_over_cdp("http://127.0.0.1:9333").contexts[0]
    page = [pg for pg in ctx.pages if "flow.google.com" in pg.url][-1]
    page.set_default_timeout(60000)
    page.goto(f"https://flow.google.com/project/{a.project}", wait_until="domcontentloaded"); time.sleep(5)
    page.get_by_text("Videos", exact=True).first.click(); time.sleep(4)
    page.locator('img[alt="Generated video thumbnail"]').first.click(force=True); time.sleep(6)  # opens the editor
    for pair in a.pairs:
        title, out = pair.split("=", 1)
        page.locator(f'button[aria-label^="{title}"]').first.click(); time.sleep(4)
        page.locator('button[aria-label*="ownload" i]').first.click(); time.sleep(2)
        with page.expect_download(timeout=120000) as d:
            page.get_by_text("Original size").first.click()
        d.value.save_as(out); print(title, "->", out, flush=True)
        time.sleep(2)
