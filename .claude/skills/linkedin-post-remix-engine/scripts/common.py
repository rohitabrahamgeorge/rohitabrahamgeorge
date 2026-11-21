"""Shared helpers: paths, config, JSON state, Apify REST client, post normalizer."""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def repo_root():
    d = SKILL_DIR
    while d != "/":
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        d = os.path.dirname(d)
    return os.getcwd()


CONFIG = json.load(open(os.path.join(SKILL_DIR, "config.json")))
DATA_DIR = os.path.join(repo_root(), CONFIG["data_dir"], "data")
RUNS_DIR = os.path.join(repo_root(), CONFIG["data_dir"], "runs")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RUNS_DIR, exist_ok=True)


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def run_dir(date=None):
    d = os.path.join(RUNS_DIR, date or today())
    os.makedirs(d, exist_ok=True)
    return d


def load(name, default):
    p = os.path.join(DATA_DIR, name)
    if not os.path.exists(p):
        return default
    with open(p) as f:
        return json.load(f)


def save(name, obj):
    p = os.path.join(DATA_DIR, name)
    with open(p, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    return p


# ---------------------------------------------------------------- Apify REST

APIFY = "https://api.apify.com/v2"


def _token():
    # In Claude cloud sessions the network proxy injects the saved Apify
    # credential for api.apify.com, so a placeholder is fine. Locally, set
    # APIFY_TOKEN.
    return os.environ.get("APIFY_TOKEN") or "proxy-injected"


def apify_run(actor, payload, timeout=900):
    """Run an actor synchronously and return its dataset items.

    Uses run-sync-get-dataset-items (waits up to 300s on Apify's side); for
    longer runs it falls back to start + poll.
    """
    if os.environ.get("APIFY_DRY"):
        # Prints what to run through the Apify connector, then stops.
        print(json.dumps({"actor": actor.replace("~", "/"), "input": payload}, indent=2))
        sys.exit(0)
    if os.environ.get("APIFY_ITEMS"):
        # Connector path: Claude ran the actor through the Apify MCP connector and saved the
        # dataset items to this JSON file; the scripts just read them.
        print(f"using items from {os.environ['APIFY_ITEMS']} instead of calling {actor}", file=sys.stderr)
        return json.load(open(os.environ["APIFY_ITEMS"]))
    headers = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}
    body = json.dumps(payload).encode()
    url = f"{APIFY}/acts/{actor}/runs"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        run = json.load(urllib.request.urlopen(req, timeout=60))["data"]
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:500]
        if e.code in (401, 403):
            sys.exit(f"APIFY_AUTH: Apify refused the request ({e.code}). Use the Apify connector path "
                     f"(SKILL.md Phase 0) or save an Apify token for api.apify.com. {msg}")
        raise SystemExit(f"Apify error {e.code}: {msg}")
    run_id, ds = run["id"], run["defaultDatasetId"]
    t0 = time.time()
    while True:
        st = json.load(urllib.request.urlopen(urllib.request.Request(
            f"{APIFY}/actor-runs/{run_id}", headers=headers), timeout=60))["data"]["status"]
        if st in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break
        if time.time() - t0 > timeout:
            print(f"warning: run {run_id} still {st} after {timeout}s, reading partial data", file=sys.stderr)
            break
        time.sleep(10)
    if st not in ("SUCCEEDED",):
        print(f"warning: run {run_id} ended {st}", file=sys.stderr)
    items, offset = [], 0
    while True:
        r = urllib.request.Request(f"{APIFY}/datasets/{ds}/items?clean=true&format=json&limit=1000&offset={offset}",
                                   headers=headers)
        page = json.load(urllib.request.urlopen(r, timeout=120))
        items += page
        if len(page) < 1000:
            break
        offset += 1000
    return items


# ---------------------------------------------------------------- normalizer

def _g(d, *path, default=None):
    for k in path:
        if isinstance(d, dict):
            d = d.get(k)
        elif isinstance(d, list) and isinstance(k, int) and len(d) > k:
            d = d[k]
        else:
            return default
    return default if d is None else d


def profile_key(url):
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url or "")
    return (m.group(1) if m else (url or "")).lower().strip("/")


