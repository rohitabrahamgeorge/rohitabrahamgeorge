# Claude instructions

## Browser automation
- Python Playwright is installed and a persistent headless Chromium is started automatically by
  `.claude/hooks/session-start.sh` at session start. If it is missing, run that hook manually:
  `CLAUDE_CODE_REMOTE=true .claude/hooks/session-start.sh`.
- Always reuse the running browser; never launch a new one. In Python:
  `from pwb import page; p = page(); p.goto(url)` (attaches over CDP on 127.0.0.1:9222, keeping
  open tabs, cookies and logins).
- Node: `chromium.connectOverCDP('http://127.0.0.1:9222')`.
