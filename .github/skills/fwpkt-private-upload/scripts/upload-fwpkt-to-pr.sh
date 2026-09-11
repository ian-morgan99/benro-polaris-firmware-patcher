#!/usr/bin/env bash
# upload-fwpkt-to-pr.sh — publish a freshly built FwPkt.zip to the PRIVATE
# ian-morgan99/PrivateResearch repo so other agents can fetch it online.
#
# This is the "zip_location" half of docs/FWPKT-PROVENANCE-CONTRACT.md:
#   - public repos (BenroPolarisPatcher, OpenPolaris, libgphoto2 fork) keep
#     only the registry ROW (hashes + commit links);
#   - the zip BYTES live here, in the private repo, under
#     firmware-packets/<registry-id>/.
#
# Usage:
#   bash .github/skills/fwpkt-private-upload/scripts/upload-fwpkt-to-pr.sh \
#        --build out/k1ii-k3iii-v8-modelgate-20260910 \
#        --id o-v8 \
#        [--status candidate] [--note "model-gate fix 0953dde"] \
#        [--dry-run]
#
# Env:
#   GH_TOKEN      GitHub token with write access to ian-morgan99/PrivateResearch.
#                 Without it the script relies on whatever git credential
#                 helper is configured (works if you are already logged in).
#   PR_REPO       Override the private repo URL (default below).
#   PR_CHECKOUT   Override the local checkout path (default below).
#
# The script:
#   1. recomputes zip MD5 + SHA-256 from the actual file (never copied forward),
#   2. runs BOTH offline gates (structural + firmwareInfo manifest),
#   3. stages FwPkt.zip + README.md (+ build-source-provenance.txt if present)
#      into firmware-packets/<id>/ in a clean checkout of the private repo,
#   4. commits + pushes, then prints a paste-ready registry row for
#      docs/FWPKT-PROVENANCE-CONTRACT.md.
set -euo pipefail

PR_REPO="${PR_REPO:-https://github.com/ian-morgan99/PrivateResearch.git}"
PR_CHECKOUT="${PR_CHECKOUT:-$HOME/Documents/VSCodeProjects/PrivateResearch}"
BUILD="" ID="" STATUS="candidate" NOTE="" DRY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --build) BUILD="$2"; shift 2;;
    --id)    ID="$2"; shift 2;;
    --status) STATUS="$2"; shift 2;;
    --note)  NOTE="$2"; shift 2;;
    --dry-run) DRY=1; shift;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

