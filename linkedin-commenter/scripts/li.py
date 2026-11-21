#!/usr/bin/env python3
"""LinkedIn browser helper for the GTM commenting routine.

Runs on YOUR computer (LinkedIn blocks cloud browsers). Uses a dedicated, persistent
browser profile so you log in once and the session is reused by every scheduled run.

Every command prints one JSON object to stdout.

  python3 li.py login                       # opens a visible browser; log in by hand once
  python3 li.py check                       # {"logged_in": true/false}
  python3 li.py resolve "Name" "Company"    # top people-search matches -> profile URLs
  python3 li.py profile URL                 # headline, location, follower count
  python3 li.py latest URL [--n 3]          # creator's most recent original posts
  python3 li.py comment POST_URL FILE       # post the comment text stored in FILE
  python3 li.py comment POST_URL FILE --dry-run   # fill the box but do not submit

Setup:  pip install playwright && python3 -m playwright install chromium
Env:    LI_PROFILE_DIR (default ~/.linkedin-commenter/profile)
        LI_HEADLESS=1 to hide the window (visible is the default; it is less likely to be flagged)
"""
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

PROFILE = Path(os.environ.get("LI_PROFILE_DIR", Path.home() / ".linkedin-commenter" / "profile"))
HEADLESS = os.environ.get("LI_HEADLESS") == "1"
SHOTS = Path(__file__).resolve().parent.parent / "state" / "screenshots"


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def human_pause(lo=0.8, hi=2.2):
    time.sleep(random.uniform(lo, hi))


def open_ctx(pw, headless=None):
    PROFILE.mkdir(parents=True, exist_ok=True)
    kw = dict(
        user_data_dir=str(PROFILE),
        headless=HEADLESS if headless is None else headless,
        viewport={"width": 1366, "height": 900},
        locale="en-US",
    )
    try:  # prefer the real Google Chrome if installed
        return pw.chromium.launch_persistent_context(channel="chrome", **kw)
    except Exception:
        return pw.chromium.launch_persistent_context(**kw)


def page_of(ctx):
    return ctx.pages[0] if ctx.pages else ctx.new_page()


