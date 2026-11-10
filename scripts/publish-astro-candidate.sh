#!/usr/bin/env bash
# Publish one complete Astro candidate to a unique PrivateResearch path.
# This intentionally does not use the user's dirty PrivateResearch checkout.
set -euo pipefail

BUILD="" PR_REPO="https://github.com/ian-morgan99/PrivateResearch.git"
PR_CHECKOUT="" NOTE="Astro candidate; build-only; physical qualification pending." STATUS="gated"
SUPERSEDED_BY=""
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
    --status) STATUS="$2"; shift 2;;
    --superseded-by) SUPERSEDED_BY="$2"; shift 2;;
    -h|--help) usage;; *) die "unknown option: $1";;
  esac
done
[ -n "$BUILD" ] || usage
[ -d "$BUILD" ] || die "candidate directory not found: $BUILD"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="$BUILD/astro-candidate-manifest.json"
[ -f "$MANIFEST" ] || die "candidate manifest missing"
[ -f "$BUILD/FwPkt.zip" ] || die "FwPkt.zip missing"
[ -f "$BUILD/astro-bundle.tar.gz" ] || die "astro-bundle.tar.gz missing"
[ -f "$BUILD/release-change-manifest.json" ] || die "release-change-manifest.json missing"
[ -f "$BUILD/RELEASE-IDENTITY.md" ] || die "RELEASE-IDENTITY.md missing"
case "$STATUS" in gated|published|installed-verified) ;; *) die "unsupported publication status: $STATUS";; esac
python3 "$REPO_ROOT/scripts/verify-candidate-identity.py" "$BUILD" --require-deployable

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
EXISTING=0
if [ -e "$PR_CHECKOUT/$DEST" ]; then
  EXISTING=1
  [ -f "$PR_CHECKOUT/$DEST/FwPkt.zip" ] || die "existing publication has no FwPkt.zip: $DEST"
  cmp -s "$BUILD/FwPkt.zip" "$PR_CHECKOUT/$DEST/FwPkt.zip" || die "refusing to replace published ZIP bytes for existing candidate: $DEST"
else
  mkdir -p "$PR_CHECKOUT/$DEST"
  cp "$BUILD/FwPkt.zip" "$PR_CHECKOUT/$DEST/"
  cp "$BUILD/astro-bundle.tar.gz" "$PR_CHECKOUT/$DEST/"
fi

# The two SD-rooted archives are what a user actually copies onto the card, so they
# belong at the top of the publication beside FwPkt.zip rather than only inside
# astro-bundle.tar.gz. Before this, reaching polaris-wifi.zip meant untarring the
# bundle first, and the archive that had been verified to unzip at the card root was
# not the artifact anyone was handed.
#
# Guarded by the same refuse-to-replace rule as FwPkt.zip: once bytes are public they
# must not change silently under the same candidate name.
SD_ROOT="$BUILD/astro-bundle/COPY-TO-SD-CARD-ROOT"
for sdzip in polaris-astro.zip polaris-wifi.zip astrometry-indexes.zip; do
  [ -f "$SD_ROOT/$sdzip" ] || continue
  if [ "$EXISTING" = 1 ] && [ -f "$PR_CHECKOUT/$DEST/$sdzip" ]; then
    cmp -s "$SD_ROOT/$sdzip" "$PR_CHECKOUT/$DEST/$sdzip" \
      || die "refusing to replace published $sdzip bytes for existing candidate: $DEST"
  else
    cp "$SD_ROOT/$sdzip" "$PR_CHECKOUT/$DEST/"
  fi
done
ASTRO_ZIP_SHA=""; WIFI_ZIP_SHA=""; INDEX_ZIP_SHA=""
[ -f "$PR_CHECKOUT/$DEST/polaris-astro.zip" ] && \
  ASTRO_ZIP_SHA=$(sha256sum "$PR_CHECKOUT/$DEST/polaris-astro.zip" | awk '{print $1}')
[ -f "$PR_CHECKOUT/$DEST/polaris-wifi.zip" ] && \
  WIFI_ZIP_SHA=$(sha256sum "$PR_CHECKOUT/$DEST/polaris-wifi.zip" | awk '{print $1}')
[ -f "$PR_CHECKOUT/$DEST/astrometry-indexes.zip" ] && \
  INDEX_ZIP_SHA=$(sha256sum "$PR_CHECKOUT/$DEST/astrometry-indexes.zip" | awk '{print $1}')
