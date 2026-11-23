"""LinkedIn collector that runs on YOUR computer, logged in as you, with Playwright.

It drives a separate Brave (or Chromium) window with its own profile folder, so your normal
browser is untouched. You log into LinkedIn in that window once; the session is kept in the
profile folder for later runs.

  python collect.py login        # opens the window; log into LinkedIn by hand, then close it
  python collect.py posts        # roster experts + your own profile -> linkedin-remix/data/collected/
  python collect.py roster       # visits candidate profiles (location, followers, headline), monthly
  python collect.py posts --debug  # also saves HTML + screenshot when a page yields 0 posts

Pacing is deliberately slow (one profile every 10 to 20 seconds, a few scrolls each), the way
a person reads. If LinkedIn shows a checkpoint or login page, the run stops; it never retries
around it.
"""
import json
import os
import random
import re
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.realpath(__file__))
SKILL = os.path.dirname(HERE)


def repo_root():
    d = SKILL
    while d != os.path.dirname(d):
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        d = os.path.dirname(d)
    sys.exit("run this from inside your clone of the repo")


ROOT = repo_root()
CFG = json.load(open(os.path.join(SKILL, "config.json")))
DATA = os.path.join(ROOT, CFG["data_dir"], "data")
OUT = os.path.join(DATA, "collected")
PROFILE_DIR = os.path.expanduser(os.environ.get("REMIX_PROFILE_DIR", "~/.linkedin-remix/browser-profile"))
WINDOW_DAYS = CFG["scrape"]["window_days"]

BRAVE_PATHS = [
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    os.path.expandvars(r"%PROGRAMFILES%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    os.path.expandvars(r"%PROGRAMFILES(X86)%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    "/usr/bin/brave-browser", "/usr/bin/brave", "/snap/bin/brave",
]


def browser_exe():
    if os.environ.get("REMIX_BROWSER"):
        return os.environ["REMIX_BROWSER"]
    for p in BRAVE_PATHS:
        if p and os.path.exists(p):
            return p
    return shutil.which("brave") or shutil.which("brave-browser")  # None -> Playwright's Chromium


def open_context(pw, headless):
    os.makedirs(PROFILE_DIR, exist_ok=True)
    # Low-RAM launch: one renderer, no GPU, small JS heap, no background tabs or extensions.
    args = ["--disable-gpu", "--disable-dev-shm-usage", "--renderer-process-limit=2",
            "--js-flags=--max-old-space-size=384", "--disable-extensions", "--disable-background-networking",
            "--disable-features=Translate,MediaRouter,BackForwardCache", "--mute-audio"]
    kw = dict(user_data_dir=PROFILE_DIR, headless=headless, viewport={"width": 1280, "height": 900}, args=args)
    exe = browser_exe()
    if exe:
        kw["executable_path"] = exe
    ctx = pw.chromium.launch_persistent_context(**kw)
    # Never download images, video, audio or fonts: image URLs stay in the page, the bytes are
    # what eat memory (LinkedIn autoplays videos in the activity feed).
    if headless:  # the login window keeps images so LinkedIn's verification steps work
        ctx.route("**/*", lambda r: r.abort() if r.request.resource_type in ("image", "media", "font") else r.continue_())
    for extra in ctx.pages[1:]:
        extra.close()
    return ctx


def fresh_page(ctx, page, n):
    """Every 10 profiles, throw the tab away and start a clean one so memory doesn't pile up."""
    if n % 10:
        return page
    try:
        page.goto("about:blank")
        page.close()
    except Exception:  # noqa: BLE001
        pass
    return ctx.new_page()


def blocked(page):
    u = page.url
    return any(k in u for k in ("/login", "/checkpoint", "/authwall", "/uas/"))


def slug(url):
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url or "")
    return m.group(1).strip("/") if m else ""


def activity_date(urn):
    m = re.search(r"(\d{19})", urn or "")
    if not m:
        return None
    return datetime.fromtimestamp((int(m.group(1)) >> 22) / 1000, timezone.utc)