def shot(p, name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    f = SHOTS / f"{time.strftime('%Y%m%d-%H%M%S')}-{name}.png"
    try:
        p.screenshot(path=str(f))
    except Exception:
        return None
    return str(f)


def is_logged_in(p):
    p.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
    human_pause(2, 3)
    u = p.url
    return "/feed" in u and "login" not in u and "checkpoint" not in u and "authwall" not in u


def scroll(p, times=3):
    for _ in range(times):
        p.mouse.wheel(0, random.randint(700, 1100))
        human_pause(0.8, 1.6)


# ---------------------------------------------------------------- commands

def cmd_login(pw, _args):
    ctx = open_ctx(pw, headless=False)
    p = page_of(ctx)
    p.goto("https://www.linkedin.com/login")
    print("Log in to LinkedIn in the opened window (complete any 2FA). Waiting up to 5 minutes...",
          file=sys.stderr)
    deadline = time.time() + 300
    while time.time() < deadline:
        if "/feed" in p.url:
            break
        time.sleep(2)
    ok = "/feed" in p.url
    ctx.close()
    out({"logged_in": ok, "profile_dir": str(PROFILE)})


def cmd_check(pw, _args):
    ctx = open_ctx(pw)
    p = page_of(ctx)
    ok = is_logged_in(p)
    res = {"logged_in": ok, "url": p.url}
    if not ok:
        res["screenshot"] = shot(p, "not-logged-in")
    ctx.close()
    out(res)


def cmd_resolve(pw, args):
    name, company = args[0], (args[1] if len(args) > 1 else "")
    ctx = open_ctx(pw)
    p = page_of(ctx)
    q = quote(f"{name} {company}".strip())
    p.goto(f"https://www.linkedin.com/search/results/people/?keywords={q}", wait_until="domcontentloaded")
    human_pause(3, 4.5)
    results = p.evaluate(r"""() => {
      const seen = new Set(), res = [];
      for (const a of document.querySelectorAll('a[href*="/in/"]')) {
        const m = a.href.match(/https:\/\/www\.linkedin\.com\/in\/[^/?#]+/);
        if (!m || seen.has(m[0])) continue;
        const card = a.closest('li') || a.closest('div');
        const text = (card ? card.innerText : a.innerText).trim().replace(/\n+/g, ' | ');
        if (!text) continue;
        seen.add(m[0]); res.push({url: m[0] + '/', card: text.slice(0, 300)});
        if (res.length >= 5) break;
      }
      return res;
    }""")
    ctx.close()
    out({"query": f"{name} {company}", "matches": results})


def _profile_info(p, url):
    p.goto(url, wait_until="domcontentloaded")
    human_pause(2.5, 4)
    body = p.inner_text("body")
    followers = None
    m = re.search(r"([\d,.]+)\s*([KkMm]?)\s+followers", body)
    if m:
        n = float(m.group(1).replace(",", ""))
        mult = {"k": 1e3, "m": 1e6}.get(m.group(2).lower(), 1)
        followers = int(n * mult)
    name = (p.locator("h1").first.inner_text() if p.locator("h1").count() else "").strip()
    return {"url": url, "name": name, "followers": followers, "top_text": body[:600]}


def cmd_profile(pw, args):
    ctx = open_ctx(pw)
    p = page_of(ctx)
    info = _profile_info(p, args[0])
    ctx.close()
    out(info)


def cmd_latest(pw, args):
    url = args[0].rstrip("/")
    n = int(args[args.index("--n") + 1]) if "--n" in args else 3
    ctx = open_ctx(pw)
    p = page_of(ctx)
    p.goto(url + "/recent-activity/all/", wait_until="domcontentloaded")
    human_pause(3, 4.5)
    scroll(p, 2)
    posts = p.evaluate(r"""(n) => {
      const res = [];
      const nodes = document.querySelectorAll('[data-urn^="urn:li:activity:"], [data-id^="urn:li:activity:"]');
      for (const el of nodes) {
        const urn = el.getAttribute('data-urn') || el.getAttribute('data-id');
        if (res.find(r => r.urn === urn)) continue;
        const all = el.innerText || '';
        const header = all.slice(0, 250).toLowerCase();
        const isRepost = header.includes('reposted') || header.includes('reposted this');
        const isCommentActivity = header.includes('commented on') || header.includes('likes this')
                                  || header.includes('celebrates') || header.includes('loves this')
                                  || header.includes('finds this');
        const textEl = el.querySelector('.update-components-text, .feed-shared-update-v2__description, .feed-shared-inline-show-more-text');
        const text = (textEl ? textEl.innerText : all).trim();
        const timeEl = el.querySelector('.update-components-actor__sub-description, .feed-shared-actor__sub-description');
        const am = timeEl ? timeEl.innerText.trim().match(/^\d+\s*(s|m|h|d|w|mo|yr|y)\b/i) : null;
        const age = am ? am[0].replace(/\s+/g, '') : (timeEl ? timeEl.innerText.trim().slice(0, 12) : '');
        res.push({urn, post_url: 'https://www.linkedin.com/feed/update/' + urn + '/',
                  age, is_repost: isRepost, is_other_activity: isCommentActivity,
                  text: text.slice(0, 4000)});
        if (res.length >= n * 3) break;
      }
      return res;
    }""", n)
    originals = [x for x in posts if not x["is_repost"] and not x["is_other_activity"]][:n]
    res = {"profile": url, "posts": originals, "skipped_non_original": len(posts) - len(originals)}
    if not posts:
        res["screenshot"] = shot(p, "no-posts-found")
    ctx.close()
    out(res)


COMMENT_BOX = [
    ".comments-comment-box__form .ql-editor",
    "div.ql-editor[contenteditable='true']",
    "div.comments-comment-texteditor div[contenteditable='true']",
    "div[role='textbox'][contenteditable='true']",
]
SUBMIT_BTN = [
    "button.comments-comment-box__submit-button--cr",
    "button.comments-comment-box__submit-button",
    ".comments-comment-box__form button[type='submit']",
    "button:has-text('Comment'):not([aria-label*='Comment on'])",
    "button:has-text('Post')",
]


def _first(p, selectors, timeout=4000):
    for s in selectors:
        loc = p.locator(s).first
        try:
            loc.wait_for(state="visible", timeout=timeout)
            return loc
        except PWTimeout:
            continue
    return None


def cmd_comment(pw, args):
    post_url, text_file = args[0], args[1]
    dry = "--dry-run" in args
    text = Path(text_file).read_text(encoding="utf-8").strip()
    if not text:
        return out({"ok": False, "error": "empty comment text"})
    ctx = open_ctx(pw)
    p = page_of(ctx)
    p.goto(post_url, wait_until="domcontentloaded")
    human_pause(3, 5)
    scroll(p, 1)
    box = _first(p, COMMENT_BOX)
    if box is None:  # the box often appears only after clicking the Comment action
        btn = _first(p, ["button[aria-label='Comment']", "button:has-text('Comment')"], 3000)
        if btn:
            btn.click()
            human_pause()
        box = _first(p, COMMENT_BOX, 6000)
    if box is None:
        res = {"ok": False, "error": "comment box not found", "screenshot": shot(p, "no-comment-box")}
        ctx.close()
        return out(res)
    box.click()
    human_pause(0.6, 1.2)
    for i, line in enumerate(text.split("\n")):
        if i:
            p.keyboard.press("Shift+Enter")
        p.keyboard.type(line, delay=random.randint(25, 60))
    human_pause(1, 2)
    if dry:
        res = {"ok": True, "dry_run": True, "screenshot": shot(p, "dry-run")}
        ctx.close()
        return out(res)
    btn = _first(p, SUBMIT_BTN, 4000)
    if btn is None:
        res = {"ok": False, "error": "submit button not found", "screenshot": shot(p, "no-submit")}
        ctx.close()
        return out(res)
    btn.click()
    human_pause(3, 5)
    snippet = text[:60]
    posted = snippet.split("\n")[0][:40] in p.inner_text("body")
    res = {"ok": posted, "post_url": post_url, "verified_on_page": posted}
    if not posted:
        res["screenshot"] = shot(p, "unverified")
    ctx.close()
    out(res)


CMDS = {"login": cmd_login, "check": cmd_check, "resolve": cmd_resolve, "profile": cmd_profile,
        "latest": cmd_latest, "comment": cmd_comment}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__)
        sys.exit(1)
    with sync_playwright() as pw:
        CMDS[sys.argv[1]](pw, sys.argv[2:])
