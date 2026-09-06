#!/bin/bash
# poll-github-issues.sh — periodic triage poller for new GitHub issues.
#
# Watches:
#   - ian-morgan99/benro-polaris-firmware-patcher (this repo)
#   - ian-morgan99/libgphoto2 (library half of the stack)
#
# For every NEW open issue it has not seen before, it logs a triage comment:
#   - which side owns it (patcher runtime vs libgphoto2 driver),
#   - the first concrete next step,
#   - cross-refs to related issues.
# State is kept in .github-issue-poll-state (one line per repo#issue).
#
# Usage:
#   bash scripts/poll-github-issues.sh            # one poll (for cron/systemd)
#   bash scripts/poll-github-issues.sh --loop 30m # poll every 30 minutes forever
#
# Requires: gh (authenticated), jq.

set -uo pipefail

REPOS=("ian-morgan99/benro-polaris-firmware-patcher" "ian-morgan99/libgphoto2")
STATE_FILE="$(cd "$(dirname "$0")/.." && pwd)/.github-issue-poll-state"
mkdir -p "$(dirname "$STATE_FILE")"
touch "$STATE_FILE"

log() { echo "[$(date '+%F %T')] $*"; }

triage_comment() {
  local repo="$1" num="$2" title="$3"
  local side next
  case "$repo" in
    *libgphoto2*)
      side="library (driver/camlib behavior)"
      next="Reproduce with gphoto2 --debug, attribute the failing PTP op, and check whether it is already covered by an open/closed fix on master before proposing a new change."
      ;;
    *)
      side="patcher/runtime (this repo)"
      next="Decide ownership (build pipeline vs on-disk runtime vs docs), record the decision in a comment, and link the issue to the umbrella (#15) if it blocks the canonical candidate."
      ;;
  esac
  cat <<EOF
## Auto-triage (poller, $(date '+%F %T'))

**Ownership:** $side
**First step:** $next

Cross-refs: check related open issues in both repos before duplicating work —
patcher runtime defects belong here; driver/camlib behavior belongs in
ian-morgan99/libgphoto2. If this issue is blocked on the other side, say so
explicitly and link the blocking issue.
EOF
}

poll_repo() {
  local repo="$1"
  local issues
  issues=$(gh issue list --repo "$repo" --state open --json number,title --limit 100 2>/dev/null \
    | jq -r '.[] | "\(.number)\t\(.title)"')
  [ -z "$issues" ] && { log "$repo: no open issues"; return; }

  while IFS=$'\t' read -r num title; do
    [ -z "$num" ] && continue
    if grep -q "^${repo}#${num}$" "$STATE_FILE"; then
      continue
    fi
    log "NEW issue in $repo: #$num — $title"
    triage_comment "$repo" "$num" "$title" > /tmp/poll-comment-$num.md
    if gh issue comment "$num" --repo "$repo" --body-file "/tmp/poll-comment-$num.md"; then
      log "  triage comment posted on $repo#$num"
    else
      log "  WARNING: failed to post triage comment on $repo#$num (will retry next poll)"
      continue
    fi
    echo "${repo}#${num}" >> "$STATE_FILE"
  done <<< "$issues"
}

seed_state() {
  log "first run: seeding state with all currently-open issues (no comments posted)"
  for repo in "${REPOS[@]}"; do
    gh issue list --repo "$repo" --state open --json number --limit 100 2>/dev/null \
      | jq -r '.[].number' | while read -r n; do echo "${repo}#${n}"; done >> "$STATE_FILE"
  done
}

poll_once() {
  # First run: record what already exists so we only triage issues that appear later.
  if [ ! -s "$STATE_FILE" ]; then
    seed_state
  fi
  for repo in "${REPOS[@]}"; do
    poll_repo "$repo"
  done
}

if [ "${1:-}" = "--loop" ]; then
  interval="${2:-30m}"
  log "polling ${REPOS[*]} every $interval (Ctrl-C to stop)"
  while true; do
    poll_once
    sleep "$interval"
  done
else
  poll_once
fi
