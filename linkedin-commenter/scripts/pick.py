#!/usr/bin/env python3
"""Pick today's creators: least-recently-commented first, balanced across follower tiers.

  python3 pick.py [--n 25] [--backups 20]

Prints JSON: {"primary": [...n creators...], "backups": [...]}. Use backups, in order, to
replace any primary creator who is skipped (no fresh post, off-limits topic, error).
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CREATORS = ROOT / "creators.csv"
LOG = ROOT / "state" / "comments-log.csv"


def arg(name, default):
    return int(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def main():
    n, backups = arg("--n", 25), arg("--backups", 20)
    creators = [c for c in csv.DictReader(CREATORS.open()) if c["status"].strip() == "active"]
    last = {}
    if LOG.exists():
        for row in csv.DictReader(LOG.open()):
            if row.get("result") == "posted":
                last[row["creator_id"]] = max(last.get(row["creator_id"], ""), row["date"])
    for c in creators:
        c["last_commented"] = last.get(c["id"], "")
    tiers = {}
    for c in creators:
        tiers.setdefault(c["tier"], []).append(c)
    for t in tiers.values():  # never-commented first, then oldest; id breaks ties
        t.sort(key=lambda c: (c["last_commented"], int(c["id"])))
    # round-robin across tiers so every run mixes small, mid and large audiences
    order, keys = [], sorted(tiers)
    while any(tiers[k] for k in keys):
        for k in keys:
            if tiers[k]:
                order.append(tiers[k].pop(0))
    keep = ["id", "name", "role", "company", "region", "tier", "linkedin_url", "topics", "last_commented"]
    slim = [{k: c[k] for k in keep} for c in order]
    print(json.dumps({"primary": slim[:n], "backups": slim[n:n + backups]}, indent=2))


if __name__ == "__main__":
    main()
