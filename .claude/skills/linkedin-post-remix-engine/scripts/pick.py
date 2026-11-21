"""Profile sync + pick the best N posts not yet used on the owner's profile.

  python pick.py sync     # match drafted remixes against my_posts.json -> mark 'posted'
  python pick.py pick     # write runs/<date>/picks.json (top N by engagement, unused)
  python pick.py mark <source_post_id> <status> [final_text_file]
        status: drafting | approved | posted | rejected | deferred

ledger.json is the memory of what has been used, keyed by source post id.
A post is 'already copied over' if it is in the ledger (any status except deferred)
OR if anything on the owner's profile overlaps it above picks.similarity_threshold.
"""
import json
import os
import sys
from common import CONFIG, load, save, run_dir, similarity, today

P = CONFIG["picks"]


def sync():
    ledger = load("ledger.json", {})
    mine = list(load("my_posts.json", {"posts": {}})["posts"].values())
    hits = 0
    for sid, rec in ledger.items():
        if rec.get("status") in ("approved", "drafting") and rec.get("final_text"):
            for m in mine:
                if similarity(rec["final_text"], m["text"]) >= 0.6:
                    rec.update(status="posted", my_post_url=m["url"], posted_at=m["posted_at"],
                               my_likes=m["likes"], my_comments=m["comments"], my_shares=m["shares"])
                    hits += 1
                    break
        elif rec.get("status") == "posted" and rec.get("my_post_url"):
            for m in mine:  # refresh my engagement numbers
                if m["url"] == rec["my_post_url"]:
                    rec.update(my_likes=m["likes"], my_comments=m["comments"], my_shares=m["shares"])
    save("ledger.json", ledger)
    print(f"sync: {hits} newly confirmed live on your profile; {len(mine)} of your posts on file")


def pick():
    posts = sorted(load("posts.json", {"posts": {}})["posts"].values(), key=lambda p: -p["score"])
    ledger = load("ledger.json", {})
    mine = [m["text"] for m in load("my_posts.json", {"posts": {}})["posts"].values()]
    mine += [r["final_text"] for r in ledger.values() if r.get("final_text")]
    used_authors_recent = {r.get("author") for r in ledger.values() if r.get("date", "") >= today()[:8]}
    chosen, per_author = [], {}
    for p in posts:
        if len(chosen) >= P["count"]:
            break
        if p["id"] in ledger and ledger[p["id"]].get("status") != "deferred":
            continue
        if p["media_type"] in P["skip_media_types"]:
            continue
        if len(p["text"]) < 200:  # one-liners and link drops don't remix well
            continue
        if per_author.get(p["author"], 0) >= P["max_per_author"]:
            continue
        overlap = max([similarity(p["text"], m) for m in mine] or [0])
        if overlap >= P["similarity_threshold"]:
            ledger[p["id"]] = {"status": "already-on-profile", "date": today(), "author": p["author"],
                               "overlap": round(overlap, 2)}
            continue
        per_author[p["author"]] = per_author.get(p["author"], 0) + 1
        p["author_used_this_month"] = p["author"] in used_authors_recent
        chosen.append(p)
    # light category balance: if all picks are one category and the other has candidates, swap the last
    cats = {c["category"] for c in chosen}
    if len(cats) == 1 and len(chosen) == P["count"]:
        other = next((p for p in posts if p["category"] not in cats and p["id"] not in ledger
                      and p["media_type"] not in P["skip_media_types"] and len(p["text"]) >= 200
                      and p["author"] not in per_author), None)
        if other:
            chosen[-1] = other
    save("ledger.json", ledger)
    out = os.path.join(run_dir(), "picks.json")
    json.dump(chosen, open(out, "w"), indent=2, ensure_ascii=False)
    for i, p in enumerate(chosen, 1):
        print(f"{i}. [{p['category']}] {p['author']} | score {p['score']} "
              f"({p['likes']}L/{p['comments']}C/{p['shares']}S) | {p['media_type']} | {p['hook'][:80]!r}")
    print(f"-> {out}")


def mark(sid, status, text_file=None):
    ledger = load("ledger.json", {})
    posts = load("posts.json", {"posts": {}})["posts"]
    rec = ledger.get(sid, {})
    src = posts.get(sid, {})
    rec.update(status=status, date=today(), author=src.get("author", rec.get("author")),
               source_url=src.get("url", rec.get("source_url")))
    if text_file:
        rec["final_text"] = open(text_file).read()
    ledger[sid] = rec
    save("ledger.json", ledger)
    print(f"{sid}: {status}")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "mark":
        mark(*sys.argv[2:])
    else:
        {"sync": sync, "pick": pick}[cmd]()
