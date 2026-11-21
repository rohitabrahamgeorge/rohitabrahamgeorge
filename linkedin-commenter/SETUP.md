# Setup: LinkedIn GTM commenting routine (runs on your computer)

LinkedIn blocks cloud browsers with a Cloudflare bot check, and the AimFox API has no endpoint for reading
posts or commenting. So this routine runs on your computer, in your own browser profile, on a schedule
through the Claude desktop app.

## One-time setup (about 10 minutes)

1. **Get the repo onto your computer**
   ```bash
   git clone https://github.com/rohitabrahamgeorge/rohitabrahamgeorge.git
   cd rohitabrahamgeorge
   git checkout claude/linkedin-engagement-automation-h7dz64   # or main once merged
   ```
2. **Install Playwright** (needs Python 3.9+):
   ```bash
   pip install playwright
   python3 -m playwright install chromium
   ```
   If Google Chrome is installed, the script uses it automatically.
3. **Log in to LinkedIn once** in the routine's own browser profile:
   ```bash
   python3 linkedin-commenter/scripts/li.py login
   ```
   A browser window opens. Log in and finish any 2FA. The session is saved in
   `~/.linkedin-commenter/profile` and reused by every run. Your password never goes to Claude.
   Then confirm: `python3 linkedin-commenter/scripts/li.py check` → `"logged_in": true`.
4. **Do a dry run first** (fills the comment boxes but never submits). In Claude desktop → Code tab,
   open this folder and send: `/linkedin-gtm-commenter dry run, 5 creators`. Check the report in
   `linkedin-commenter/reports/`. This also resolves profile URLs and real follower counts for those creators.

## Schedule it: Mon/Wed/Fri 10:30 AM IST

In **Claude desktop → Code → Scheduled → New task** (needs Claude Desktop 1.1.5368 or later):

- **Name:** LinkedIn GTM comments
- **Instructions:** `/linkedin-gtm-commenter Run today's routine: 25 comments, then show me the report.`
- **Advanced → Only on this computer**, local folder = this repo folder
- **Schedule:** Custom → `30 10 * * 1,3,5` (uses your computer's local time, so IST)
- **Permission mode:** click **Run now** once and approve the `python3` / file edits with "always allow".
  Then set the mode to Accept edits so later runs don't stall waiting for a person.
- Turn on **Keep computer awake** in the app's settings. Runs only happen while the app is open and the
  computer is awake. If one is missed, a single catch-up run fires when the computer wakes.

Docs: https://code.claude.com/docs/en/desktop-scheduled-tasks

**Fallback without the desktop app** (cron on Mac/Linux):
```
30 10 * * 1,3,5 cd /path/to/rohitabrahamgeorge && claude -p "/linkedin-gtm-commenter Run today's routine" --permission-mode acceptEdits --allowedTools "Bash(python3 *),Bash(git *),Read,Edit,Write" >> linkedin-commenter/state/cron.log 2>&1
```

## Every run

- The report lands in `linkedin-commenter/reports/<date>.md` and in the scheduled run's session, with a
  link to each post.
- To give feedback, open any session in this folder and say for example: "On the Josh Braun comment
  from Friday, too generic. Ask about his numbers instead." Claude adds it to `feedback.md`, and
  every later run follows it.

## Notes and risks

- Automated activity is against LinkedIn's User Agreement. A real browser on your home IP, human-like
  pacing (60–180 s between comments) and specific comments keep the risk low, but it isn't zero. 25
  comments per run (about 75 a week) is on the high side. If LinkedIn ever shows a warning or checkpoint,
  the routine stops itself and tells you. Drop to 15 per run if that happens.
- LinkedIn changes its page layout often. If the script can't find the comment box, it saves a
  screenshot to `linkedin-commenter/state/screenshots/`, and Claude adapts or reports the error.
  Selectors may need a tweak over time.
- Follower counts in `creators.csv` are estimates. Each creator's real count is checked on their first
  visit, and they're moved to the correct tier (or flagged for review) automatically.
