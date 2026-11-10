#!/bin/sh
# Prove install_astro.sh still installs the boot hook when /app runs out of space.
#
# Reproduces the 6.0.0.54.104 failure: a firmware flash replaces /app and leaves
# it nearly full, the catalogue copy hits ENOSPC, and the old script died under
# set -e BEFORE writing /app/network_telnetd.sh -- leaving polaris-httpd on disk
# with nothing to start it at boot.
#
# The installer hardcodes /app paths, so a copy is rewritten into a sandbox first.
# A stub cp then fails only on the optional catalogue payloads (.pcat/.polcat/
# .ptri), exactly as a full UBIFS would, and passes everything else through.
#
#   sh test-install-enospc.sh <path-to-install_astro.sh>
set -e

INSTALLER="$1"
[ -f "$INSTALLER" ] || { echo "usage: $0 <path-to-install_astro.sh>"; exit 2; }

SRC=$(mktemp -d)
ROOT=$(mktemp -d)
BIN="$ROOT/bin"
mkdir -p "$SRC/catalogue-tiles" "$BIN" "$ROOT/app/astro" \
         "$ROOT/app/sd/polaris-astro" "$ROOT/app/sd/astrometry"

# Rewrite the installer's absolute /app paths into the sandbox.
sed "s#/app/#$ROOT/app/#g" "$INSTALLER" > "$ROOT/install_astro.sh"

# --- a bundle that looks real -------------------------------------------------
for b in polaris-solve polaris-solve-independent polaris-solve-independent-search \
         polaris-exif-solve polaris-skysim-independent polaris-extract polaris-mount \
         polaris-httpd polaris-logwatch polaris-match; do
    printf '#!/bin/sh\necho %s\n' "$b" > "$SRC/$b"; chmod +x "$SRC/$b"
done
for s in polaris-astro-boot.sh polaris-align.sh polaris-guide.sh \
         polaris-frame-watch.sh polaris-autosolve.sh polaris-astro-sync.sh; do
    printf '#!/bin/sh\n# %s\n' "$s" > "$SRC/$s"; chmod +x "$SRC/$s"
done
printf '#!/bin/sh\n# polaris-astro boot hook\n' > "$SRC/polaris-astro-boot.sh"
: > "$SRC/site.conf.example"
: > "$SRC/camera-sensors.tsv"
: > "$SRC/catalogue.polcat"
: > "$SRC/catalogue-tiles.manifest.json"
: > "$SRC/catalogue-tiles.ptri"
i=1; while [ $i -le 40 ]; do : > "$SRC/catalogue-tiles/tile-$(printf %03d $i).pcat"; i=$((i+1)); done

# WITH_MANIFEST=1 gives the bundle a polaris-astro.manifest, which is what turns
# install_astro.sh's byte comparison on. Without it the installer prints "installed
# files are unverified" and skips the check -- which is exactly what every published
# astro candidate did until build-astro-candidate.sh started generating one.
if [ "${WITH_MANIFEST:-0}" = 1 ]; then
    (
      cd "$SRC"
      { for b in polaris-httpd polaris-solve polaris-solve-independent \
                 polaris-solve-independent-search polaris-exif-solve \
                 polaris-skysim-independent polaris-extract polaris-logwatch \
                 polaris-match polaris-mount; do
          [ -f "$b" ] && printf '%s\n' "$b"
        done
        for s in *.sh; do [ -f "$s" ] && printf '%s\n' "$s"; done
      } | sort -u | while IFS= read -r f; do sha256sum "$f"; done
    ) > "$SRC/polaris-astro.manifest"
fi

# TAMPER=1 changes a binary AFTER the manifest was written, simulating a stale or
# substituted polaris-httpd. The installer must refuse to claim success.
if [ "${TAMPER:-0}" = 1 ]; then
    printf '#!/bin/sh\necho tampered\n' > "$SRC/polaris-httpd"
fi

# --- stub cp: ENOSPC on the optional catalogue data only ----------------------
# NOSPACE=0 turns the failure off, so the same script doubles as a happy-path
# regression check: with room on /app everything must still land.
NOSPACE=${NOSPACE:-1}
cat > "$BIN/cp" <<STUB
#!/bin/sh
if [ "$NOSPACE" = 1 ]; then
  case "\$1" in
    *.pcat|*.polcat|*.ptri|*/catalogue-tiles.manifest.json)
      echo "cp: write error: No space left on device" >&2
      exit 1
      ;;
  esac
fi
exec /bin/cp "\$@"
STUB
chmod +x "$BIN/cp"

# --- run it ------------------------------------------------------------------
set +e
out=$(cd "$SRC" && PATH="$BIN:$PATH" SRC="$SRC" DEST="$ROOT/app/astro" \
      INDEXES="$ROOT/app/sd/astrometry" \
      CONF="$ROOT/app/sd/polaris-astro/site.conf" \
      sh "$ROOT/install_astro.sh" 2>&1)
rc=$?
set -e
echo "$out" | sed 's/^/    /'
echo "  ---- installer exit code: $rc ----"

fail=0
# A tampered bundle must be REJECTED, not installed quietly.
if [ "${TAMPER:-0}" = 1 ]; then
    if [ $rc -ne 0 ] && echo "$out" | grep -qi "NOT verified"; then
        echo "PASS  tampered binary rejected (rc=$rc)"
    else
        echo "FAIL  tampered binary accepted -- manifest check did not run"
        fail=1
    fi
    rm -rf "$SRC" "$ROOT"
    [ $fail -eq 0 ] && echo "== ALL PASS ==" || echo "== FAILURES =="
    exit $fail
fi

if [ "${WITH_MANIFEST:-0}" = 1 ]; then
    if echo "$out" | grep -q "verified every manifest entry"; then
        echo "PASS  byte verification ran against the manifest"
    else
        echo "FAIL  manifest present but verification did not run"
        fail=1
    fi
fi

if [ -x "$ROOT/app/network_telnetd.sh" ] && \
   grep -q "polaris-astro boot hook" "$ROOT/app/network_telnetd.sh"; then
    if [ "$NOSPACE" = 1 ]; then
        echo "PASS  boot hook installed despite ENOSPC"
    else
        echo "PASS  boot hook installed"
    fi
else
    echo "FAIL  boot hook MISSING -- device would not autostart"
    fail=1
fi
if [ -x "$ROOT/app/astro/polaris-httpd" ]; then
    echo "PASS  polaris-httpd installed and executable"
else
    echo "FAIL  polaris-httpd missing or not executable"
    fail=1
fi
if [ $rc -eq 0 ]; then
    echo "PASS  installer completed (optional data skipped, not fatal)"
else
    echo "FAIL  installer aborted with rc=$rc"
    fail=1
fi
if [ "$NOSPACE" = 1 ]; then
    # It must have said why, rather than dying on a bare cp error.
    if echo "$out" | grep -qi "did not fit"; then
        echo "PASS  reported the skipped catalogue copy explicitly"
    else
        echo "FAIL  silent about the failed catalogue copy"
        fail=1
    fi
else
    # Happy path: the optional data should actually be present.
    if [ -f "$ROOT/app/astro/catalogue-tiles.ptri" ] && \
       [ -d "$ROOT/app/astro/catalogue-tiles" ]; then
        echo "PASS  optional catalogue copied when there is room"
    else
        echo "FAIL  optional catalogue missing although space was available"
        fail=1
    fi
fi

rm -rf "$SRC" "$ROOT"
[ $fail -eq 0 ] && echo "== ALL PASS ==" || echo "== FAILURES =="
exit $fail