def hook_of(text):
    """The hook is what shows above '...see more': the first 1-2 lines (max ~210 chars)."""
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    if not lines:
        return ""
    hook = lines[0]
    if len(hook) < 60 and len(lines) > 1:
        hook = hook + "\n" + lines[1]
    return hook[:210]


def media_of(it):
    """Return (media_type, [urls]). Types: gif, image, carousel, video, article, poll, text."""
    imgs = it.get("postImages") or it.get("images") or []
    urls = []
    for im in imgs:
        u = im.get("url") if isinstance(im, dict) else im
        if u:
            urls.append(u)
    doc = it.get("document")
    vid = it.get("postVideo") or it.get("video") or it.get("videos")
    art = it.get("article")
    if vid:
        v = vid[0] if isinstance(vid, list) and vid else vid
        u = (v.get("videoUrl") or v.get("thumbnailUrl") or v.get("url")) if isinstance(v, dict) else v
        return "video", [u] if u else []
    if doc:
        cover = []
        for cp in doc.get("coverPages") or []:
            cover += cp.get("imageUrls", [])[:1]
        return "carousel", [doc.get("transcribedDocumentUrl")] + cover[:3] if doc.get("transcribedDocumentUrl") else cover[:3]
    if urls:
        if any(".gif" in u.lower() or "gif" in u.lower().split("?")[0][-12:] for u in urls):
            return "gif", urls
        return ("image" if len(urls) == 1 else "multi-image"), urls
    if it.get("poll"):
        return "poll", []
    if art:
        return "article", [art.get("link") or art.get("url") or ""]
    return "text", []


def normalize_post(it, category="", roster_name=""):
    text = it.get("content") or it.get("text") or it.get("commentary") or ""
    eng = it.get("engagement") or {}
    likes = int(eng.get("likes") or it.get("numLikes") or it.get("likesCount") or 0)
    comments = int(eng.get("comments") or it.get("numComments") or it.get("commentsCount") or 0)
    shares = int(eng.get("shares") or it.get("numShares") or it.get("repostsCount") or 0)
    w = CONFIG["engagement_weights"]
    mtype, murls = media_of(it)
    author = it.get("author") or {}
    date = _g(it, "postedAt", "date") or it.get("postedAtISO") or it.get("date") or ""
    return {
        "id": str(it.get("id") or it.get("urn") or it.get("linkedinUrl")),
        "category": category,
        "author": author.get("name") or roster_name,
        "author_url": (author.get("linkedinUrl") or "").split("?")[0],
        "author_headline": author.get("info") or author.get("headline") or "",
        "posted_at": date[:10],
        "hook": hook_of(text),
        "text": text,
        "media_type": mtype,
        "media_urls": [u for u in murls if u],
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "score": likes * w["likes"] + comments * w["comments"] + shares * w["shares"],
        "url": it.get("linkedinUrl") or it.get("url") or _g(it, "socialContent", "shareUrl", default=""),
        "is_repost": bool(it.get("repostedBy") or it.get("isRepost") or it.get("resharedPost")) and not text,
    }


STOP = set("""the and for that with this you your are was were have has had not but from they them their what when
where which who will would can could should just than then into out about more most some such only also over very
our ours its it's i'm i've don't can't how all any one two get got make made like been being does did doing because
there here these those each other much many own same too why yes now new way ways want really thing things""".split())


def tokens(text):
    return {w for w in re.findall(r"[a-z0-9']{3,}", (text or "").lower()) if w not in STOP}


def shingles(text, n=3):
    w = re.findall(r"[a-z0-9']+", (text or "").lower())
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def similarity(a, b):
    """0..1 score for 'b is a copy or close remix of a'.

    Max of (a) 3-word-shingle containment, scaled so 30 percent shared phrases = 1.0, and
    (b) content-word containment discounted so two posts merely on the same topic stay low.
    """
    sa, sb = shingles(a), shingles(b)
    sh = len(sa & sb) / min(len(sa), len(sb)) if sa and sb else 0.0
    ta, tb = tokens(a), tokens(b)
    wd = len(ta & tb) / min(len(ta), len(tb)) if ta and tb else 0.0
    return round(min(1.0, max(sh / 0.3, (wd - 0.35) / 0.4 if wd > 0.35 else 0.0)), 3)