SD_ROWS=""
[ -n "$ASTRO_ZIP_SHA" ] && SD_ROWS="${SD_ROWS}| polaris-astro.zip SHA-256 | \`$ASTRO_ZIP_SHA\` |"$'\n'
[ -n "$WIFI_ZIP_SHA" ] && SD_ROWS="${SD_ROWS}| polaris-wifi.zip SHA-256 | \`$WIFI_ZIP_SHA\` |"$'\n'
# Route A step 3 tells the user to copy this archive, so it needs a digest to check
# against like the other two. Without one they cannot tell a truncated download from a
# good one, and a missing astrometry/ folder solves nothing while looking healthy.
[ -n "$INDEX_ZIP_SHA" ] && SD_ROWS="${SD_ROWS}| astrometry-indexes.zip SHA-256 | \`$INDEX_ZIP_SHA\` |"$'\n'

cp "$MANIFEST" "$PR_CHECKOUT/$DEST/"
for file in install-manifest.json build-source-provenance.txt release-change-manifest.json \
  RELEASE-IDENTITY.md shared-camera-gate.txt astro-test-transcript.txt install-status.txt \
  install.log install-receipt.txt; do
  [ -f "$BUILD/$file" ] && cp "$BUILD/$file" "$PR_CHECKOUT/$DEST/"
done
# A superseded build stays published -- published bytes must not change under the same
# candidate name -- but its README must not read as installable. Without this, someone
# landing on 6.0.0.54.102 finds working-looking Route A steps and installs a build whose
# goto solver exits 2.
SUPERSEDED_BANNER=""
if [ -n "$SUPERSEDED_BY" ]; then
  # One quoted multi-line string. Appending $'\n' on separate lines looks equivalent
  # and is not: without a joining operator bash treats each following line as its own
  # command, so it dies at runtime while bash -n passes -- the same class of bug as the
  # comment line in build-astro-candidate.sh that lost its '#'.
  SUPERSEDED_BANNER="> **DO NOT INSTALL THIS BUILD.** It is superseded by $SUPERSEDED_BY.
> Published bytes are kept unchanged so the record stays verifiable, but nothing
> in this folder should be copied onto a card.
"
fi

cat > "$PR_CHECKOUT/$DEST/README.md" <<EOF
# Astro candidate $DISPLAY_FWVER — $ID

$SUPERSEDED_BANNER
This is a separately published Astro candidate. The FwPkt uses the shared
camera baseline recorded in astro-candidate-manifest.json.

Everything you need for Route A below is a .zip. No tar tool is required, and
none of the on-device extractors handle .tar.gz -- astro-bundle.tar.gz exists
for inspection and licensing only, and opening it needs 'tar xzf' on a PC.

There are two ways to install, and they are not interchangeable. Route A needs the microSD
card plus one ssh command -- no PC tooling, no repo, no build. Route B needs a PC, SSH and
this repo, and is the only one that can prove an install happened.

## Route A -- SD card plus one ssh command (no repo, no build)

