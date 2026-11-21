# Set up the LinkedIn collector on your computer (one time, about 10 minutes)

The collector reads your 60 experts' recent posts while logged into LinkedIn as you, then
pushes them to GitHub. The cloud routine (Sun, Wed, Fri at 9:36 AM IST) does everything else.

It uses Brave, but a **separate Brave profile** just for this, so your normal Brave windows,
tabs and logins are untouched.

## 1. Get the code

Mac (Terminal) or Windows (PowerShell):

```
git clone https://github.com/rohitabrahamgeorge/rohitabrahamgeorge.git linkedin-remix-repo
cd linkedin-remix-repo
git checkout ccr-037db276-kmixql
```

## 2. Install Python packages

You need Python 3.10 or newer (`python3 --version`; on Windows use `python`).

```
python3 -m pip install playwright openpyxl pillow
```

Brave is found automatically. If you ever see "Executable doesn't exist", either set
`REMIX_BROWSER` to your Brave path or run `python3 -m playwright install chromium`.

## 3. Log into LinkedIn once

```
python3 .claude/skills/linkedin-post-remix-engine/local/collect.py login
```

A Brave window opens on the LinkedIn login page. Log in with your **LinkedIn email and
password** (Google may refuse "Sign in with Google" in a window controlled by a script).
Finish any verification code LinkedIn sends you. When your feed shows, go back to the
terminal and press Enter. The session is saved in `~/.linkedin-remix/browser-profile` and
reused on every run. You won't need to do this again unless LinkedIn logs you out.

## 4. First run

```
python3 .claude/skills/linkedin-post-remix-engine/local/run.py
```

The first run takes about 40 to 50 minutes. It checks all 90 candidate profiles (US
location, followers) to pick the 30 + 30, then reads their posts. Later runs take about 20
minutes. It is slow on purpose: one profile every 10 to 20 seconds, like a person reading.

If a profile shows 0 posts when you know it has some, run with `--debug` and the cloud run
will use the saved page to fix the selectors.

## 5. Schedule it (Sun, Wed, Fri at 8:40 AM)

Your computer has to be on and awake at that time.

**Option A: Claude desktop app.** Claude Code → Scheduled tasks → New local task. Choose
the `linkedin-remix-repo` folder, set it to Sunday, Wednesday and Friday at 8:40 AM, with this
prompt:

> Run `python3 .claude/skills/linkedin-post-remix-engine/local/run.py` in this folder and
> tell me its last line. If it fails, show me the error.

The desktop app has to be open for it to fire.

**Option B: Mac, no Claude needed.** Run `crontab -e` and add (fix the path):

```
40 8 * * 0,3,5 cd ~/linkedin-remix-repo && /usr/bin/env python3 .claude/skills/linkedin-post-remix-engine/local/run.py >> ~/linkedin-remix.log 2>&1
```

**Option B: Windows, no Claude needed.** Task Scheduler → Create Basic Task → Weekly, Sun
Wed Fri, 8:40 AM → Start a program: `python`, arguments
`.claude\skills\linkedin-post-remix-engine\local\run.py`, start in: your
`linkedin-remix-repo` folder.

## If something goes wrong

- **"LinkedIn asked for login/checkpoint"**: run step 3 again.
- **Push rejected**: run `git pull` in the folder, then run again.
- **Want to watch it work**: set `REMIX_HEADED=1` before running to see the browser window.
