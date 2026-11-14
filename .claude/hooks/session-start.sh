#!/bin/bash
set -euo pipefail

# Only run in Claude Code cloud sessions
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

# Python Playwright into the system Python (skip if already installed and this script is unchanged)
purelib="$(python3 -I -c 'import sysconfig; print(sysconfig.get_path("purelib"))')"
pyhashes="$purelib/.session-start.sha256"
if ! sha256sum --check --status "$pyhashes" 2>/dev/null || ! python3 -c 'import playwright' 2>/dev/null; then
  rm -f "$pyhashes"
  python3 -m pip install -q playwright
  sha256sum .claude/hooks/session-start.sh > "$pyhashes" || rm -f "$pyhashes"
fi

# Make the pwb helper importable from any Python script
chmod +x .claude/browser/start-browser.sh
ln -sf "$PWD/.claude/browser/pwb.py" "$purelib/pwb.py"

# Start the persistent browser (no-op if already running)
.claude/browser/start-browser.sh