1. Copy FwPkt.zip to the SD card root and EXTRACT it there, so the card ends up with a
   FwPkt/ folder containing camera/config, camera/uImage, camera/rootfs.ubifs and
   camera/appfs.ubifs. Do not leave it as a zip: the on-boot watcher reads the extracted
   tree and silently ignores an archive sitting beside it (issue #58).
2. Copy polaris-astro.zip and polaris-wifi.zip to the SD card root and extract each.
   Both are rooted at their own directory with no wrapper, so they expand to
   polaris-astro/ and polaris-wifi/ directly on the card. Repeat every release.
3. Copy astrometry-indexes.zip to the SD card root and extract it. It is rooted at
   astrometry/, so it expands to <SD root>/astrometry/index-41xx.fits. This is a
   one-time copy -- the index files themselves do not change between releases, so skip
   it if the folder is already on the card. Note that the archive's SHA-256 below does
   change from release to release even when the index files are identical: zip embeds
   each file's build timestamp, so a different hash here is not evidence of a different
   card payload. It is NOT inside polaris-astro.zip: without those index files
   install_astro.sh prints "NO index files ... NOTHING WILL SOLVE" and the solver
   never resolves a frame while everything else looks healthy.
4. Run the installer over ssh:

       ssh root@<polaris ip> /app/sd/polaris-astro/install_astro.sh

   This is what installs the boot hook and copies the kit into /app/astro. Nothing
   runs it for you: no shipped boot path calls install_astro.sh, so a card that has
   simply been rebooted will flash the firmware from step 1 and then start nothing
   astro-related. It also chains any pre-existing hook (the patcher's --ssh-key option
   uses the same file), so ssh keeps working.

   Run it after EVERY release, not just the first one. Flashing FwPkt replaces /app
   wholesale, which deletes both /app/astro and the boot hook that was installed there.
   A device that upgrades its firmware without re-running this command comes back on
   the new firmware with no astro stack at all, and nothing tells you so.

   The first line it prints is how much room /app has. That partition is 68 MB and a
   flashed firmware image uses most of it, so "free on /app/astro" is often small. You may
   also see a line saying the solve data stays on the SD card -- that is correct and
   deliberate: every solver reads the catalogue from /app/sd/polaris-astro, which is where
   step 2 put it, and /app is far too small to hold a copy. What must NOT be missing is the
   line "boot hook installed".

   Also look for "verified every manifest entry against /app/astro". If instead it says
   "installed files are unverified", the polaris-astro folder on your card came from an
   older release -- re-extract polaris-astro.zip from this one and run it again. Without
   that verification an old server can stay in place while the install reports success.
5. Reboot the camera. Wi-Fi auto-join stays off until you create the file
   polaris-wifi/autojoin.
6. Confirm two separate things, because they are independent and one passing does not
   mean the other did:

   - Firmware: read the version in the app. It must show $DISPLAY_FWVER. This is the
     only check available without a PC, and a reboot that did not flash looks identical
     to one that did -- so read it, do not assume it.
   - Astro stack: open http://<polaris ip>:8090 in a browser on the same network. The
     web UI appearing is the proof that the kit installed in step 4 actually started.
     A correct firmware version with no page on port 8090 means step 4 was skipped or
     did not finish.

astro-bundle.tar.gz contains the same trees plus licences and manifests. It is for
inspection, not for copying onto the card, and it needs tar rather than unzip.

## Route B -- systematic install (maintainers)

    ./scripts/release/release-fwpkt.sh out/$ID

Stages the extracted FwPkt tree, verifies every firmwareInfo MD5 on the device,
records /proc/uptime before rebooting to prove the boot actually reset, and confirms
build_id, both source commits and mandatory file SHA-256s afterwards. See
docs/FIRMWARE-INSTALL-PROCESS.md.

This flashes firmware only. It does not install, update, or restore the astro kit, and
it prints installed-verified whether or not /app/astro exists. Flashing replaces /app,
so on a device that already had the kit this leaves it gone -- server binary, scripts
and boot hook all removed at once -- with the same installed-verified line at the end.
Confirmed on-device upgrading to $DISPLAY_FWVER: after the flash /app/astro was empty
and port 8090 closed, and the kit had to be reinstalled from the card:

    ssh root@<polaris ip> /app/sd/polaris-astro/install_astro.sh

Then reboot and check http://<polaris ip>:8090. installed-verified on its own is not
evidence that the device can solve anything.

| field | value |
|---|---|
| candidate | $ID |
| display firmware version | $DISPLAY_FWVER |
| FwPkt SHA-256 | $ACTUAL_SHA |
| FwPkt MD5 | $ACTUAL_MD5 |
$SD_ROWS| patcher commit | $PATCHER_SHA |
| libgphoto2 commit | $LIBG_SHA |
| status | $STATUS |
| note | $NOTE |

Do not install from this directory until the standard camera owner accepts the
baseline, issue #251 is closed or explicitly waived, and a supervised hardware
window is scheduled. Use the documented ZIP/Bluetooth-wake process only.
EOF
git -C "$PR_CHECKOUT" add --sparse "$DEST"
if [ "$EXISTING" = 1 ]; then
  git -C "$PR_CHECKOUT" commit -m "astro candidate: update $DISPLAY_FWVER--$ID status"
else
  git -C "$PR_CHECKOUT" commit -m "astro candidate: add $DISPLAY_FWVER--$ID"
fi
git -C "$PR_CHECKOUT" push origin HEAD:main
echo "published=$DEST"
echo "FwPkt SHA-256=$ACTUAL_SHA"
echo "FwPkt MD5=$ACTUAL_MD5"
echo "publication checkout=$PR_CHECKOUT"
