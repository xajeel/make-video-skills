"""Tiny CDP driver for the Flow Chrome window.
usage: cdp.py shot OUT | goto URL | click X Y | type TEXT | key KEY | upload CSS FILE | eval JS | text | wait SEC
"""
import sys, time
from playwright.sync_api import sync_playwright

cmd, args = sys.argv[1], sys.argv[2:]
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9333")
    ctx = b.contexts[0]
    pages = [pg for pg in ctx.pages if pg.url.startswith("http")] or ctx.pages
    page = pages[-1]
    page.set_default_timeout(20000)
    if cmd == "shot":
        import base64
        cs = ctx.new_cdp_session(page)
        cs.send("Page.bringToFront")
        vw = page.evaluate("[innerWidth, innerHeight]")
        data = cs.send("Page.captureScreenshot", {"format": "png", "fromSurface": True, "clip": {"x":0,"y":0,"width":vw[0],"height":vw[1],"scale":1}})["data"]
        open(args[0], "wb").write(base64.b64decode(data)); print(page.url)
    elif cmd == "goto":
        page.goto(args[0], wait_until="domcontentloaded"); time.sleep(4); print(page.url)
    elif cmd == "click":
        page.mouse.click(float(args[0]), float(args[1])); time.sleep(1.5)
    elif cmd == "clicktext":
        page.get_by_text(args[0], exact=True).last.click(); time.sleep(2); print("clicked", args[0])
    elif cmd == "clickfirst":
        page.get_by_text(args[0]).first.click(); time.sleep(2); print("clicked first", args[0])
    elif cmd == "pick":
        # click picker row whose title starts with args[0] (picker column is x>850 css)
        h = page.evaluate_handle("""(t)=>{const els=[...document.querySelectorAll('*')].filter(e=>e.children.length<=3&&(e.innerText||'').startsWith(t)&&(e.innerText||'').includes('\\n')); for(const e of els){const r=e.getBoundingClientRect(); if(r.x>850&&r.x<900&&r.width>0){e.scrollIntoView({block:'center'}); return e;}} return null}""", args[0])
        el = h.as_element()
        if not el: print("not found"); sys.exit(1)
        el.click(); time.sleep(2); print("picked", args[0])
    elif cmd == "savevideo":
        src = page.evaluate("[...document.querySelectorAll('video')].map(v=>v.currentSrc||v.src).filter(Boolean)[0]")
        r = ctx.request.get(src)
        open(args[0], "wb").write(r.body()); print(r.status, len(r.body()), r.headers.get("content-type"))
    elif cmd == "type":
        page.keyboard.type(args[0], delay=8)
    elif cmd == "key":
        page.keyboard.press(args[0]); time.sleep(1)
    elif cmd == "upload":
        page.set_input_files(args[0], args[1]); time.sleep(3); print("uploaded")
    elif cmd == "eval":
        print(page.evaluate(args[0]))
    elif cmd == "text":
        print(page.inner_text("body")[:4000])
    elif cmd == "wait":
        time.sleep(float(args[0]))
