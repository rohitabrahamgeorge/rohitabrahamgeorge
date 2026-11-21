"""Build or refresh the expert roster from data/candidates.json.

  python roster.py status          # is a refresh due? prints counts and age
  python roster.py verify          # enrich candidates via Apify, keep top N US per category
  python roster.py resolve         # find missing LinkedIn URLs by name (Apify search-by-name)

Verification rules (config.json -> roster): US location, not excluded, follower floor.
Posting activity is applied later by scrape.py (people with < min_posts_last_30_days
are flagged 'inactive' and swapped for the next-best verified candidate).
"""
import json
import re
import sys
from datetime import datetime, timezone
from common import CONFIG, load, save, apify_run, profile_key

R = CONFIG["roster"]


def excluded(name):
    n = (name or "").lower()
    return any(x.lower() in n for x in R["exclude_names"])


def status():
    roster = load("roster.json", {})
    if not roster:
        print("ROSTER: missing -> refresh needed")
        return
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(roster["verified_at"])).days
    counts = {c: len([p for p in roster["experts"] if p["category"] == c and p.get("active", True)])
              for c in R["categories"]}
    due = age >= R["refresh_every_days"] or any(v < R["per_category"] for v in counts.values())
    print(f"ROSTER: age {age}d, active counts {counts}, refresh {'NEEDED' if due else 'not needed'}")


def resolve():
    cand = load("candidates.json", {})
    changed = 0
    for cat in R["categories"]:
        for c in cand.get(cat, []):
            if c.get("linkedin_url") or excluded(c["name"]):
                continue
            parts = c["name"].split()
            items = apify_run("harvestapi~linkedin-profile-search-by-name", {
                "profileScraperMode": "Short", "firstName": parts[0], "lastName": parts[-1],
                "locations": ["United States"], "maxItems": 3, "strictSearch": True})
            hint = (c.get("headline_or_company") or "").lower().split()
            best = None
            for it in items:
                hl = (it.get("headline") or "").lower()
                if not best or any(w in hl for w in hint if len(w) > 3):
                    best = it
            if best and best.get("linkedinUrl"):
                c["linkedin_url"] = best["linkedinUrl"].split("?")[0]
                c["resolved_by"] = "search-by-name"
                changed += 1
    save("candidates.json", cand)
    print(f"resolved {changed} URLs")


def verify():
    cand = load("candidates.json", {})
    old = {profile_key(p["linkedin_url"]): p for p in load("roster.json", {}).get("experts", [])}
    pool = []
    for cat in R["categories"]:
        for c in cand.get(cat, []):
            if c.get("linkedin_url") and not excluded(c["name"]):
                pool.append((cat, c))
    urls = sorted({c["linkedin_url"] for _, c in pool})
    print(f"enriching {len(urls)} profiles...")
    items = apify_run(CONFIG["scrape"]["profile_actor"], {
        "profileScraperMode": "Profile details no email ($4 per 1k)", "urls": urls})
    by_key = {}
    for it in items:
        for k in (it.get("publicIdentifier"), profile_key(it.get("linkedinUrl", ""))):
            if k:
                by_key[k.lower()] = it
    experts, rejected, seen = [], [], set()
    for cat, c in pool:
        k = profile_key(c["linkedin_url"])
        if k in seen:
            continue
        seen.add(k)
        it = by_key.get(k)
        if not it:
            rejected.append({**c, "category": cat, "reason": "profile not returned"})
            continue
        loc = it.get("location") or {}
        country = (loc.get("countryCode") or (loc.get("parsed") or {}).get("countryCode") or "").upper()
        loc_text = loc.get("linkedinText") or ""
        followers = int(it.get("followerCount") or 0)
        name = f"{it.get('firstName', '')} {it.get('lastName', '')}".strip() or c["name"]
        rec = {"name": name, "category": cat, "linkedin_url": f"https://www.linkedin.com/in/{k}/",
               "headline": it.get("headline", ""), "location": loc_text, "followers": followers,
               "active": old.get(k, {}).get("active", True)}
        if excluded(name):
            rejected.append({**rec, "reason": "excluded by name"})
        elif country != "US" and "United States" not in loc_text:
            rejected.append({**rec, "reason": f"not US ({loc_text or 'unknown'})"})
        elif followers < R["min_followers"]:
            rejected.append({**rec, "reason": f"followers {followers} < {R['min_followers']}"})
        else:
            experts.append(rec)
    # keep top N per category by followers, rest become bench (swapped in when someone is inactive)
    final = []
    for cat in R["categories"]:
        group = sorted([e for e in experts if e["category"] == cat], key=lambda e: -e["followers"])
        for i, e in enumerate(group):
            e["tier"] = "roster" if i < R["per_category"] else "bench"
            final.append(e)
    save("roster.json", {"verified_at": datetime.now(timezone.utc).isoformat(), "experts": final,
                         "rejected": rejected})
    for cat in R["categories"]:
        n = len([e for e in final if e["category"] == cat and e["tier"] == "roster"])
        b = len([e for e in final if e["category"] == cat and e["tier"] == "bench"])
        print(f"{cat}: {n} on roster, {b} on bench")
    print(f"rejected {len(rejected)} (see roster.json -> rejected)")


def verify_local():
    """Same rules as verify(), using profiles read on Rohit's computer by local/collect.py roster."""
    import os
    from common import DATA_DIR
    src = os.path.join(DATA_DIR, "collected", "roster-profiles.json")
    profs = json.load(open(src))["profiles"]
    old = {profile_key(p["linkedin_url"]): p for p in load("roster.json", {}).get("experts", [])}
    experts, rejected, seen = [], [], set()
    for c in profs:
        k = profile_key(c["linkedin_url"])
        if k in seen:
            continue
        seen.add(k)
        rec = {"name": c["name"], "category": c["category"], "linkedin_url": f"https://www.linkedin.com/in/{k}/",
               "headline": c.get("headline", ""), "location": c.get("location", ""), "followers": c.get("followers", 0),
               "active": old.get(k, {}).get("active", True)}
        if excluded(rec["name"]):
            rejected.append({**rec, "reason": "excluded by name"})
        elif not any(x in rec["location"] for x in ("United States", ", US", "USA")) and not re.search(
                r", (AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\b|Area$|Metropolitan|Bay Area",
                rec["location"]):
            rejected.append({**rec, "reason": f"not US ({rec['location'] or 'unknown'})"})
        elif rec["followers"] < R["min_followers"]:
            rejected.append({**rec, "reason": f"followers {rec['followers']} < {R['min_followers']}"})
        else:
            experts.append(rec)
    _finish(experts, rejected)


def _finish(experts, rejected):
    final = []
    for cat in R["categories"]:
        group = sorted([e for e in experts if e["category"] == cat], key=lambda e: -e["followers"])
        for i, e in enumerate(group):
            e["tier"] = "roster" if i < R["per_category"] else "bench"
            final.append(e)
    save("roster.json", {"verified_at": datetime.now(timezone.utc).isoformat(), "experts": final, "rejected": rejected})
    for cat in R["categories"]:
        n = len([e for e in final if e["category"] == cat and e["tier"] == "roster"])
        b = len([e for e in final if e["category"] == cat and e["tier"] == "bench"])
        print(f"{cat}: {n} on roster, {b} on bench")
    print(f"rejected {len(rejected)} (see roster.json -> rejected)")


if __name__ == "__main__":
    {"status": status, "verify": verify, "verify-local": verify_local, "resolve": resolve}[sys.argv[1] if len(sys.argv) > 1 else "status"]()
