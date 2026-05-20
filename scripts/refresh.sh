#!/bin/bash
# Daily refresh: fetch transcripts, synthesize, render, commit, push.
# Invoked by ~/Library/LaunchAgents/com.kevnull.f1-fantasy-tips.refresh.plist.

set -euo pipefail

REPO="/Users/kevnull/Development/f1-fantasy-tips"
cd "$REPO"

# Make Homebrew tools (yt-dlp, git) findable when launchd starts us with a minimal PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# Load ANTHROPIC_API_KEY etc.
set -a
# shellcheck disable=SC1091
source .env
set +a

echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') refresh starting ==="

# Self-heal: yt-dlp goes stale every few months as YouTube changes its page format.
# Upgrade quietly; never fail the run if brew has issues.
if command -v brew >/dev/null 2>&1; then
  brew upgrade yt-dlp >/dev/null 2>&1 || echo "[warn] yt-dlp upgrade skipped/failed"
fi

.venv/bin/python src/main.py

# Make sure we're not behind origin before attempting to push (GitHub Actions
# pushes daily re-render commits to main).
git fetch origin main --quiet || true
git pull --rebase --autostash origin main || {
  echo "[error] rebase failed; aborting push to avoid making it worse"
  git rebase --abort 2>/dev/null || true
  exit 1
}

# Commit + push only if something actually changed.
if ! git diff --quiet -- data/strategy.json docs/ data/archive 2>/dev/null \
   || [[ -n "$(git status --porcelain data/strategy.json docs/ data/archive 2>/dev/null)" ]]; then
  git add data/strategy.json docs/ data/archive data/cache/photos 2>/dev/null || true
  RACE_LINE=$(.venv/bin/python -c "import json; print(json.load(open('data/strategy.json')).get('race','GP'))")
  git commit -m "Refresh strategy: $RACE_LINE [automated]" || echo "[info] nothing to commit"
  git push
  echo "=== pushed ==="
else
  echo "=== no changes ==="
fi