# Runs inside the page. Several selectors per field because LinkedIn renames classes now and then.
EXTRACT_JS = r"""
() => {
  const num = s => { if (!s) return 0; const m = s.replace(/,/g,'').match(/([\d.]+)\s*([KkMm])?/); if (!m) return 0;
                     let n = parseFloat(m[1]); if (/k/i.test(m[2]||'')) n*=1e3; if (/m/i.test(m[2]||'')) n*=1e6; return Math.round(n); };
  const q = (el, sels) => { for (const s of sels) { const x = el.querySelector(s); if (x) return x; } return null; };
  const cards = [...document.querySelectorAll('[data-urn^="urn:li:activity:"], [data-id^="urn:li:activity:"], [data-activity-urn^="urn:li:activity:"]')]
    .filter(el => !el.parentElement.closest('[data-urn^="urn:li:activity:"], [data-id^="urn:li:activity:"], [data-activity-urn^="urn:li:activity:"]'));
  return cards.map(el => {
    const urn = el.getAttribute('data-urn') || el.getAttribute('data-id') || el.getAttribute('data-activity-urn');
    const header = (q(el, ['.update-components-header', '.feed-shared-header']) || {}).innerText || '';
    const actor = q(el, ['.update-components-actor__meta a', '.update-components-actor__container a', 'a.app-aware-link']);
    const textEl = q(el, ['.update-components-text', '.feed-shared-inline-show-more-text', '.feed-shared-text', '[data-test-id="main-feed-activity-card__commentary"]']);
    const social = q(el, ['.social-details-social-counts', '.update-v2-social-activity', '.social-action-counts']) || el;
    const st = social.innerText || '';
    const react = q(social, ['.social-details-social-counts__reactions-count', '[data-test-id="social-actions__reactions"]', 'button[aria-label*="reaction"]']);
    const cm = st.match(/([\d,.]+[KkMm]?)\s+comments?/i), rp = st.match(/([\d,.]+[KkMm]?)\s+reposts?/i);
    const imgs = [...el.querySelectorAll('.update-components-image img, .feed-shared-image img, img[src*="feedshare"], img[data-delayed-url*="feedshare"]')]
      .map(i => (i.src && i.src.startsWith('http') ? i.src : '') || i.dataset.delayedUrl || '').filter(u => u.includes('feedshare'));
    return {
      urn, header,
      actorUrl: actor ? actor.href.split('?')[0] : '',
      text: textEl ? textEl.innerText.trim() : '',
      likes: (el.querySelector('[data-num-reactions]') ? +el.querySelector('[data-num-reactions]').dataset.numReactions : 0)
             || (react ? num(react.innerText || react.getAttribute('aria-label')) : 0),
      comments: (el.querySelector('[data-num-comments]') ? +el.querySelector('[data-num-comments]').dataset.numComments : 0)
             || (cm ? num(cm[1]) : 0),
      shares: rp ? num(rp[1]) : 0,
      images: [...new Set(imgs)],
      video: !!el.querySelector('video, .update-components-linkedin-video, [data-test-id*="video"]'),
      document: !!el.querySelector('.update-components-document, .document-s-container, iframe[src*="document"]'),
      poll: !!el.querySelector('.update-components-poll, [class*="poll"]'),
    };
  });
}
"""


def expand_and_scroll(page, cutoff, max_scrolls=8):
    for _ in range(max_scrolls):
        for b in page.query_selector_all("button.feed-shared-inline-show-more-text__see-more-less-toggle, "
                                         "button[aria-label*='see more' i]")[:15]:
            try:
                b.click(timeout=800)
            except Exception:  # noqa: BLE001
                pass
        urns = page.eval_on_selector_all('[data-urn^="urn:li:activity:"], [data-id^="urn:li:activity:"], [data-activity-urn^="urn:li:activity:"]', "els => els.map(e => e.dataset.urn || e.dataset.id || e.dataset.activityUrn)")
        dates = [d for d in (activity_date(u) for u in urns) if d]
        if dates and min(dates) < cutoff:
            break
        page.mouse.wheel(0, random.randint(1800, 2600))
        page.wait_for_timeout(random.randint(1800, 3200))


def read_activity(page, profile_url, cutoff, debug=False):
    s = slug(profile_url)
    page.goto(f"https://www.linkedin.com/in/{s}/recent-activity/all/", timeout=45000)
    page.wait_for_timeout(random.randint(2500, 4000))
    if blocked(page):
        raise RuntimeError(f"LinkedIn asked for login/checkpoint at {page.url}")
    expand_and_scroll(page, cutoff)
    raw = page.evaluate(EXTRACT_JS)
    if debug and not raw:
        os.makedirs(os.path.join(OUT, "debug"), exist_ok=True)
        open(os.path.join(OUT, "debug", f"{s}.html"), "w").write(page.content())
        page.screenshot(path=os.path.join(OUT, "debug", f"{s}.png"))
    items = []
    for r in raw:
        when = activity_date(r["urn"])
        if not when or when < cutoff:
            continue
        reposted = "reposted" in r["header"].lower() or (r["actorUrl"] and slug(r["actorUrl"]) and slug(r["actorUrl"]) != s)
        if reposted or not r["text"]:
            continue
        act = re.search(r"(\d{19})", r["urn"]).group(1)
        items.append({
            "id": act,
            "content": r["text"],
            "author": {"linkedinUrl": f"https://www.linkedin.com/in/{s}/"},
            "postedAt": {"date": when.isoformat()},
            "engagement": {"likes": r["likes"], "comments": r["comments"], "shares": r["shares"]},
            "postImages": [{"url": u} for u in r["images"]],
            "postVideo": {"videoUrl": "video"} if r["video"] else None,
            "document": {"transcribedDocumentUrl": f"https://www.linkedin.com/feed/update/urn:li:activity:{act}/"} if r["document"] else None,
            "poll": r["poll"] or None,
            "linkedinUrl": f"https://www.linkedin.com/feed/update/urn:li:activity:{act}/",
        })
    return items


