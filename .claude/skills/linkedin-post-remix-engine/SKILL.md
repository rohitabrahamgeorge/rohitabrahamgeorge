---
name: linkedin-post-remix-engine
description: >
  Rohit Abraham George's scheduled LinkedIn content routine (runs Monday, Wednesday, Friday).
  Finds the 30 most popular US-based GTM experts and 30 US-based product marketing experts
  (never Elena Verna or Kyle Poyar), scrapes their last 30 days of LinkedIn posts (hook, post
  text, visual, likes, comments, shares) into an Excel swipe file sorted by engagement, scrapes
  Rohit's own profile to see what he has already posted, auto-picks the best 5 posts he has not
  used yet, then for each one shows the original, asks him 3 perspective questions plus a visual
  question, rewrites it lightly in Kinner voice with his perspective, audits it for AI slop with
  the Kinner comment engine rules, recreates the visual in his brand (GIF when the original was a
  GIF), asks whether he wants changes, and hands over the final post to publish. Trigger on
  "run the LinkedIn remix routine", "run my post engine", "swipe file run", "pick my next
  LinkedIn posts", "remix top GTM posts", or when a scheduled task fires with this skill's name.
---

# LinkedIn Post Remix Engine

One run = discover/verify experts → scrape → Excel → sync my profile → pick 5 → for each post:
show, ask, rewrite, audit, visual, approve → hand over → save state.

Paths below are relative to this skill folder (`SKILL`). State lives in the repo at
`linkedin-remix/data/` and each run's output in `linkedin-remix/runs/<YYYY-MM-DD>/`.
`config.json` holds the owner profile, brand tokens, roster rules, weights and pick rules.

## How the data gets in

LinkedIn needs a login to show anyone's recent posts, and this routine never logs in from
the cloud or works around LinkedIn's sign-in wall. So scraping happens on Rohit's own
computer: `local/run.py` (Playwright driving a separate Brave profile he logged into himself)
runs Monday, Wednesday and Friday at 10:30 AM IST, reads the roster's activity pages and
his own, and pushes `linkedin-remix/data/collected/` to the data branch. The cloud run at
11:30 AM IST picks it up. Setup for his computer: `local/SETUP.md`.

No Apify. Rohit has no Apify access; the Apify code paths in the scripts are dormant.

## Phase 0. Setup (no questions, run straight through)

1. Make sure you are on the data branch named in `config.json -> data_branch` with the latest
   state: `git fetch origin <branch> && git checkout <branch> && git pull --ff-only`. If the
   session was started on a different branch, check out the data branch anyway; the scheduled
   task's prompt authorizes committing and pushing state to it.
