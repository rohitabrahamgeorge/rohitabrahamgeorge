---
name: linkedin-gtm-commenter
description: Runs the Mon/Wed/Fri LinkedIn commenting routine. Picks 25 GTM / product marketing / founder creators from linkedin-commenter/creators.csv, opens each one's latest post in the user's logged-in local browser, skips off-limits topics (politics, religion, race, tragedy, personal news), writes one specific, simple-English comment (question, missing insight, or real research point), posts it, logs it and writes a report with post links. Also use when the user gives feedback on past comments, asks to add/remove creators, or asks for a dry run.
---

# LinkedIn GTM commenting routine

All paths are relative to the repository root. Must run on the user's own computer:
LinkedIn blocks cloud browsers. Files:

- `linkedin-commenter/creators.csv`: the 100 creators (tier, topics, status, resolved profile URL)
- `linkedin-commenter/playbook.md`: topic gate, comment types, style rules, quality check
- `linkedin-commenter/feedback.md`: the user's feedback. **Overrides the playbook.**
- `linkedin-commenter/state/comments-log.csv`: every attempt (rotation + no duplicates)
- `linkedin-commenter/reports/YYYY-MM-DD.md`: one report per run
- `linkedin-commenter/scripts/li.py`: browser helper (JSON output); `scripts/pick.py`: rotation

Defaults: 25 comments per run, wait 60–180 s (random) between posted comments.
If the user's prompt says "dry run", do everything except submitting (`--dry-run`) and log result `dry-run`.

## Steps

1. **Read** `playbook.md` and `feedback.md` fully. Read the last 2 reports to avoid repeating phrasing.
2. **Session check**: `python3 linkedin-commenter/scripts/li.py check`. If not logged in, stop, write a
   report that says "LinkedIn session expired: run `python3 linkedin-commenter/scripts/li.py login`", and finish.
   Never type a password anywhere.
3. **Pick**: `python3 linkedin-commenter/scripts/pick.py --n 25 --backups 25`.
4. **For each creator** (primary first, then backups until 25 are posted or the list runs out):
   a. If `linkedin_url` is empty, run `li.py resolve "<name>" "<company>"`, choose the match whose card
      fits the name + company/role (if none clearly fits, mark it `skipped: unresolved` and move on). Save the URL
      into creators.csv. Also run `li.py profile <url>` once and save `verified_followers`; if the real count puts
      them in another tier (10k+ = 10k–49k, 50k+ = 50k–99k, 100k+ = 100k and up), update `tier`; if under 10k or not
      based in US/Canada/Europe, set `status` to `review` and note it in the report.
   b. `li.py latest <url> --n 3`. Take the newest original post. Skip if: older than 5 days (age like `6d`, `1w`, `2mo`),
      already in comments-log.csv as `posted`, or it fails the playbook topic gate.
   c. Write the comment following the playbook (pick the type that best fits the post, keep the run's type mix
      varied). Run the 6-point quality check. If any answer is no, rewrite once; if still no, skip.
   d. Save the text to a temp file and run `li.py comment <post_url> <file>`. On `ok: true` log `posted`.
      On an error, look at the screenshot path it returns, try once more, then log `error` with the reason and move on.
      If three comments in a row fail, or LinkedIn shows a checkpoint/captcha/restriction, **stop the whole run**
      and say so at the top of the report.
   e. Append a row to comments-log.csv for every attempt (posted, skipped, error, dry-run) with the reason in `notes`.
   f. Wait a random 60–180 s before the next posted comment.
5. **Report**: write `linkedin-commenter/reports/<date>.md`:
   - Summary line: posted X / 25, skipped Y (by reason), errors Z, run time.
   - Table: # | Creator (tier) | Post link | Post topic (≤10 words) | Comment type | Comment text.
   - Skipped list with reasons; creators set to `review`; any tier changes.
   - Finish with: "Reply with feedback on any comment and it will be added to feedback.md."
   Then print the same report as the final message of the session.
6. If the repository is a git checkout with a remote, commit `linkedin-commenter/` changes
   (`git add linkedin-commenter && git commit -m "LinkedIn comments <date>"`) and push if possible. Don't fail the run if the push fails.

## When the user gives feedback

Add an entry at the top of the `## Entries` section in `feedback.md` (date, creator, link, what was posted,
the better version, the general rule). If the lesson is durable, also add it under `## Standing rules`.
Do not edit the playbook unless asked; feedback.md wins over it.

## Managing the list

To add a creator, append a row with the next id and `status=active`. To remove one, set `status=paused`
(keeps history). Keep the three tiers roughly balanced.
