#!/bin/sh
# Astro in-place update regression test.
#
# Guards the failure this exists to fix: the boot hook used to install the astro
# stack only when /app/astro/polaris-httpd did not already exist, so unzipping a
# new release over an existing install changed NOTHING and reported success. Same
# class as issue #58 ("staged FwPkt.zip, rebooted, came back on .66") -- invisible
# because every step is green.
#
# Drives container/astro/ondisk/polaris-astro-sync.sh against a fake card and a
# fake install dir. Pure POSIX sh, no rig, no network. Skips (exit 2) if sha256sum
# is unavailable, per the exit-status policy in tests/run_deterministic.sh.
set -u
# This test lives in container/, which is also where tests/run_deterministic.sh
# executes from -- so the on-disk scripts are under $here/astro and the builder is
# one level up. Getting this wrong makes the test SKIP silently, which is exactly
# the kind of green-but-empty gate this repo has been burned by.
here="$(cd "$(dirname "$0")" && pwd)"
SYNC="$here/astro/ondisk/polaris-astro-sync.sh"
BOOT="$here/astro/ondisk/polaris-astro-boot.sh"
BUILDER="$here/../scripts/build-astro-bundle.sh"

command -v sha256sum >/dev/null 2>&1 || { echo "[astro-sync] SKIP: sha256sum not available"; exit 2; }
[ -f "$SYNC" ] || { echo "[astro-sync] FAIL: $SYNC not present"; exit 1; }
[ -f "$BOOT" ]    || { echo "[astro-sync] FAIL: $BOOT not present"; exit 1; }
[ -f "$BUILDER" ] || { echo "[astro-sync] FAIL: $BUILDER not present"; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT HUP INT TERM
SRC="$work/card/polaris-astro"
DEST="$work/app/astro"
mkdir -p "$SRC" "$DEST"

fail=0
ok()  { echo "  ok   $*"; }
bad() { echo "  FAIL $*"; fail=$((fail + 1)); }

# check <desc> <status>   -- status 0 passes
check() { if [ "$2" = "0" ]; then ok "$1"; else bad "$1 (status $2)"; fi; }

# expect_rc <desc> <want> <got>
expect_rc() { if [ "$3" = "$2" ]; then ok "$1 (rc $3)"; else bad "$1: want rc $2, got $3"; fi; }

# grepq <desc> <pattern> <file-or-'-'>   -- reads $OUT when file is '-'
grepq() {
    if [ "$3" = "-" ]; then printf '%s\n' "$OUT" | grep -q "$2"; else grep -q "$2" "$3"; fi
    check "$1" $?
}

# Build a card payload with a manifest, exactly as build-astro-bundle.sh emits it.
make_card() {
    printf '%s\n' "$1" > "$SRC/polaris-httpd"
    printf '%s\n' "solve" > "$SRC/polaris-solve"
    printf '%s\n' "match" > "$SRC/polaris-match"
    printf '%s\n' 'echo watcher' > "$SRC/polaris-frame-watch.sh"
    cp "$SYNC" "$SRC/polaris-astro-sync.sh"
    ( cd "$SRC"
      for f in polaris-httpd polaris-solve polaris-match; do sha256sum "$f"; done ) \
        > "$SRC/polaris-astro.manifest"
}

sync() { sh "$SYNC" sync "$@"   >"$work/out" 2>&1; rc=$?; OUT=$(cat "$work/out"); return $rc; }
verify() { sh "$SYNC" verify "$@" >"$work/out" 2>&1; rc=$?; OUT=$(cat "$work/out"); return $rc; }

echo "--- 1. fresh install copies every declared file ---"
make_card "V1 httpd"
sync "$SRC" "$DEST"; expect_rc "sync exits 0" 0 $?
[ -x "$DEST/polaris-httpd" ];      check "polaris-httpd installed and executable" $?
[ -x "$DEST/polaris-solve" ];      check "polaris-solve installed" $?
[ -f "$DEST/polaris-frame-watch.sh" ]; check "scripts copied too" $?
[ -s "$DEST/.astro-installed.sha256" ]; check "install stamped so updates are detectable" $?

echo "--- 2. re-running with an unchanged card is a no-op ---"
before=$(sha256sum "$DEST/polaris-httpd" | cut -d' ' -f1)
sync "$SRC" "$DEST"; expect_rc "second sync exits 0" 0 $?
printf '%s\n' "$OUT" | grep -q 'already up to date'; check "reports already up to date" $?
after=$(sha256sum "$DEST/polaris-httpd" | cut -d' ' -f1)
[ "$before" = "$after" ]; check "nothing rewritten" $?

echo "--- 3. verify agrees when in sync ---"
verify "$SRC" "$DEST"; expect_rc "verify exits 0 in sync" 0 $?

echo "--- 4. THE BUG: new release on the card, old install already present ---"
# The exact scenario that used to do nothing at all and still report success.
make_card "V2 httpd CHANGED"
verify "$SRC" "$DEST"; expect_rc "verify reports drift" 1 $?
grepq "verify names the drifted file" 'changed: polaris-httpd' '-'
sync "$SRC" "$DEST"; expect_rc "sync exits 0" 0 $?
printf '%s\n' "$OUT" | grep -q 'updated polaris-httpd'; check "names the file it updated" $?
[ "$(cat "$DEST/polaris-httpd")" = "V2 httpd CHANGED" ]
check "new content actually landed in the install dir" $?
verify "$SRC" "$DEST"; expect_rc "verify clean after update" 0 $?

echo "--- 5. only what changed is rewritten ---"
solve_before=$(sha256sum "$DEST/polaris-solve" | cut -d' ' -f1)
make_card "V3 httpd"
sync "$SRC" "$DEST"; expect_rc "sync exits 0" 0 $?
printf '%s\n' "$OUT" | grep -q 'updated 1 file'; check "updates exactly one file" $?
printf '%s\n' "$OUT" | grep -q 'updated polaris-solve' && bad "untouched file was rewritten" || ok "unchanged files left alone"
solve_after=$(sha256sum "$DEST/polaris-solve" | cut -d' ' -f1)
[ "$solve_before" = "$solve_after" ]; check "polaris-solve bytes unchanged" $?

echo "--- 6. a manifest naming a file the card lacks must FAIL and not stamp ---"
stamp_before=$(cat "$DEST/.astro-installed.sha256")
printf '%s\n' "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef  polaris-ghost" >> "$SRC/polaris-astro.manifest"
sync "$SRC" "$DEST"; expect_rc "sync fails closed on a missing bundle file" 1 $?
printf '%s\n' "$OUT" | grep -q 'not stamping'; check "declines to stamp a partial install" $?
stamp_after=$(cat "$DEST/.astro-installed.sha256")
[ "$stamp_before" = "$stamp_after" ]; check "stamp unchanged, so the next boot retries" $?

echo "--- 7. recovering after the bundle is fixed ---"
grep -v polaris-ghost "$SRC/polaris-astro.manifest" > "$SRC/m.tmp" && mv "$SRC/m.tmp" "$SRC/polaris-astro.manifest"
sync "$SRC" "$DEST"; expect_rc "sync succeeds again once the bundle is whole" 0 $?

echo "--- 8. an old card with no manifest still boots (fallback, loudly) ---"
LEGACY="$work/legacy-card"; LEGDEST="$work/legacy-astro"
mkdir -p "$LEGACY" "$LEGDEST"
printf '%s\n' "legacy httpd" > "$LEGACY/polaris-httpd"
sync "$LEGACY" "$LEGDEST"; expect_rc "fallback exits 0 rather than refusing to boot" 0 $?
printf '%s\n' "$OUT" | grep -q 'cannot be updated in place'; check "fallback warns that updates are impossible" $?
[ "$(cat "$LEGDEST/polaris-httpd")" = "legacy httpd" ]; check "fallback still installed the binary" $?
verify "$LEGACY" "$LEGDEST"; expect_rc "verify says 'cannot tell' (2), not failure" 2 $?

echo "--- 9. a corrupt manifest is refused, never half-applied ---"
BAD="$work/bad-card"; BADDEST="$work/bad-astro"
mkdir -p "$BAD" "$BADDEST"
printf '%s\n%s\n' "notahash polaris-httpd" "# comment only" > "$BAD/polaris-astro.manifest"
sync "$BAD" "$BADDEST"; expect_rc "refuses a manifest with no usable lines" 1 $?
[ ! -f "$BADDEST/polaris-httpd" ]; check "installed nothing from a garbage manifest" $?

echo "--- 10. no temp files left behind ---"
if find "$DEST" -name '*.part' -o -name '.astro-want.tmp' | grep -q .; then
    bad "leftover temp files"
else
    ok "no leftover temp files"
fi

echo "--- 11. the boot hook calls the sync script instead of gating on existence ---"
grepq "boot hook invokes polaris-astro-sync.sh" 'polaris-astro-sync.sh' "$BOOT"
grepq "existence gate kept only as legacy fallback" 'Card predates the sync script' "$BOOT"

echo "--- 12. the bundle builder emits the manifest and fails closed without it ---"
grepq "builder generates polaris-astro.manifest" 'polaris-astro.manifest' "$BUILDER"
grepq "builder refuses a bundle that cannot self-update" 'cannot update in place' "$BUILDER"
grepq "builder offers SD-rooted archives" 'also emit SD-rooted zips' "$BUILDER"
grepq "builder proves archives are SD-rooted" 'would not unzip to SD root' "$BUILDER"

echo
if [ "$fail" -ne 0 ]; then
    echo "FAILED: $fail assertion(s)"
    exit 1
fi
echo "ALL PASS"