[ -n "$BUILD" ] && [ -n "$ID" ] || {
  echo "usage: $0 --build <out/<name>> --id <registry-id> [--status S] [--note N] [--dry-run]" >&2
  exit 2; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
ZIP="$BUILD/FwPkt.zip"
[ -f "$ZIP" ] || { echo "FATAL: $ZIP not found (build dir must contain FwPkt.zip)" >&2; exit 1; }

echo "== 1. fingerprints (recomputed from the actual file) =="
ZIP_MD5="$(md5sum "$ZIP" | awk '{print $1}')"
ZIP_SHA256="$(sha256sum "$ZIP" | awk '{print $1}')"
echo "zip MD5:    $ZIP_MD5"
echo "zip SHA-256: $ZIP_SHA256"

echo "== 2a. structural gate (validate_fw_package.py) =="
python3 "$REPO_ROOT/container/validate_fw_package.py" "$ZIP"

echo "== 2b. manifest gate (firmwareInfo vs shipped bytes, on-board check) =="
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
unzip -q "$ZIP" -d "$TMP"
python3 - "$TMP/FwPkt" <<'PY'
import hashlib, os, re, sys, glob
root = sys.argv[1]
fi = os.path.join(root, "firmwareInfo")

# Same key->path resolution as container/verify_firmwareinfo.py
def resolve(key):
    fixed = {
        "config": "camera/config",
        "uImage": "camera/uImage",
        "rootfs": "camera/rootfs.ubifs",
        "appfs":  "camera/appfs.ubifs",
    }
    if key in fixed:
        return os.path.join(root, fixed[key])
    if key.startswith("polaris") or key == "oms":
        hits = glob.glob(os.path.join(root, "gimbal", key + "_*.bin"))
        return hits[0] if hits else None
    return None

ok = True
for raw in open(fi):
    m = re.match(r"^(\w+)\s+size:(\d+);\1\s+MD5:([0-9a-fA-F]+);", raw.strip())
    if not m:
        continue  # non-entry line
    key, size, md5 = m.group(1), int(m.group(2)), m.group(3).lower()
    path = resolve(key)
    if path is None or not os.path.isfile(path):
        print("MISSING  %s (listed in firmwareInfo, not on disk)" % key); ok = False; continue
    actual_size = os.path.getsize(path)
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    actual_md5 = h.hexdigest()
    if not (actual_size == size and actual_md5 == md5):
        print("MISMATCH %s: claimed size=%d md5=%s, actual size=%d md5=%s"
              % (key, size, md5, actual_size, actual_md5)); ok = False
    else:
        print("ok       %s (%d B)" % (key, actual_size))
sys.exit(0 if ok else 1)
PY

# appfs MD5 for the registry row (from the manifest we just verified)
APPFS_MD5="$(grep -oE '^appfs size:[0-9]+;appfs MD5:[0-9a-fA-F]+' "$TMP/FwPkt/firmwareInfo" | grep -oE 'MD5:[0-9a-fA-F]+' | cut -d: -f2)"
[ -n "$APPFS_MD5" ] || { echo "FATAL: could not find appfs MD5 in firmwareInfo" >&2; exit 1; }
echo "appfs MD5:  $APPFS_MD5"

# libgphoto2 commit, if the build recorded it
LIBG_SHA="?"
if [ -f "$BUILD/build-source-provenance.txt" ]; then
  LIBG_SHA="$(grep -m1 '^git_commit=' "$BUILD/build-source-provenance.txt" | cut -d= -f2 || true)"
  [ -n "$LIBG_SHA" ] || LIBG_SHA="?"
fi
PATCHER_REF="$(cd "$REPO_ROOT" && git rev-parse --short HEAD 2>/dev/null || echo '?')/$(cd "$REPO_ROOT" && git branch --show-current 2>/dev/null || echo detached)"

echo "== 3. stage into private repo checkout =="
if [ "$DRY" = 1 ]; then
  # Dry-run: stage into a temp dir, no git at all (no auth needed).
  STAGE_ROOT="$TMP/pr-stage"
  STAGE_DIR="$STAGE_ROOT/firmware-packets/$ID"
else
  if [ -d "$PR_CHECKOUT/.git" ]; then
    git -C "$PR_CHECKOUT" fetch origin
    git -C "$PR_CHECKOUT" checkout main 2>/dev/null || git -C "$PR_CHECKOUT" checkout -b main origin/main
    git -C "$PR_CHECKOUT" reset --hard origin/main
  else
    mkdir -p "$(dirname "$PR_CHECKOUT")"
    git clone --depth 1 "$PR_REPO" "$PR_CHECKOUT"
  fi
  STAGE_DIR="$PR_CHECKOUT/firmware-packets/$ID"
fi
mkdir -p "$STAGE_DIR"
cp "$ZIP" "$STAGE_DIR/FwPkt.zip"
[ -f "$BUILD/build-source-provenance.txt" ] && cp "$BUILD/build-source-provenance.txt" "$STAGE_DIR/"

cat > "$STAGE_DIR/README.md" <<EOF
# FwPkt $ID

| field | value |
|---|---|
| registry id | \`$ID\` |
| zip MD5 | \`$ZIP_MD5\` |
| zip SHA-256 | \`$ZIP_SHA256\` |
| appfs MD5 | \`$APPFS_MD5\` |
| libgphoto2 commit | \`$LIBG_SHA\` |
| patcher ref | \`$PATCHER_REF\` |
| status | $STATUS |
| built | $(date -u +%Y-%m-%dT%H:%M:%SZ) from \`${BUILD#*/}\` |
${NOTE:+| note | $NOTE |}

Verify before staging on a device (per the provenance contract handoff rule):

\`\`\`bash
md5sum FwPkt.zip        # must equal zip MD5 above
sha256sum FwPkt.zip     # must equal zip SHA-256 above
unzip -p FwPkt.zip FwPkt/firmwareInfo | grep '^appfs'   # appfs MD5 must match
\`\`\`

Registry row: \`docs/FWPKT-PROVENANCE-CONTRACT.md\` in
ian-morgan99/benro-polaris-firmware-patcher.
EOF

echo "== 4. commit + push =="
if [ "$DRY" = 1 ]; then
  echo "(dry-run) would commit firmware-packets/$ID and push to $PR_REPO"
else
  git -C "$PR_CHECKOUT" add "firmware-packets/$ID"
  git -C "$PR_CHECKOUT" commit -m "firmware-packets: add $ID (zip md5 $ZIP_MD5)"
  if [ -n "${GH_TOKEN:-}" ]; then
    # push via a token-embedded URL so the token never lands in .git/config
    git -C "$PR_CHECKOUT" push "https://x-access-token:${GH_TOKEN}@github.com/ian-morgan99/PrivateResearch.git" HEAD:main
  else
    git -C "$PR_CHECKOUT" push origin main
  fi
fi

echo "== 5. paste-ready registry row (docs/FWPKT-PROVENANCE-CONTRACT.md) =="
cat <<EOF
| $ID | \`firmware-packets/$ID/FwPkt.zip\` (ian-morgan99/PrivateResearch, private) | \`$ZIP_MD5\` | \`$(echo "$ZIP_SHA256" | cut -c1-16)\` | \`$APPFS_MD5\` | \`$LIBG_SHA\` | patcher @ \`$PATCHER_REF\` | $STATUS | ${NOTE:-uploaded via fwpkt-private-upload skill} |
EOF
echo "done."
