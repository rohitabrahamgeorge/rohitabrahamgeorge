#!/usr/bin/env bash
# Commit and push the remix engine's state (linkedin-remix/) to the data branch.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
BRANCH=$(python3 -c "import json;print(json.load(open('.claude/skills/linkedin-post-remix-engine/config.json'))['data_branch'])")
git add linkedin-remix .claude/skills/linkedin-post-remix-engine/config.json
if git diff --cached --quiet; then echo "nothing to save"; exit 0; fi
git commit -q -m "LinkedIn remix engine: state for $(date -u +%Y-%m-%d)"
for i in 1 2 3 4; do
  if git push -q -u origin "HEAD:$BRANCH"; then echo "saved to $BRANCH"; exit 0; fi
  git fetch -q origin "$BRANCH" && git merge -q --no-edit FETCH_HEAD || true
  sleep $((i * 4))
done
echo "push failed after 4 tries" >&2; exit 1
