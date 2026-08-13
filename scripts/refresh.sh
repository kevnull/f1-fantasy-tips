#!/bin/bash
# Daily refresh: fetch transcripts, synthesize, render, commit, push, notify.
# Invoked by ~/Library/LaunchAgents/com.kevnull.f1-fantasy-tips.refresh.plist.

REPO="/Users/kevnull/Development/f1-fantasy-tips"
cd "$REPO" || exit 1

# Make Homebrew tools (yt-dlp, git) findable when launchd starts us with a minimal PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# Load ANTHROPIC_API_KEY, NTFY_TOPIC, NTFY_EMAIL, etc.
set -a
# shellcheck disable=SC1091
source .env
set +a

echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') refresh starting ==="

# Capture the full run's output so we can send the tail of it on failure.
TMP_LOG="$(mktemp -t f1-refresh.XXXXXX)"
trap 'rm -f "$TMP_LOG"' EXIT

notify_success() {
  [[ -z "${NTFY_TOPIC:-}" ]] && return 0
  local race="$1" summary_file="$2"
  local subject="F1 Fantasy — ${race} updated"
  local headers=(-H "Title: ${subject}" -H "Tags: checkered_flag" -H "Click: https://kevnull.github.io/f1-fantasy-tips/")
  [[ -n "${NTFY_EMAIL:-}" ]] && headers+=(-H "Email: ${NTFY_EMAIL}")
  curl -fsS --max-time 15 "${headers[@]}" \
    --data-binary @"$summary_file" \
    "https://ntfy.sh/${NTFY_TOPIC}" >/dev/null \
    || echo "[warn] ntfy success notify failed"
}

notify_failure() {
  [[ -z "${NTFY_TOPIC:-}" ]] && return 0
  local race="${1:-refresh}" tail_text="$2"
  local subject="F1 refresh FAILED — ${race}"
  curl -fsS --max-time 15 \
    -H "Title: ${subject}" \
    -H "Tags: warning" \
    -H "Click: https://kevnull.github.io/f1-fantasy-tips/" \
    --data-binary "${tail_text}" \
    "https://ntfy.sh/${NTFY_TOPIC}" >/dev/null \
    || echo "[warn] ntfy failure notify failed"
}

# Run the whole pipeline, tee'ing to log so we can extract failure tails.
run_pipeline() {
  set -e

  # Self-heal: yt-dlp goes stale every few months as YouTube changes its page format.
  if command -v brew >/dev/null 2>&1; then
    brew upgrade yt-dlp >/dev/null 2>&1 || echo "[warn] yt-dlp upgrade skipped/failed"
  fi

  .venv/bin/python src/main.py

  # Make sure we're not behind origin before attempting to push (GitHub Actions
  # pushes daily re-render commits to main).
  git fetch origin main --quiet || true
  if ! git pull --rebase --autostash origin main; then
    echo "[error] rebase failed; aborting push to avoid making it worse"
    git rebase --abort 2>/dev/null || true
    return 1
  fi

  # Commit + push only if something actually changed.
  if ! git diff --quiet -- data/strategy.json docs/ data/archive 2>/dev/null \
     || [[ -n "$(git status --porcelain data/strategy.json docs/ data/archive 2>/dev/null)" ]]; then
    git add data/strategy.json docs/ data/archive data/cache/photos 2>/dev/null || true
    RACE_LINE=$(.venv/bin/python -c "import json; print(json.load(open('data/strategy.json')).get('race','GP'))")
    git commit -m "Refresh strategy: $RACE_LINE [automated]" || echo "[info] nothing to commit"
    git push
    echo "=== pushed ==="
    echo "__PUSHED__=1"
  else
    echo "=== no changes ==="
  fi
}

# Run pipeline capturing output. Preserve exit code.
if run_pipeline 2>&1 | tee "$TMP_LOG"; then
  RC=0
else
  RC=${PIPESTATUS[0]}
fi

RACE=$(.venv/bin/python -c "import json; print(json.load(open('data/strategy.json')).get('race','GP'))" 2>/dev/null || echo "unknown")

if [[ "$RC" -ne 0 ]]; then
  TAIL=$(tail -20 "$TMP_LOG")
  notify_failure "$RACE" "$TAIL"
  exit "$RC"
fi

# Only notify on actual push (new content), not "no changes" days.
if grep -q "^__PUSHED__=1$" "$TMP_LOG"; then
  SUMMARY="$(mktemp -t f1-summary.XXXXXX)"
  if .venv/bin/python scripts/notify.py > "$SUMMARY" 2>/dev/null && [[ -s "$SUMMARY" ]]; then
    notify_success "$RACE" "$SUMMARY"
  else
    # Fallback to a one-liner if summary build fails.
    echo "F1 Fantasy: ${RACE} updated. https://kevnull.github.io/f1-fantasy-tips/" > "$SUMMARY"
    notify_success "$RACE" "$SUMMARY"
  fi
  rm -f "$SUMMARY"
fi

exit 0