2. Read `linkedin-remix/data/collected/latest.json`. Fresh means `collected_at` is within the
   last 20 hours. If it is stale or missing, the collector did not run (computer asleep, app
   closed, or LinkedIn asked him to log in again). Say so in one line at the top of the run,
   with the fix ("open the Claude desktop app and run the collector, or run
   `python local/run.py`"), then carry on with the posts already on file.
   If `failed` lists people, mention the count.
3. Load the voice and anti-slop skills before writing anything. Use the Skill tool for
   `anthropic-skills:kinner-voice`, `anthropic-skills:kinner-comment-engine` and
   `anthropic-skills:kinner-commenting-skill` (or read their SKILL.md files under
   `~/.claude/skills/**/`). If they are missing, use `references/remix-rules.md`, which holds
   the parts that matter here.
4. `pip install openpyxl pillow playwright` only if an import fails. Chromium is already
   running (repo CLAUDE.md); `scripts/render.py` attaches to it.
5. Never scrape LinkedIn profile or activity pages from the cloud, never log into LinkedIn,
   and never work around its sign-in wall. Opening a handful of single public post pages
   (`scripts/li_public.py`) is fine; stop if LinkedIn walls it.

## Phase 1. Roster: the 30 + 30 experts

Run `python scripts/roster.py status`.
- If it says NEEDED and `linkedin-remix/data/candidates.json` is older than 30 days, refresh
  the candidate list: about 45 per category from web search (Favikon and similar creator
  rankings, "top GTM voices", "top product marketing creators", Exit Five, PMA, Pavilion,
  podcasts, newsletters). Shape: `{"gtm":[...],"pmm":[...]}`, each `{name, linkedin_url,
  headline_or_company, why_popular, source}`. US-based only. Never add anyone in
  `config.json -> roster.exclude_names` (Elena Verna, Kyle Poyar). Keep people already on the
  roster unless they went inactive. Never invent a LinkedIn URL.
- Verification (US location, follower floor, not excluded, top 30 per category by followers,
  the rest on the bench) runs on his computer: `local/run.py` sees the roster is due, reads
  each candidate's profile, and runs `roster.py verify-local`. If `roster.json` is missing in
  the cloud run, the collector has not done its first run yet: stop after saving
  candidates.json and tell him to run `python local/run.py` once.
- Posting activity is enforced in Phase 2: anyone with fewer than 4 posts in 30 days is
  swapped for the best bench person (the collector also reads 6 bench people each run).

## Phase 2. Load the collected posts

1. `APIFY_ITEMS=linkedin-remix/data/collected/experts-<date>.json python scripts/scrape.py experts`
   (use the newest experts file). This merges the posts into the 30-day table and applies the
   activity swap. Each post has: hook (the lines above "see more"), full text, visual type
   (text, image, multi-image, gif, carousel, video, poll) and image links, likes, comments,
   reposts, engagement score, URL.
2. `APIFY_ITEMS=linkedin-remix/data/collected/self-<date>.json python scripts/scrape.py self`
   for his own posts (skip if no self file). The collector fills `owner.linkedin_url` in
   `config.json` itself on its first run.
3. If a post in the table has no text or counts (rare DOM misses), it is fine to fill it from
   its public page with `scripts/li_public.py read <urls.txt>`, only for a handful of posts.

## Phase 3. Sync and the Excel swipe file

1. `python scripts/pick.py sync` marks earlier approved remixes as `posted` once they show up
   on his profile, and refreshes his engagement numbers on them.
2. `python scripts/build_workbook.py` writes
   `runs/<date>/linkedin-swipe-file-<date>.xlsx` with sheets Top Posts (sorted by engagement
   score), Experts, My Posts, Remix Ledger, About.
3. Send the workbook with SendUserFile (`display: attach`).

Engagement score = likes x1 + comments x3 + reposts x5 (`config.json -> engagement_weights`).
Comments and shares are weighted up because they are what LinkedIn's feed rewards.

## Phase 4. Pick the best 5 he has not used

`python scripts/pick.py pick` writes `runs/<date>/picks.json`. Rules: highest engagement score
first; skip anything in the ledger; skip anything that overlaps one of his own posts (that
means he already moved it over); skip video posts (he does not use video); skip posts under
200 characters; max one post per author; at least one GTM and one PMM post when possible.

When the run was started by the schedule, send a push notification now (PushNotification
tool, if available): "Your 5 LinkedIn picks are ready. 3 quick questions each." Then start
Phase 5.

## Phase 5. One post at a time: show, ask, rewrite, audit, visual, approve

Do this for each pick in order. Offer once at the start: "Want to go one post at a time, or
answer all 5 sets of questions in one go?" Default is one at a time.

### 5a. Get the original visual
`python scripts/fetch_media.py <post_id>` saves the media into `runs/<date>/<post_id>/`.
Open the image (or the GIF frames it extracts) with the Read tool so you know what the
visual looks like: layout, number of sections, what each section says, whether it is a GIF.

### 5b. Show the original post FIRST
Before any question, show:
```
POST 2 of 5  ·  [GTM]  ·  <Author>  ·  <date>  ·  <likes> likes, <comments> comments, <shares> shares
Hook: <hook>
<full post text>
Visual: <type> · <link>  (and the downloaded image via SendUserFile, display render)
Why it won: one plain line on what made it work (hook shape, format, a number, a story)
```

### 5c. Ask the questions (questions 1 to 4)
Ask in plain chat, numbered, short, specific to THIS post and to his work at Edbound AI
(content hubs, resource centers, AI content workflows, GTM for B2B AI companies):
1. Perspective: where does he agree or disagree with the post, from his own work?
2. Proof: a real example, number, client situation or moment from his work that fits it.
3. Angle: what would he add or change for his audience (content marketing and content hub
   GTM people)?
4. Visual: what from his answers should the visual show (a number, a step, a before and
   after), or keep the original's structure as is?
Wait for his answers. Never fill in answers for him. If he skips one, use less, never invent.

### 5d. Rewrite in Kinner voice (light touch)
Rules, in order of priority:
- Keep the original's skeleton: same hook shape, same structure, same length band (within
  about 20 percent), same format (list stays a list).
