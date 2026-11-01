#!/usr/bin/env bash
# Publish one complete Astro candidate to a unique PrivateResearch path.
# This intentionally does not use the user's dirty PrivateResearch checkout.
set -euo pipefail

BUILD="" PR_REPO="https://github.com/ian-morgan99/PrivateResearch.git"
PR_CHECKOUT="" NOTE="Astro candidate; build-only; physical qualification pending."
usage() {
  cat >&2 <<'EOF'
usage: scripts/publish-astro-candidate.sh --build out/astro-id
The default publication checkout is a fresh temporary clone. Set PR_CHECKOUT
only to a separate clean clone; the existing PrivateResearch worktree is not
safe because it contains unrelated dirty work.
EOF
  exit 2
}
die() { echo "ERROR: $*" >&2; exit 1; }
while [ $# -gt 0 ]; do
  case "$1" in
    --build) BUILD="$2"; shift 2;; --repo) PR_REPO="$2"; shift 2;;
    --checkout) PR_CHECKOUT="$2"; shift 2;; --note) NOTE="$2"; shift 2;;
    -h|--help) usage;; *) die "unknown option: $1";;
  esac
done
[ -n "$BUILD" ] || usage
[ -d "$BUILD" ] || die "candidate directory not found: $BUILD"
MANIFEST="$BUILD/astro-candidate-manifest.json"
[ -f "$MANIFEST" ] || die "candidate manifest missing"
[ -f "$BUILD/FwPkt.zip" ] || die "FwPkt.zip missing"
[ -f "$BUILD/astro-bundle.tar.gz" ] || die "astro-bundle.tar.gz missing"

readarray -t META < <(python3 - "$MANIFEST" <<'PY'
import json, sys
m=json.load(open(sys.argv[1], encoding="utf-8"))
print(m["display_fwver"])
print(m["candidate_id"])
print(m["firmware"]["packet"]["sha256"])
print(m["firmware"]["packet"]["md5"])
print(m["source"]["patcher_commit"])
print(m["source"]["libgphoto2_commit"])
PY
)
DISPLAY_FWVER="${META[0]}"; ID="${META[1]}"; ZIP_SHA="${META[2]}"; ZIP_MD5="${META[3]}"
PATCHER_SHA="${META[4]}"; LIBG_SHA="${META[5]}"
[ "$ID" = "$(basename "$BUILD")" ] || die "manifest candidate id does not match directory"
ACTUAL_SHA="$(sha256sum "$BUILD/FwPkt.zip" | awk '{print $1}')"
ACTUAL_MD5="$(md5sum "$BUILD/FwPkt.zip" | awk '{print $1}')"
[ "$ACTUAL_SHA" = "$ZIP_SHA" ] || die "FwPkt SHA-256 mismatch"
[ "$ACTUAL_MD5" = "$ZIP_MD5" ] || die "FwPkt MD5 mismatch"
DEST="firmware-packets/$DISPLAY_FWVER--$ID"

if [ -z "$PR_CHECKOUT" ]; then
  PR_CHECKOUT="$(mktemp -d "${TMPDIR:-/tmp}/privateresearch-astro.XXXXXX")"
  git clone --depth 1 "$PR_REPO" "$PR_CHECKOUT"
else
  [ -e "$PR_CHECKOUT/.git" ] || die "explicit publication checkout must already exist"
  [ -z "$(git -C "$PR_CHECKOUT" status --porcelain --untracked-files=all)" ] || \
    die "explicit publication checkout is dirty; no reset or overwrite will be attempted"
  git -C "$PR_CHECKOUT" fetch origin
  BRANCH="$(git -C "$PR_CHECKOUT" branch --show-current)"
  if [ "$BRANCH" = "main" ]; then
    git -C "$PR_CHECKOUT" checkout main >/dev/null 2>&1 || die "cannot select main"
  elif [ -z "$BRANCH" ] && [ "$(git -C "$PR_CHECKOUT" rev-parse HEAD)" = "$(git -C "$PR_CHECKOUT" rev-parse origin/main)" ]; then
    echo "using clean detached origin/main publication worktree"
  else
    die "explicit publication checkout must be main or clean detached origin/main"
  fi
  [ -z "$(git -C "$PR_CHECKOUT" status --porcelain --untracked-files=all)" ] || die "publication checkout became dirty"
fi
REMOTE="$(git -C "$PR_CHECKOUT" remote get-url origin)"
case "$REMOTE" in
  https://github.com/ian-morgan99/PrivateResearch*|git@github.com:ian-morgan99/PrivateResearch*) ;;
  *) die "publication checkout origin is not PrivateResearch: $REMOTE";;
esac
[ ! -e "$PR_CHECKOUT/$DEST" ] || die "refusing to overwrite existing publication: $DEST"
mkdir -p "$PR_CHECKOUT/$DEST"
cp "$BUILD/FwPkt.zip" "$PR_CHECKOUT/$DEST/"
cp "$BUILD/astro-bundle.tar.gz" "$PR_CHECKOUT/$DEST/"
cp "$MANIFEST" "$PR_CHECKOUT/$DEST/"
for file in install-manifest.json build-source-provenance.txt shared-camera-gate.txt \
  astro-test-transcript.txt install-status.txt; do
  [ -f "$BUILD/$file" ] && cp "$BUILD/$file" "$PR_CHECKOUT/$DEST/"
done
cat > "$PR_CHECKOUT/$DEST/README.md" <<EOF
# Astro candidate $DISPLAY_FWVER — $ID

This is a separately published Astro candidate. The FwPkt uses the shared
camera baseline recorded in astro-candidate-manifest.json; the Astro solver,
catalogue and indexes are in astro-bundle.tar.gz.

| field | value |
|---|---|
| candidate | $ID |
| display firmware version | $DISPLAY_FWVER |
| FwPkt SHA-256 | $ACTUAL_SHA |
| FwPkt MD5 | $ACTUAL_MD5 |
| patcher commit | $PATCHER_SHA |
| libgphoto2 commit | $LIBG_SHA |
| status | candidate, not installed |
| note | $NOTE |

Do not install from this directory until the standard camera owner accepts the
baseline, issue #251 is closed or explicitly waived, and a supervised hardware
window is scheduled. Use the documented ZIP/Bluetooth-wake process only.
EOF
git -C "$PR_CHECKOUT" add "$DEST"
git -C "$PR_CHECKOUT" commit -m "astro candidate: add $DISPLAY_FWVER--$ID"
git -C "$PR_CHECKOUT" push origin main
echo "published=$DEST"
echo "FwPkt SHA-256=$ACTUAL_SHA"
echo "FwPkt MD5=$ACTUAL_MD5"
echo "publication checkout=$PR_CHECKOUT"