def read_profile(page, url):
    page.goto(url, timeout=45000)
    page.wait_for_timeout(random.randint(2500, 4000))
    if blocked(page):
        raise RuntimeError(f"LinkedIn asked for login/checkpoint at {page.url}")
    return page.evaluate(r"""() => {
      const t = s => (document.querySelector(s) || {}).innerText || '';
      const body = document.body.innerText;
      const f = body.match(/([\d,.]+[KkMm]?)\s+followers/);
      return { name: t('h1'), headline: t('.text-body-medium.break-words'),
               location: t('.text-body-small.inline.t-black--light.break-words') || t('[class*="top-card"] .text-body-small'),
               followers: f ? f[1] : '' };
    }""")


def to_int(s):
    m = re.match(r"([\d.]+)\s*([KkMm])?", (s or "").replace(",", ""))
    if not m:
        return 0
    n = float(m.group(1)) * (1000 if (m.group(2) or "").lower() == "k" else 1_000_000 if (m.group(2) or "").lower() == "m" else 1)
    return int(n)


def main():
    from playwright.sync_api import sync_playwright
    cmd = sys.argv[1] if len(sys.argv) > 1 else "posts"
    debug = "--debug" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as pw:
        if cmd == "login":
            ctx = open_context(pw, headless=False)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://www.linkedin.com/login")
            print("Log into LinkedIn in the Brave window that opened. This finishes by itself once your feed shows "
                  "(waits up to 10 minutes).", flush=True)
            for _ in range(600):
                if "/feed" in page.url or "/in/" in page.url:
                    page.wait_for_timeout(3000)
                    break
                page.wait_for_timeout(1000)
            else:
                ctx.close()
                sys.exit("Timed out waiting for the LinkedIn feed. Run login again.")
            ctx.close()
            print(f"Saved. Session lives in {PROFILE_DIR}")
            return
        ctx = open_context(pw, headless=os.environ.get("REMIX_HEADED") != "1")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            if cmd == "roster":
                cand = json.load(open(os.path.join(DATA, "candidates.json")))
                out = []
                n = 0
                for cat in ("gtm", "pmm"):
                    for c in cand.get(cat, []):
                        if not c.get("linkedin_url"):
                            continue
                        n += 1
                        page = fresh_page(ctx, page, n)
                        info = read_profile(page, c["linkedin_url"])
                        out.append({**c, "category": cat, "name": info["name"] or c["name"], "headline": info["headline"],
                                    "location": info["location"], "followers": to_int(info["followers"])})
                        print(f"{cat} {out[-1]['name']}: {info['location']} / {info['followers']} followers")
                        time.sleep(random.uniform(10, 20))
                json.dump({"collected_at": datetime.now(timezone.utc).isoformat(), "profiles": out},
                          open(os.path.join(OUT, "roster-profiles.json"), "w"), indent=2, ensure_ascii=False)
                return
            cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
            roster = json.load(open(os.path.join(DATA, "roster.json")))
            people = [e for e in roster["experts"] if e.get("tier") == "roster" and e.get("active", True)]
            people += [e for e in roster["experts"] if e.get("tier") == "bench"][:6]  # spares for swaps
            items, failed = [], []
            for i, e in enumerate(people, 1):
                page = fresh_page(ctx, page, i)
                try:
                    got = read_activity(page, e["linkedin_url"], cutoff, debug)
                    items += got
                    print(f"[{i}/{len(people)}] {e['name']}: {len(got)} posts")
                except RuntimeError:
                    raise
                except Exception as ex:  # noqa: BLE001
                    failed.append(e["name"])
                    print(f"[{i}/{len(people)}] {e['name']}: failed ({str(ex)[:80]})")
                time.sleep(random.uniform(10, 20))
            json.dump(items, open(os.path.join(OUT, f"experts-{today}.json"), "w"), indent=2, ensure_ascii=False)
            mine = []
            if not CFG["owner"].get("linkedin_url"):
                page.goto("https://www.linkedin.com/in/me/", timeout=45000)
                page.wait_for_timeout(3000)
                if slug(page.url) and slug(page.url) != "me":
                    CFG["owner"]["linkedin_url"] = f"https://www.linkedin.com/in/{slug(page.url)}/"
                    json.dump(CFG, open(os.path.join(SKILL, "config.json"), "w"), indent=2, ensure_ascii=False)
                    print(f"found your profile: {CFG['owner']['linkedin_url']}")
            if CFG["owner"].get("linkedin_url"):
                mine = read_activity(page, CFG["owner"]["linkedin_url"],
                                     datetime.now(timezone.utc) - timedelta(days=180), debug)
                json.dump(mine, open(os.path.join(OUT, f"self-{today}.json"), "w"), indent=2, ensure_ascii=False)
            json.dump({"collected_at": datetime.now(timezone.utc).isoformat(), "experts_posts": len(items),
                       "self_posts": len(mine), "failed": failed},
                      open(os.path.join(OUT, "latest.json"), "w"), indent=2)
            print(f"done: {len(items)} expert posts, {len(mine)} of yours, {len(failed)} profiles failed")
        finally:
            ctx.close()


if __name__ == "__main__":
    main()
