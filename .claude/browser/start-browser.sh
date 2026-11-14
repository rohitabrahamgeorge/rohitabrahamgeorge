#!/bin/bash
# Start one persistent headless Chromium (CDP on 127.0.0.1:9222) if it is not already running.
PORT=9222
PROFILE="${PW_PROFILE_DIR:-/root/.pw/profile}"
if curl -s "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then echo "browser already running"; exit 0; fi
CHROME=/opt/pw-browsers/chromium
[ -x "$CHROME" ] || { echo "chromium not found at $CHROME" >&2; exit 1; }
mkdir -p "$PROFILE"
nohup "$CHROME" --headless=new --no-sandbox --remote-debugging-port=$PORT \
  --user-data-dir="$PROFILE" --window-size=1440,900 about:blank >/tmp/pw-browser.log 2>&1 &
for _ in $(seq 1 50); do
  curl -s "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1 && { echo "browser started"; exit 0; }
  sleep 0.2
done
echo "browser failed to start; see /tmp/pw-browser.log" >&2; exit 1
