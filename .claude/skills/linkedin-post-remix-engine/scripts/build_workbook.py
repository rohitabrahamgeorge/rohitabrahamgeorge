"""Write runs/<date>/linkedin-swipe-file-<date>.xlsx from the JSON state.

Sheets: Top Posts (sorted by engagement score), Experts, My Posts, Remix Ledger, About.
"""
import os
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from common import CONFIG, load, run_dir, today

B = CONFIG["brand"]
HEAD_FILL = PatternFill("solid", fgColor=B["ink"].lstrip("#"))
HEAD_FONT = Font(bold=True, color="FFFFFF", name="Calibri")
ACCENT = PatternFill("solid", fgColor="FCEDE6")
WRAP = Alignment(wrap_text=True, vertical="top")


def sheet(wb, title, headers, rows, widths, link_cols=(), first=False):
    ws = wb.active if first else wb.create_sheet()
    ws.title = title
    ws.append(headers)
    for c in ws[1]:
        c.fill, c.font = HEAD_FILL, HEAD_FONT
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for r in rows:
        ws.append(r)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = WRAP
        for ci in link_cols:
            cell = row[ci]
            v = cell.value
            if isinstance(v, str) and v.startswith("http"):
                cell.hyperlink = v.split("\n")[0]
                cell.font = Font(color="C2410C", underline="single")
    ws.freeze_panes = "B2" if title == "Top Posts" else "A2"
    ws.auto_filter.ref = ws.dimensions
    return ws


def main():
    posts = sorted(load("posts.json", {"posts": {}})["posts"].values(), key=lambda p: -p["score"])
    ledger = load("ledger.json", {})
    roster = load("roster.json", {"experts": []})
    mine = sorted(load("my_posts.json", {"posts": {}})["posts"].values(),
                  key=lambda p: p.get("posted_at", ""), reverse=True)
    wb = Workbook()
    rows = []
    for i, p in enumerate(posts, 1):
        st = ledger.get(p["id"], {}).get("status", "")
        rows.append([i, p["category"].upper(), p["author"], p["posted_at"], p["hook"], p["text"],
                     p["media_type"], "\n".join(p["media_urls"]), p["likes"], p["comments"], p["shares"],
                     p["score"], p["url"], st, p["author_url"]])
    ws = sheet(wb, "Top Posts",
               ["Rank", "Category", "Author", "Posted", "Hook", "Post text", "Visual type", "Visual link(s)",
                "Likes", "Comments", "Shares", "Engagement score", "Post URL", "Used by me?", "Author profile"],
               rows, [6, 9, 20, 11, 40, 80, 11, 40, 8, 10, 8, 11, 30, 14, 30], link_cols=(7, 12, 14), first=True)
    for row in ws.iter_rows(min_row=2):
        if row[13].value:
            for c in row:
                c.fill = ACCENT
    sheet(wb, "Experts", ["Category", "Name", "Headline", "Location", "Followers", "Tier", "Active", "Profile"],
          [[e["category"].upper(), e["name"], e["headline"], e["location"], e["followers"], e["tier"],
            "yes" if e.get("active", True) else "no", e["linkedin_url"]]
           for e in sorted(roster["experts"], key=lambda e: (e["category"], e["tier"] != "roster", -e["followers"]))],
          [10, 24, 50, 30, 11, 9, 8, 45], link_cols=(7,))
    sheet(wb, "My Posts", ["Posted", "Hook", "Post text", "Visual type", "Likes", "Comments", "Shares", "URL"],
          [[m["posted_at"], m["hook"], m["text"], m["media_type"], m["likes"], m["comments"], m["shares"], m["url"]]
           for m in mine], [11, 40, 80, 11, 8, 10, 8, 40], link_cols=(7,))
    sheet(wb, "Remix Ledger", ["Source post id", "Status", "Date", "Source author", "Source URL", "My post URL",
                               "My likes", "My comments", "My shares", "Final text"],
          [[k, v.get("status"), v.get("date"), v.get("author"), v.get("source_url", ""), v.get("my_post_url", ""),
            v.get("my_likes", ""), v.get("my_comments", ""), v.get("my_shares", ""), v.get("final_text", "")]
           for k, v in sorted(ledger.items(), key=lambda kv: kv[1].get("date", ""), reverse=True)],
          [22, 16, 11, 22, 40, 40, 8, 10, 8, 80], link_cols=(4, 5))
    w = CONFIG["engagement_weights"]
    about = wb.create_sheet("About")
    for line in [
        f"LinkedIn swipe file for {CONFIG['owner']['name']}, built {today()}",
        f"Window: last {CONFIG['scrape']['window_days']} days of posts from {len(roster['experts'])} verified US experts",
        f"Engagement score = likes x{w['likes']} + comments x{w['comments']} + shares x{w['shares']}",
        "Hook = the first lines a reader sees before 'see more'",
        "Highlighted rows in Top Posts are already used (drafted, approved or posted).",
    ]:
        about.append([line])
    about.column_dimensions["A"].width = 110
    out = os.path.join(run_dir(), f"linkedin-swipe-file-{today()}.xlsx")
    wb.save(out)
    print(out)


if __name__ == "__main__":
    main()