- Every sentence is reworded. No sentence of 7+ words copied from the original (the checker
  enforces this). Do not tag or name the original author unless he asks for a credit line.
- Weave his answers in as his own first-person experience. His perspective should be the
  part a reader remembers. Never invent a number, client, or story beyond what he said.
- Voice: kinner-voice (warm, direct, plain, short and longer lines mixed, says it out loud).
  Its LinkedIn structure applies: hook, story, lesson, optional genuine closing question,
  then hashtags. Never sign off with Kinner's name; this is Rohit's post. Zero em dashes,
  zero ampersands.

### 5e. Audit for AI slop (loop until clean)
1. Save the draft to `runs/<date>/<post_id>/draft.md` and the original text to
   `runs/<date>/<post_id>/source.txt`.
2. `python scripts/slop_check.py runs/<date>/<post_id>/draft.md --source runs/<date>/<post_id>/source.txt`
   Fix every HARD FAIL. Treat every REVIEW item as a question to answer honestly.
3. Run the kinner-comment-engine Phase 5 self-audit on the draft (the "AI-slop patterns" and
   "Human signal and voice" and "Fabrication check" blocks apply to posts unchanged), plus
   the kinner-commenting-skill hard rules (no metaphors for color, banned words and framings,
   plain language over clever, industry logic check, never fabricate). The master tell: any
   sentence that sounds crafted gets flattened.
4. Loop steps 2 and 3 until both are clean. Never show him a draft that has not passed.

### 5f. Recreate the visual in his brand
- Start from `assets/templates/brand.css` and the samples in `assets/templates/`
  (`sample-framework.html` for static, `sample-animated.html` for GIF). The brand reference
  is `assets/brand-reference.png`; open it if you need to check the look.
- Mirror the ORIGINAL visual's structure (same number of sections, same kind of diagram,
  same idea), rewritten with his words and updated with his answer to question 4.
- Original is a GIF → make a GIF (`window.FRAMES` + `window.setFrame(i)`, 4 to 7 frames).
  Original is an image, carousel cover or multi-image → one static PNG (for a carousel, make
  the cover plus up to 4 inner slides as separate PNGs). Original is text-only → make a
  simple brand quote card from the hook only if he asked for a visual in question 4.
- Footer always uses the placeholders `{{ASSETS}}/headshot.jpg`, `{{NAME}}`, `{{TITLE}}`;
  `render.py` fills them from `config.json`.
- Fill the 1080x1350 canvas; no big empty band above the footer. Only real numbers.
- Render: `python scripts/render.py runs/<date>/<post_id>/visual.html runs/<date>/<post_id>/visual.png`
  (or `.gif`). Open the result with Read and fix overlaps, overflow and empty space before
  showing it.

### 5g. Show the draft, then ask question 5
Show the final post text in a code block (so it copies cleanly) and send the visual with
SendUserFile (display render). Then ask:
5. "Want any changes to the post or the visual, or is it good to go?"
If he wants changes, make them, rerun 5e (and the render), and ask again. When he approves:
save `runs/<date>/<post_id>/final.md` and run
`python scripts/pick.py mark <post_id> approved runs/<date>/<post_id>/final.md`.
If he passes on a post: `mark <post_id> rejected` and move to the next pick (do not refill).

## Phase 6. Apply the post

LinkedIn has no posting connector in this setup, so "apply" means a ready-to-post package:
- the final text in a code block, the visual file (PNG or GIF), and a suggested slot (one
  post per day, spread across the days before the next run; weekday mornings US Eastern
  suit his US-based audience).
- If a tool that can publish to LinkedIn is connected (for example a vidIQ social account on
  LINKEDIN, or a LinkedIn connector), draft it there, show the draft, and publish only after
  he says yes to that specific draft.
The next run's `pick.py sync` confirms when each post is live on his profile and logs its
engagement in the Remix Ledger.

## Phase 7. Save state

`bash scripts/save_state.sh` commits `linkedin-remix/` (data and this run's folder) and
pushes to the data branch. Run it after Phase 3 (so the scrape is never lost) and again at the
end of the run. If the push is rejected, follow the repo's git rules (fetch, merge, push).

## Guardrails
- Never Elena Verna or Kyle Poyar, in any list, pick, or credit.
- Never invent numbers, clients, quotes, or LinkedIn URLs.
- Never publish anything without his explicit yes on that exact post.
- Video posts are tracked in the Excel but never picked.
- If Apify fails mid-run, finish with what you have, say exactly what is missing, and save
  state.
