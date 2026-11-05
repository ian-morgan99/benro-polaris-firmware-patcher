#!/usr/bin/env bash
# pin-divergence-check.sh — does a candidate libgphoto2 pin carry everything the previous pin had?
#
# Why this exists: v95 was about to pin 855f718e (tip of feature/polaris-capture-events).
# That commit contains the #235 shutter gate, but it branched off driver main at 83240b36a on
# 2026-10-28 and never took 12 commits that landed on main afterwards -- 9 of which touch shipped
# code (stale-session safety barriers, deferred Bulb cancellation, IT2 WB alias, RAW container
# format, AF release mode, K-1 live-view contract). Pinning it would have silently regressed v94.
#
# Reachability from a branch is NOT enough: 855f718e is perfectly reachable and is still missing
# work. This checks ancestry against the PREVIOUS pin, which is what "no regression" actually means.
#
# usage: pin-divergence-check.sh <repo> <candidate-sha> <baseline-sha> [ref-to-fetch...]
set -euo pipefail

REPO="${1:?usage: $0 <repo> <candidate-sha> <baseline-sha> [refs...]}"
CAND="${2:?missing candidate sha}"
BASE="${3:?missing baseline sha}"
shift 3

die() { echo "FAIL: $*" >&2; exit 1; }
g() { git -C "$REPO" "$@"; }

for s in "$CAND" "$BASE"; do
  case "$s" in (*[!0-9a-f]*) die "$s is not lower-case hex";; esac
  [ "${#s}" -eq 40 ] || die "$s is not a full 40-char SHA (got ${#s})"
  g cat-file -e "${s}^{commit}" 2>/dev/null || die "$s is not present in $REPO (fetch first)"
done

echo "repo:      $REPO"
echo "candidate: $(g log -1 --format='%h %ad %s' --date=short "$CAND" | cut -c1-72)"
echo "baseline:  $(g log -1 --format='%h %ad %s' --date=short "$BASE" | cut -c1-72)"

# 1. candidate must contain the baseline, or at least every non-doc commit in it
if g merge-base --is-ancestor "$BASE" "$CAND"; then
  echo "ancestry:  OK -- baseline is an ancestor of candidate (clean superset)"
  ANCESTRAL=1
else
  ANCESTRAL=0
  MB=$(g merge-base "$BASE" "$CAND")
  echo "ancestry:  DIVERGED at $(g log -1 --format='%h %ad' --date=short "$MB")"
  echo "           baseline has $(g rev-list --count "$MB..$BASE") commits the candidate lacks"
fi

# 2. patch-equivalence: which baseline commits are genuinely absent from the candidate?
MISSING=(); PRESENT=0
while read -r sign sha; do
  if [ "$sign" = "-" ]; then PRESENT=$((PRESENT+1)); else MISSING+=("$sha"); fi
done < <(g cherry "$CAND" "$BASE" 2>/dev/null || true)

echo "patch-equiv: $PRESENT already present, ${#MISSING[@]} genuinely missing"
[ "${#MISSING[@]}" -eq 0 ] && { echo "RESULT: PASS -- candidate carries the baseline"; exit 0; }

# 3. classify the missing ones by whether they touch shipped code
CODE=0; DOCS=0
for c in "${MISSING[@]}"; do
  subj=$(g log -1 --format='%s' "$c" | cut -c1-58)
  if g show --stat --format="" "$c" -- camlibs libgphoto2 2>/dev/null | grep -q "changed"; then
    CODE=$((CODE+1)); printf "  [CODE] %s %s\n" "${c:0:9}" "$subj"
  else
    DOCS=$((DOCS+1)); printf "  [docs] %s %s\n" "${c:0:9}" "$subj"
  fi
done

echo
if [ "$CODE" -gt 0 ]; then
  echo "RESULT: FAIL -- $CODE commit(s) touching shipped code are missing from the candidate."
  echo "        Pinning it would regress the baseline. Merge or cherry-pick first, then re-run."
  exit 1
fi
echo "RESULT: PASS (with note) -- only docs/test commits missing; no shipped-code regression."
exit 0
