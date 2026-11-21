"""Scrape expert posts and the owner's own posts.

  python scrape.py experts     # last 30 days for every roster expert, merged into data/posts.json
  python scrape.py self        # owner's own recent posts -> data/my_posts.json

Cost control: the first run (or a run more than 10 days after the last) pulls a full
month; later runs pull only the last week and merge it in, refreshing engagement on
recent posts. Posts older than window_days are dropped from the table.
"""
import sys
from datetime import datetime, timedelta, timezone
from common import CONFIG, load, save, apify_run, normalize_post, profile_key, today

S = CONFIG["scrape"]
R = CONFIG["roster"]


def _cutoff():
    return (datetime.now(timezone.utc) - timedelta(days=S["window_days"])).strftime("%Y-%m-%d")


def _scrape(urls, limit):
    return apify_run(S["posts_actor"], {
        "targetUrls": urls, "maxPosts": S["max_posts_per_profile"], "postedLimit": limit,
        "includeReposts": S["include_reposts"], "includeQuotePosts": True,
        "scrapeReactions": False, "scrapeComments": False}, timeout=1500)


def experts():
    roster = load("roster.json", None)
    if not roster:
        sys.exit("No roster.json yet. Run roster discovery + `roster.py verify` first.")
    store = load("posts.json", {"last_scraped": None, "posts": {}})
    last = store.get("last_scraped")
    limit = "week" if last and (datetime.now(timezone.utc) - datetime.fromisoformat(last)).days <= 10 else "month"
    active = [e for e in roster["experts"] if e["tier"] == "roster" and e.get("active", True)]
    meta = {profile_key(e["linkedin_url"]): e for e in roster["experts"]}

    def ingest(items):
        n = 0
        for it in items:
            key = profile_key((it.get("author") or {}).get("linkedinUrl") or it.get("query") or "")
            if not key:
                key = profile_key(it.get("inputUrl") or "")
            e = meta.get(key, {})
            p = normalize_post(it, e.get("category", ""), e.get("name", ""))
            if p["is_repost"] or not p["text"]:
                continue
            if e:
                p["author"], p["author_url"] = e["name"], e["linkedin_url"]
            prev = store["posts"].get(p["id"], {})
            p["first_seen"] = prev.get("first_seen", today())
            store["posts"][p["id"]] = p
            n += 1
        return n

    print(f"scraping {len(active)} experts (window: {limit})...")
    n = ingest(_scrape([e["linkedin_url"] for e in active], limit))
    cut = _cutoff()
    store["posts"] = {k: v for k, v in store["posts"].items() if (v.get("posted_at") or "9999") >= cut}

    # activity check: swap inactive roster members for bench people (same category)
    if True:  # the store always holds the full 30-day window, so counts are valid every run
        counts = {}
        for p in store["posts"].values():
            counts[profile_key(p["author_url"])] = counts.get(profile_key(p["author_url"]), 0) + 1
        promoted = []
        for e in active:
            if counts.get(profile_key(e["linkedin_url"]), 0) < R["min_posts_last_30_days"]:
                e["active"] = False
                bench = [b for b in roster["experts"] if b["category"] == e["category"]
                         and b["tier"] == "bench" and b.get("active", True)]
                if bench:
                    bench[0]["tier"] = "roster"
                    promoted.append(bench[0])
                print(f"inactive: {e['name']} ({counts.get(profile_key(e['linkedin_url']), 0)} posts)"
                      + (f" -> swapped for {bench[0]['name']}" if bench else " -> no bench left"))
        if promoted:
            n += ingest(_scrape([b["linkedin_url"] for b in promoted], "month"))
            store["posts"] = {k: v for k, v in store["posts"].items() if (v.get("posted_at") or "9999") >= cut}
        save("roster.json", roster)

    store["last_scraped"] = datetime.now(timezone.utc).isoformat()
    save("posts.json", store)
    print(f"ingested {n} posts; table now holds {len(store['posts'])} posts from the last {S['window_days']} days")


def self_posts():
    url = CONFIG["owner"]["linkedin_url"]
    if not url:
        sys.exit("SELF_URL_MISSING: set owner.linkedin_url in config.json")
    items = _scrape([url], S["self_window"])
    mine = load("my_posts.json", {"posts": {}})
    for it in items:
        p = normalize_post(it, "self", CONFIG["owner"]["name"])
        if p["text"]:
            mine["posts"][p["id"]] = p
    mine["last_scraped"] = datetime.now(timezone.utc).isoformat()
    save("my_posts.json", mine)
    print(f"own profile: {len(mine['posts'])} posts on file")


if __name__ == "__main__":
    {"experts": experts, "self": self_posts}[sys.argv[1]]()
