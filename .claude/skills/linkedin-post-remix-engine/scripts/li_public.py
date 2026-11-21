"""Read public LinkedIn post pages with Playwright (no login, no Apify).

  python li_public.py read <urls.txt> [--category gtm|pmm|self]   -> merges into data/posts.json
                                                                     (or my_posts.json for self)

A public post page (linkedin.com/posts/...) carries schema.org JSON-LD with the full text,
publish date, likes, comment count and the author's follower count; images sit in the page.
Shares are not shown to logged-out visitors, so shares = 0 for posts read this way.

Rules: plain visits only, one tab, 3 to 6 seconds apart. If LinkedIn answers with its sign-in
wall or a 999, stop and report it. Never retry around it (no cookie clearing, no new
contexts, no user-agent changes).
"""
import json
import random
import re
import sys
import time
import os
from datetime import datetime, timedelta, timezone

from common import CONFIG, load, save, today

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "..", "browser"))


def _page():
    try:
        from pwb import browser
        return browser().contexts[0].new_page()
    except Exception:  # noqa: BLE001
        from playwright.sync_api import sync_playwright
        return sync_playwright().start().chromium.launch().new_page()


def activity_date(url):
    """LinkedIn activity ids encode the post time: id >> 22 = epoch ms."""
    m = re.search(r"activity[-:](\d{19})", url)
    if not m:
        return ""
    return datetime.fromtimestamp((int(m.group(1)) >> 22) / 1000, timezone.utc).strftime("%Y-%m-%d")


def parse(html, url):
    ld = None
    for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            d = json.loads(m)
        except ValueError:
            continue
        if d.get("@type") in ("SocialMediaPosting", "DiscussionForumPosting", "Article", "VideoObject"):
            ld = d
            break
    if not ld:
        return None
    stats = {s.get("interactionType", "").rsplit("/", 1)[-1]: s.get("userInteractionCount", 0)
             for s in (ld.get("interactionStatistic") or []) if isinstance(s, dict)}
    likes = stats.get("LikeAction") or int((re.findall(r'data-num-reactions="(\d+)"', html) or [0])[0])
    comments = stats.get("CommentAction") or ld.get("commentCount") or 0
    author = ld.get("author") or {}
    i = html.find("main-feed-activity-card")
    card = html[i:i + 80000] if i >= 0 else html
    media = list(dict.fromkeys(re.findall(r'(?:src|data-delayed-url)="(https://media\.licdn\.com/dms/image/[^"]*feedshare[^"]*)"', card)))
    media = [u.replace("&amp;", "&") for u in media]
    if re.search(r"<video|data-sources=|video-js|feed-video", card):
        mtype = "video"
    elif re.search(r"native-document|document-s-container|feed-shared-document", card):
        mtype = "carousel"
    elif any("gif" in u.lower() for u in media):
        mtype = "gif"
    elif media:
        mtype = "image" if len(media) == 1 else "multi-image"
    else:
        mtype = "text"
    return {
        "id": (re.search(r"activity[-:](\d{19})", url) or re.search(r"(.*)", url)).group(1),
        "content": ld.get("articleBody") or ld.get("headline") or "",
        "author": {"name": author.get("name", ""), "linkedinUrl": (author.get("url") or "").rstrip("/") + "/",
                   "followers": (author.get("interactionStatistic") or {}).get("userInteractionCount")},
        "postedAt": {"date": ld.get("datePublished") or activity_date(url)},
        "engagement": {"likes": int(likes or 0), "comments": int(comments or 0), "shares": 0},
        "postImages": [{"url": u} for u in media] if mtype not in ("video",) else [],
        "postVideo": {"videoUrl": url} if mtype == "video" else None,
        "document": {"transcribedDocumentUrl": url} if mtype == "carousel" else None,
        "linkedinUrl": url.split("?")[0],
    }


def read(urls, category=""):
    from common import normalize_post
    page = _page()
    out, blocked = [], None
    try:
        for n, url in enumerate(urls):
            r = page.goto(url, timeout=30000)
            page.wait_for_load_state("load")
            page.wait_for_timeout(1500)
            if "authwall" in page.url or "/login" in page.url or (r and r.status == 999):
                blocked = f"LinkedIn sign-in wall at post {n + 1} of {len(urls)} ({url})"
                break
            it = parse(page.content(), url)
            if it:
                p = normalize_post(it, category)
                p["author_followers"] = it["author"].get("followers")
                out.append(p)
            else:
                print(f"no post data on {url}", file=sys.stderr)
            time.sleep(random.uniform(3, 6))
    finally:
        page.close()
    if blocked:
        print("STOPPED: " + blocked + ". Not retrying around it.", file=sys.stderr)
    return out


def main():
    src = sys.argv[2]
    cat = sys.argv[sys.argv.index("--category") + 1] if "--category" in sys.argv else ""
    urls = [l.strip() for l in open(src) if l.strip().startswith("https://www.linkedin.com/")]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=CONFIG["scrape"]["window_days"])).strftime("%Y-%m-%d")
    fresh = [u for u in urls if (activity_date(u) or "9999") >= cutoff]
    print(f"{len(urls)} links, {len(fresh)} inside the {CONFIG['scrape']['window_days']}-day window")
    name = "my_posts.json" if cat == "self" else "posts.json"
    store = load(name, {"posts": {}})
    roster = {e["linkedin_url"].rstrip("/").lower(): e for e in load("roster.json", {"experts": []})["experts"]}
    posts = read(fresh, cat)
    for p in posts:
        e = roster.get(p["author_url"].rstrip("/").lower())
        if e and not cat:
            p["category"] = e["category"]
        prev = store["posts"].get(p["id"], {})
        p["first_seen"] = prev.get("first_seen", today())
        store["posts"][p["id"]] = p
    store["posts"] = {k: v for k, v in store["posts"].items() if (v.get("posted_at") or "9999") >= cutoff or cat == "self"}
    store["last_scraped"] = datetime.now(timezone.utc).isoformat()
    save(name, store)
    print(f"read {len(posts)} posts; {name} now holds {len(store['posts'])}")


if __name__ == "__main__":
    main()
