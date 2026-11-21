"""Render a brand visual (HTML) to PNG, or to an animated GIF.

  python render.py visual.html out.png
  python render.py visual.html out.gif          # page must define window.FRAMES and window.setFrame(i)

Canvas is 1080x1350 (LinkedIn portrait) unless the page sets <body data-w data-h>.
PNG is captured at 2x for crispness; GIF at 1x (file size).
Reuses the session's persistent Chromium over CDP (see repo CLAUDE.md); falls back to
launching Playwright Chromium if that is not available.
"""
import io
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.realpath(__file__))


def _context():
    sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "browser"))
    try:
        from pwb import browser  # persistent browser
        return browser().contexts[0], None
    except Exception:  # noqa: BLE001
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        b = pw.chromium.launch()
        return b.new_context(), b


def _fill(src):
    """Replace {{ASSETS}}, {{NAME}}, {{TITLE}}, {{SECONDARY}} so every visual gets the same footer."""
    import json
    skill = os.path.dirname(HERE)
    cfg = json.load(open(os.path.join(skill, "config.json")))["owner"]
    html = open(src).read()
    for k, v in {"{{ASSETS}}": "file://" + os.path.join(skill, "assets"), "{{NAME}}": cfg["name"],
                 "{{TITLE}}": cfg["title"], "{{SECONDARY}}": cfg["secondary_line"]}.items():
        html = html.replace(k, v)
    tmp = os.path.join(os.path.dirname(os.path.abspath(src)), "." + os.path.basename(src) + ".render.html")
    open(tmp, "w").write(html)
    return tmp


def main(src, out):
    src = _fill(src)
    ctx, owned = _context()
    page = ctx.new_page()
    try:
        page.set_viewport_size({"width": 1080, "height": 1350})
        page.goto("file://" + os.path.abspath(src))
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts.ready")
        w = page.evaluate("+document.body.dataset.w || 1080")
        h = page.evaluate("+document.body.dataset.h || 1350")
        page.set_viewport_size({"width": w, "height": h})
        if out.endswith(".gif"):
            n = page.evaluate("window.FRAMES || 0")
            if not n:
                sys.exit("GIF needs window.FRAMES and window.setFrame(i) in the page")
            ms = page.evaluate("window.FRAME_MS || 900")
            frames = []
            for i in range(n):
                page.evaluate(f"window.setFrame({i})")
                page.wait_for_timeout(60)
                frames.append(Image.open(io.BytesIO(page.screenshot(clip={"x": 0, "y": 0, "width": w, "height": h}))).convert("RGB"))
            hold = page.evaluate("window.HOLD_LAST_MS || 2200")
            durations = [ms] * (n - 1) + [hold]
            pal = [f.quantize(colors=128, method=Image.Quantize.MEDIANCUT) for f in frames]
            pal[0].save(out, save_all=True, append_images=pal[1:], duration=durations, loop=0, optimize=True)
            print(f"{out}: {n} frames, {os.path.getsize(out) // 1024} KB")
        else:
            cdp = ctx.new_cdp_session(page)
            cdp.send("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 2, "mobile": False})
            page.screenshot(path=out, clip={"x": 0, "y": 0, "width": w, "height": h})
            print(f"{out}: {w * 2}x{h * 2}")
    finally:
        page.close()
        os.remove(src)
        if owned:
            owned.close()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
