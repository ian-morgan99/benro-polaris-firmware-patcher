#!/bin/bash
# ============================================================================
#  Benro Polaris libgphoto2 patcher — in-container pipeline
#
#  Rebuilds the ptp2 camera driver from a chosen libgphoto2 release, minimally
#  patches the stock `pgphoto` binary so the firmware actually loads that driver
#  (instead of its compiled-in 2.5.27 copy), and repacks a flashable appfs.
#
#  Runs entirely inside the debian:9 image (see docker/Dockerfile).
#  Inputs/outputs are bind mounts:
#     /in   read-only stock FwPkt (folder containing camera/appfs.ubifs, ...)
#     /out  destination for the custom FwPkt/ and FwPkt.zip
#
#  Env:
#     LIBGPHOTO2_VERSION      libgphoto2 release tag to build    (default 2.5.34)
#     LIBGPHOTO2_PORT_VERSION libgphoto2_port release tag         (default 0.12.2)
#     PENTAX_MAX_CAPTURE_SIZE Pentax capture file-size cap in bytes (default 268435456 = 256 MiB)
#     FIX_R5M2_TYPO           1 = correct the upstream "EOS 5Rm2" model-name typo
#     SELFTEST                1 = qemu-emulate the driver load (needs qemu-arm-static)
#     SSH_PUBKEY              optional: authorized_keys line(s) to authorise for
#                             root SSH debugging (adds ONE new file to the appfs;
#                             issue #31 — opt-in, off by default)
#
#  SEE README.md AND docs/TESTED.md.  Use at your own risk.  Tested ONLY against
#  Benro Polaris FwVer 4.0.0.32 with a Canon EOS R5 Mark II.
# ============================================================================
set -euo pipefail

log(){ printf '\033[1;36m[patcher]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die(){ printf '\033[1;31m[abort]\033[0m %s\n' "$*" >&2; exit 1; }

LIBGPHOTO2_VERSION="${LIBGPHOTO2_VERSION:-2.5.34}"
LIBGPHOTO2_PORT_VERSION="${LIBGPHOTO2_PORT_VERSION:-0.12.2}"
# Pentax capture file-size budget in bytes (issue #2). libgphoto2's hard-coded
# default is 2 GiB which is unsafe on the Polaris' constrained RAM; a runaway
# DNG/RAW request from a K-1 II / K-3 III would exhaust heap and abort pgphoto
# mid-transfer. 256 MiB covers the largest practical capture with headroom. See
# docs/PENTAX-CAPTURE-BUDGET.md.
PENTAX_MAX_CAPTURE_SIZE="${PENTAX_MAX_CAPTURE_SIZE:-268435456}"
FIX_R5M2_TYPO="${FIX_R5M2_TYPO:-1}"
SELFTEST="${SELFTEST:-0}"
# Mode:
#   full     = full-libgphoto2 swap (DEFAULT, hardware-validated): replace the
#              WHOLE 2.5.34 stack (core + port + ptp2 + usb1) via the on-disk
#              trampoline loader, over the reliability-patched pgphoto base.
#   ptp2only = conservative legacy swap: keep pgphoto's compiled-in 2.5.27 core,
#              swap only the ptp2 camlib + usb1 iolib and apply the 14-byte patch.
MODE="${MODE:-full}"
case "$MODE" in full|ptp2only) : ;; *) echo "invalid MODE=$MODE (full|ptp2only)"; exit 1;; esac
# Also swap the usb1 port/iolib (USB transport) alongside the ptp2 camlib.
# 1 = swap usb1.so too (default); 0 = ptp2-only camlib swap (legacy).
SWAP_USB1="${SWAP_USB1:-1}"
# Full mode ALWAYS needs usb1 (the fresh 2.5.34 port dlopens usb1 from IOLIBS).
[ "$MODE" = "full" ] && SWAP_USB1=1
XT=arm-linux-gnueabi
W=/work
mkdir -p "$W"

# Known-good reference for the ONLY firmware this tool has been tested against.
TESTED_FWVER="4.0.0.32"
TESTED_APPFS_MD5="47f2ae680be3a5f5d69aa20e20a2397b"
TESTED_PGPHOTO_MD5="a0"  # informational only; verified structurally below

# ---------------------------------------------------------------------------
# 0. Validate input FwPkt
# ---------------------------------------------------------------------------
[ -f /in/firmwareInfo ] || die "/in/firmwareInfo not found — mount your stock FwPkt at /in"
[ -f /in/camera/appfs.ubifs ] || die "/in/camera/appfs.ubifs not found"
[ -f /in/camera/config ] || die "/in/camera/config not found"

STOCK_APPFS=/in/camera/appfs.ubifs
log "libgphoto2 target : $LIBGPHOTO2_VERSION"
log "Pentax capture cap: $PENTAX_MAX_CAPTURE_SIZE bytes  (override with PENTAX_MAX_CAPTURE_SIZE=…; issue #2)"
log "stock appfs.ubifs : $(stat -c %s "$STOCK_APPFS") bytes  md5=$(md5sum "$STOCK_APPFS"|cut -d' ' -f1)"

FWVER="unknown"
[ -f /in/FwVer ] && FWVER="$(cat /in/FwVer 2>/dev/null || true)"
if ! grep -q "$TESTED_FWVER" <<<"$FWVER"; then
    warn "This FwPkt reports FwVer='$FWVER'."
    warn "This tool has ONLY been tested against FwVer $TESTED_FWVER."
    warn "Continuing, but the patch-site checks below will ABORT on any mismatch."
fi

# ---------------------------------------------------------------------------
# 1. Faithful extraction of the stock appfs (preserves uid/gid/mode/symlinks)
# ---------------------------------------------------------------------------
log "extracting stock appfs (permission-preserving)…"
rm -rf "$W/app_ext"
ubireader_extract_files -k -o "$W/app_ext" "$STOCK_APPFS" >/dev/null 2>&1
APP="$(find "$W/app_ext" -maxdepth 3 -name ubifs -type d | head -1)"
[ -n "$APP" ] || die "extraction failed"
PG="$APP/bin/pgphoto"
[ -f "$PG" ] || die "pgphoto not found inside appfs (unexpected firmware layout)"

# Locate the stock camlib (its directory name encodes the stock libgphoto2 rev).
STOCK_PTP2="$(find "$APP/lib/libgphoto2" -name ptp2.so | head -1)"
[ -n "$STOCK_PTP2" ] || die "stock ptp2.so not found inside appfs"
CAMLIB_DIR="$(dirname "$STOCK_PTP2")"
log "camlib dir        : /app/lib/libgphoto2/$(basename "$CAMLIB_DIR")"

# Locate the stock usb1 iolib (port/USB transport). Unlike ptp2, pgphoto's port
# loader dlopen's this file at runtime (verified: gp_port_set_info →
# lt_dlopenext + lt_dlsym("gp_port_library_operations"), no static short-circuit),
# so replacing it actually takes effect. Its dir name encodes the port ABI rev.
STOCK_USB1=""
if [ "$SWAP_USB1" = "1" ]; then
  STOCK_USB1="$(find "$APP/lib/libgphoto2_port" -name usb1.so | head -1)"
  if [ -n "$STOCK_USB1" ]; then
    log "iolib dir         : /app/lib/libgphoto2_port/$(basename "$(dirname "$STOCK_USB1")")"
  else
    warn "usb1.so not found inside appfs — disabling usb1 swap (ptp2-only)"
    SWAP_USB1=0
  fi
fi

# ---------------------------------------------------------------------------
# 2. Analyse pgphoto: trampoline target + the three static-dispatch gates
# ---------------------------------------------------------------------------
python3 /opt/patcher/analyze_pgphoto.py "$PG" > "$W/pgphoto.plan" || die "pgphoto analysis failed"
cat "$W/pgphoto.plan"
TRAMP_ADDR="$(grep '^TRAMPOLINE_ADDR=' "$W/pgphoto.plan" | cut -d= -f2)"
GATES="$(grep '^GATE=' "$W/pgphoto.plan" | cut -d= -f2 | tr '\n' ' ')"
RESETUSB="$(grep '^RESETUSB_ADDR=' "$W/pgphoto.plan" | cut -d= -f2)"
LISTFILES="$(grep '^LISTFILES_BL=' "$W/pgphoto.plan" | cut -d= -f2 | tr '\n' ' ')"
[ -n "$TRAMP_ADDR" ] || die "could not locate gp_filesystem_set_info_dirty in pgphoto"
[ "$(wc -w <<<"$GATES")" = "3" ] || die "expected exactly 3 dispatch gates, found: $GATES — refusing to patch unknown firmware"
[ -n "$RESETUSB" ] || die "could not locate resetUsb in pgphoto — refusing to patch unknown firmware"
[ "$(wc -w <<<"$LISTFILES")" = "1" ] || die "expected exactly 1 ARG_LIST_FILES dispatch, found: $LISTFILES — refusing to patch"
log "trampoline target : $TRAMP_ADDR (pgphoto's own gp_filesystem_set_info_dirty)"
log "dispatch gates    : $GATES"
log "resetUsb          : $RESETUSB (USBDEVFS_RESET → return 0; stops cold re-enumeration storm)"
log "list-files gate   : $LISTFILES (skip full-card PTP scan at connect → ready in seconds)"

# ---------------------------------------------------------------------------
# 3. Stage the device's own link libraries (exact soname / ABI match)
# ---------------------------------------------------------------------------
DEV=/work/devlibs; rm -rf "$DEV"; mkdir -p "$DEV"
# libexif/libltdl: link targets for ptp2.  libusb-1.0: link target for usb1
# (device's OWN soname/ABI, so the rebuilt usb1.so binds the exact libusb the
# device ships).  Each staged with a plain `.so` symlink for -l<name>.
STAGE_LIBS="libexif.so.12 libltdl.so.7"
[ "$SWAP_USB1" = "1" ] && STAGE_LIBS="$STAGE_LIBS libusb-1.0.so.0"
for l in $STAGE_LIBS; do
  s="$(find "$APP/lib" -name "${l}*" ! -name '*.la' | sort | tail -1)"
  [ -n "$s" ] && { cp -a "$s" "$DEV/$l"; ln -sf "$l" "$DEV/${l%.so.*}.so"; }
done
if [ "$SWAP_USB1" = "1" ] && [ ! -f "$DEV/libusb-1.0.so.0" ]; then
  warn "device libusb-1.0.so.0 not found in appfs — disabling usb1 swap (ptp2-only)"
  SWAP_USB1=0
fi
cp -a "$(find "$APP/lib" -name 'libgphoto2.so.6*'      ! -name '*.la'|sort|tail -1)" "$DEV/dev_libgphoto2.so.6"
cp -a "$(find "$APP/lib" -name 'libgphoto2_port.so.12*' ! -name '*.la'|sort|tail -1)" "$DEV/dev_libgphoto2_port.so.12"

# ---------------------------------------------------------------------------
# 4. Cross-build the chosen libgphoto2 ptp2 driver
#    Reliability hardening baked in for the R5 Mark II (see docs/HOW-IT-WORKS.md):
#      * drop the EOS keep-device-on heartbeat (clobbers the viewfinder settle timer)
#      * drop the SetRemoteMode toggle 2.5.34 added to camera_exit (extra re-enum)
#    (COLD_START_TIMEOUT_MS is intentionally left at the stock 1.5s — a longer
#    timeout makes camera_init exceed polestar_app's ~5s watchdog and crash-loops.)
# ---------------------------------------------------------------------------
if [ "$MODE" = "ptp2only" ]; then
  # Legacy path: rebuilt ptp2 talks to pgphoto's compiled-in 2.5.27 core, so the
  # 2.5.34 EOS-init additions are dropped for Polaris reliability.
  export REMOVE_KEEP_DEVICE_ON=1
  export REMOVE_EXIT_REMOTEMODE=1
  /opt/patcher/build_ptp2.sh "$LIBGPHOTO2_VERSION" "$TRAMP_ADDR" "$FIX_R5M2_TYPO"
else
  # Full-stack path: build the whole 2.5.34 stack (core+port+ptp2+usb1). ptp2 runs
  # against the FRESH 2.5.34 core here, so the upstream EOS-init behaviour is kept
  # (the cold-start storm is handled by the pgphoto reliability base — resetUsb +
  # list-files — not by the driver). No trampoline shim (new core has the symbol).
  /opt/patcher/build_fullstack.sh "$LIBGPHOTO2_VERSION" "$TRAMP_ADDR" "$FIX_R5M2_TYPO"
fi
NEW_PTP2="$W/out/ptp2.so"
NEW_CORE="$W/out/libgphoto2.so.6"; NEW_PORT="$W/out/libgphoto2_port.so.12"
[ -f "$NEW_PTP2" ] || die "ptp2.so build failed"
if [ -e /libgphoto2-source-input ]; then
  # NOTE: under 'set -euo pipefail', a '$(strings ... | grep -Fc ...)' command
  # substitution aborts the whole script on the *first* missing marker
  # (grep exits 1, the substitution exits 1, set -e fires) before the
  # intended die() ever runs. The previous 'grep -Fqm1' form had the
  # mirror bug: grep exits on first match, strings keeps writing, gets
  # SIGPIPE (exit 141), pipefail propagates — also a false abort. Use
  # the pipeline *as the if condition itself*: 'grep -Fc' reads to EOF
  # (no SIGPIPE), its exit is the test, and an absence naturally falls
  # into the else-branch instead of tripping set -e. See
  # docs/pentax-patcher-gate-bug.md.
  if strings "$NEW_PTP2" | grep -Fc 'Pentax vendor mode enabled' >/dev/null; then
    log "local-source Pentax candidate marker: present"
  else
    die "local-source ptp2.so lacks the Pentax candidate marker"
  fi
  for model in 'Pentax:K-1 Mark II (PTP mode)' 'Pentax:K-3 Mark III (MTP mode)'; do
    if ! strings "$NEW_PTP2" | grep -F "$model" >/dev/null; then
      die "local-source ptp2.so lacks required target model: $model"
    fi
  done
  log "local-source target models: K-1 II and K-3 III present"
elif [ "$MODE" = "full" ]; then
  [ "${ALLOW_VANILLA_SOURCE:-0}" = "1" ] ||
    die "full mode lacks required libgphoto2 source input"
  warn "explicit vanilla-source build: Pentax fork markers and target models are absent by design"
fi

# ---------------------------------------------------------------------------
# 5. Verify the rebuilt driver resolves against the CORE IT WILL RUN AGAINST.
#    ptp2only: pgphoto's own compiled-in 2.5.27 core (device core + pgphoto).
#    full    : the FRESH 2.5.34 core/port this run built (which the on-disk loader
#              dlopens) -- so newer symbols like gp_filesystem_set_info_dirty
#              resolve there, NOT against the older device core.
# ---------------------------------------------------------------------------
log "verifying rebuilt ptp2.so…"
FLAGS="$($XT-readelf -h "$NEW_PTP2" | awk -F: '/Flags/{print $2}')"
grep -q 'soft-float' <<<"$FLAGS" || die "ABI mismatch: expected soft-float EABI, got:$FLAGS"
MAXGLIBC="$($XT-readelf --dyn-syms "$NEW_PTP2" | grep -oE 'GLIBC_[0-9.]+' | sort -V | tail -1)"
log "  ABI=$FLAGS  glibc_ceiling=$MAXGLIBC"
case "$MAXGLIBC" in GLIBC_2.4|GLIBC_2.5|GLIBC_2.6|GLIBC_2.7|GLIBC_2.8|GLIBC_2.9|GLIBC_2.1[0-9]|GLIBC_2.2[0-4]) : ;;
  *) die "glibc ceiling $MAXGLIBC exceeds device glibc 2.24 — driver would not load";; esac
# Build the symbol-provider set for the core the driver will bind against.
if [ "$MODE" = "full" ]; then
  [ -f "$NEW_CORE" ] && [ -f "$NEW_PORT" ] || die "full mode: core/port not built"
  $XT-nm -D --defined-only "$NEW_CORE" | awk '{print $3}'  >"$W/prov.txt"
  $XT-nm -D --defined-only "$NEW_PORT" | awk '{print $3}' >>"$W/prov.txt"
  PROV_DESC="the freshly-built $LIBGPHOTO2_VERSION core/port"
else
  $XT-nm -D --defined-only "$DEV/dev_libgphoto2.so.6"       | awk '{print $3}'  >"$W/prov.txt"
  $XT-nm -D --defined-only "$DEV/dev_libgphoto2_port.so.12" | awk '{print $3}' >>"$W/prov.txt"
  PROV_DESC="the device's stock 2.5.27 core"
fi
$XT-nm -D --defined-only "$PG"                             | awk '{print $3}' >>"$W/prov.txt"
sort -u "$W/prov.txt" -o "$W/prov.txt"
$XT-nm -D --undefined-only "$NEW_PTP2" | awk '{print $2}' | grep -E '^(gp_|gpi_)' | sort -u >"$W/need.txt"
MISSING="$(comm -23 "$W/need.txt" "$W/prov.txt" || true)"
[ -z "$MISSING" ] || die "rebuilt driver needs core symbols missing from the target core:\n$MISSING"
log "  all core symbols resolve against $PROV_DESC ✓"

# ---------------------------------------------------------------------------
# 5b. Verify the rebuilt usb1 iolib (fail-safe, same rigour as ptp2).
#     Aborts on ANY mismatch so a bad usb1.so can never reach the firmware.
# ---------------------------------------------------------------------------
NEW_USB1="$W/out/usb1.so"
if [ "$SWAP_USB1" = "1" ]; then
  [ -f "$NEW_USB1" ] || die "usb1 swap requested but usb1.so was not built (libusb detection failed) — aborting"
  log "verifying rebuilt usb1.so…"
  UFLAGS="$($XT-readelf -h "$NEW_USB1" | awk -F: '/Flags/{print $2}')"
  grep -q 'soft-float' <<<"$UFLAGS" || die "usb1 ABI mismatch: expected soft-float EABI, got:$UFLAGS"
  UMAXGLIBC="$($XT-readelf --dyn-syms "$NEW_USB1" | grep -oE 'GLIBC_[0-9.]+' | sort -V | tail -1)"
  log "  ABI=$UFLAGS  glibc_ceiling=$UMAXGLIBC"
  case "$UMAXGLIBC" in GLIBC_2.4|GLIBC_2.5|GLIBC_2.6|GLIBC_2.7|GLIBC_2.8|GLIBC_2.9|GLIBC_2.1[0-9]|GLIBC_2.2[0-4]) : ;;
    *) die "usb1 glibc ceiling $UMAXGLIBC exceeds device glibc 2.24 — iolib would not load";; esac
  # it must export the three iolib entry points the port loader lt_dlsym's.
  for e in gp_port_library_type gp_port_library_list gp_port_library_operations; do
    $XT-nm -D --defined-only "$NEW_USB1" | awk '{print $3}' | grep -qx "$e" \
      || die "rebuilt usb1.so is missing iolib entry point '$e' — aborting"
  done
  # DT_NEEDED ⊆ the STOCK usb1.so's NEEDED: never introduce a shared library the
  # stock iolib did not already depend on (and the device therefore provably has).
  $XT-readelf -d "$STOCK_USB1" | awk -F'[][]' '/\(NEEDED\)/{print $2}' | sort -u >"$W/usb1_stock_needed.txt"
  $XT-readelf -d "$NEW_USB1"   | awk -F'[][]' '/\(NEEDED\)/{print $2}' | sort -u >"$W/usb1_new_needed.txt"
  EXTRA="$(comm -23 "$W/usb1_new_needed.txt" "$W/usb1_stock_needed.txt" || true)"
  [ -z "$EXTRA" ] || die "rebuilt usb1.so pulls in libs the stock usb1.so did not:\n$EXTRA"
  log "  DT_NEEDED ⊆ stock usb1.so ($(tr '\n' ' ' <"$W/usb1_new_needed.txt")) ✓"
  # every gp_/gpi_ (core/port) symbol it imports must be provided by the device
  # port core; every libusb_* import must be provided by the device's libusb.
  $XT-nm -D --undefined-only "$NEW_USB1" | awk '{print $2}' | grep -E '^(gp_|gpi_)' | sort -u >"$W/usb1_need.txt"
  MISSING_U="$(comm -23 "$W/usb1_need.txt" "$W/prov.txt" || true)"
  [ -z "$MISSING_U" ] || die "rebuilt usb1.so needs core/port symbols the device lacks:\n$MISSING_U"
  $XT-nm -D --undefined-only "$NEW_USB1" | awk '{print $2}' | grep -iE '^libusb_' | sort -u >"$W/usb1_needusb.txt"
  $XT-nm -D --defined-only "$DEV/libusb-1.0.so.0" | awk '{print $3}' | sort -u >"$W/usb1_provusb.txt"
  MISSING_LU="$(comm -23 "$W/usb1_needusb.txt" "$W/usb1_provusb.txt" || true)"
  [ -z "$MISSING_LU" ] || die "rebuilt usb1.so needs libusb symbols the device's libusb-1.0 lacks:\n$MISSING_LU"
  log "  all core/port + libusb symbols resolve on-device ✓ ($(wc -l <"$W/usb1_needusb.txt"|tr -d ' ') libusb imports)"
fi

# ---------------------------------------------------------------------------
# 5c. FULL mode: verify the freshly-built core + port (fail-safe, same rigour).
# ---------------------------------------------------------------------------
NEW_CORE="$W/out/libgphoto2.so.6"; NEW_PORT="$W/out/libgphoto2_port.so.12"
if [ "$MODE" = "full" ]; then
  [ -f "$NEW_CORE" ] || die "full mode: libgphoto2.so.6 was not built"
  [ -f "$NEW_PORT" ] || die "full mode: libgphoto2_port.so.12 was not built"
  log "verifying rebuilt core + port…"
  for L in "$NEW_CORE" "$NEW_PORT"; do
    CFLAGS_="$($XT-readelf -h "$L" | awk -F: '/Flags/{print $2}')"
    grep -q 'soft-float' <<<"$CFLAGS_" || die "core/port ABI mismatch (not soft-float): $L$CFLAGS_"
    CMAX="$($XT-readelf --dyn-syms "$L" | grep -oE 'GLIBC_[0-9.]+' | sort -V | tail -1)"
    case "$CMAX" in GLIBC_2.4|GLIBC_2.5|GLIBC_2.6|GLIBC_2.7|GLIBC_2.8|GLIBC_2.9|GLIBC_2.1[0-9]|GLIBC_2.2[0-4]) : ;;
      *) die "$L glibc ceiling $CMAX exceeds device glibc 2.24";; esac
  done
  # Every one of the 64 boundary symbols the loader dlsym's must be exported by the
  # new core or port, else the loader would leave that slot at the abort stub.
  $XT-nm -D --defined-only "$NEW_CORE" | awk '{print $3}'  >"$W/newexp.txt"
  $XT-nm -D --defined-only "$NEW_PORT" | awk '{print $3}' >>"$W/newexp.txt"
  sort -u "$W/newexp.txt" -o "$W/newexp.txt"
  MISSING_B="$(comm -23 <(python3 -c "import sys;sys.path.insert(0,'/opt/patcher');import stage2_patch as s;print('\n'.join(sorted(s.BOUNDARY)))") "$W/newexp.txt" || true)"
  [ -z "$MISSING_B" ] || die "new core/port do not export boundary symbols:\n$MISSING_B"
  log "  core/port soft-float, glibc≤2.24, all 64 boundary symbols exported ✓"
fi

if [ "$SELFTEST" = "1" ] && command -v qemu-arm-static >/dev/null 2>&1; then
  if [ "$MODE" = "ptp2only" ]; then
    if [ -e /libgphoto2-source-input ]; then
      /opt/patcher/selftest.sh "$APP" "$NEW_PTP2" "$DEV" ||
        die "candidate-source qemu selftest failed"
    else
      /opt/patcher/selftest.sh "$APP" "$NEW_PTP2" "$DEV" ||
        warn "selftest reported an issue (non-fatal)"
    fi
  else
    warn "selftest skipped in full mode (it emulates ptp2 against the device's 2.5.27"
    warn "core; full mode runs ptp2 against the fresh $LIBGPHOTO2_VERSION core it just built)."
  fi
fi

P_UID="$(stat -c %u "$PG")"; P_GID="$(stat -c %g "$PG")"; P_MODE="$(stat -c %a "$PG")"
if [ "$MODE" = "ptp2only" ]; then
  # -------------------------------------------------------------------------
  # 6 (ptp2only). Patch pgphoto (14 bytes) and swap ptp2/usb1 in place.
  # -------------------------------------------------------------------------
  log "patching pgphoto (3 gates + resetUsb return-0 + list-files skip)…"
  python3 /opt/patcher/analyze_pgphoto.py "$PG" --apply "$W/pgphoto.patched" >/dev/null
  DIFFB="$( { cmp -l "$PG" "$W/pgphoto.patched" || true; } | wc -l | tr -d ' ')"
  # 14 = 3 (gates) + 7 (resetUsb: mov r0,#0 + bx lr) + 4 (list-files bl → nop)
  [ "$DIFFB" = "14" ] || die "pgphoto patch changed $DIFFB bytes (expected 14) — aborting"
  log "  pgphoto patched: 14 bytes (gates + resetUsb + list-files skip) ✓"

  O_UID="$(stat -c %u "$STOCK_PTP2")"; O_GID="$(stat -c %g "$STOCK_PTP2")"; O_MODE="$(stat -c %a "$STOCK_PTP2")"
  install -m "$O_MODE" -o "$O_UID" -g "$O_GID" "$NEW_PTP2"           "$STOCK_PTP2"
  install -m "$P_MODE" -o "$P_UID" -g "$P_GID" "$W/pgphoto.patched" "$PG"
  if [ "$SWAP_USB1" = "1" ]; then
    U_UID="$(stat -c %u "$STOCK_USB1")"; U_GID="$(stat -c %g "$STOCK_USB1")"; U_MODE="$(stat -c %a "$STOCK_USB1")"
    install -m "$U_MODE" -o "$U_UID" -g "$U_GID" "$NEW_USB1"         "$STOCK_USB1"
    log "swapped usb1 iolib: /app/lib/libgphoto2_port/$(basename "$(dirname "$STOCK_USB1")")/usb1.so"
  fi
else
  # -------------------------------------------------------------------------
  # 6 (full). Full-libgphoto2 on-disk trampoline swap (DEFAULT).
  #   a) reliability-patched base (the same 14-byte patch, symbol-discovered)
  #   b) on-disk trampoline the 64 boundary entries over that base
  #   c) compile the generic loader against the generated slot table
  #   d) assemble /app/lib/stage2 + install the self-driving wrapper as
  #      /app/bin/pgphoto  (the hardware-validated wrapper form)
  # -------------------------------------------------------------------------
  log "full-libgphoto2: building reliability-patched base…"
  python3 /opt/patcher/analyze_pgphoto.py "$PG" --apply "$W/pgphoto.base" >/dev/null
  DIFFB="$( { cmp -l "$PG" "$W/pgphoto.base" || true; } | wc -l | tr -d ' ')"
  [ "$DIFFB" = "14" ] || die "reliability base changed $DIFFB bytes (expected 14) — aborting"
  log "  base: 14-byte reliability patch (resetUsb + list-files + 3 gates) md5=$(md5sum "$W/pgphoto.base"|cut -d' ' -f1)"

  log "full-libgphoto2: on-disk trampolining 64 boundary entries…"
  rm -rf "$W/s2"; mkdir -p "$W/s2"
  python3 /opt/patcher/stage2_patch.py \
    --pgphoto "$W/pgphoto.base" --core "$NEW_CORE" --port "$NEW_PORT" \
    --nm "$XT-nm" --readelf "$XT-readelf" \
    --reliability-base "$PG" \
    --outdir "$W/s2" --out "$W/s2/pgphoto.stage2ondisk" \
    || die "stage2_patch.py failed (blocker / collision / unresolved boundary symbol)"
  log "  trampolined: md5=$(md5sum "$W/s2/pgphoto.stage2ondisk"|cut -d' ' -f1) (size $(stat -c %s "$W/s2/pgphoto.stage2ondisk") == stock $(stat -c %s "$PG"))"
  [ "$(stat -c %s "$W/s2/pgphoto.stage2ondisk")" = "$(stat -c %s "$PG")" ] \
    || die "trampolined binary changed size — must be byte-count-identical to stock"

  log "full-libgphoto2: compiling loader (libpolaris_stage2.so)…"
  # Compile from a source NAMED stage2_ondisk_loader.c so the .symtab STT_FILE
  # symbol matches the hardware-validated loader byte-for-byte.
  cp /opt/patcher/stage2_loader.c "$W/s2/stage2_ondisk_loader.c"
  cp /opt/patcher/stage2_policy.h /opt/patcher/stage2_policy.c "$W/s2/"
  ( cd "$W/s2" && $XT-gcc -shared -fPIC -O2 -std=gnu11 -mfloat-abi=soft -Wall -Wextra \
      -Wl,-soname,libpolaris_stage2.so -I. stage2_ondisk_loader.c stage2_policy.c \
      -o libpolaris_stage2.so -ldl ) || die "loader compile failed"
  LFLAGS="$($XT-readelf -h "$W/s2/libpolaris_stage2.so" | awk -F: '/Flags/{print $2}')"
  grep -q 'soft-float' <<<"$LFLAGS" || die "loader ABI mismatch (not soft-float):$LFLAGS"
  # Issue #27: fail-closed provenance check. The loader now links stage2_policy.c
  # (R5-II compatibility-shim gate, commit ccde305), so it is NOT the upstream
  # hardware-validated loader (md5 74f681de…). If a build ever reproduces that
  # old md5, or lacks the R5-gate marker string, our policy code is silently
  # missing from the shipped binary — abort instead of shipping it.
  LOADER_MD5="$(md5sum "$W/s2/libpolaris_stage2.so"|cut -d' ' -f1)"
  if [ "$LOADER_MD5" = "74f681de5a43e068df36ae61001a4e79" ]; then
    die "loader md5 matches the PRE-R5-GATE upstream loader (74f681de) — stage2_policy.c is not in this build (issue #27)"
  fi
  # Do not use grep -q here: with pipefail, an early successful grep exit can
  # SIGPIPE strings(1), turning a present marker into a failed pipeline.
  if ! strings "$W/s2/libpolaris_stage2.so" | grep 'stage2_model_uses_r5_shims' >/dev/null; then
    die "loader lacks the R5-II gate marker (stage2_model_uses_r5_shims) — stage2_policy.c missing from build (issue #27)"
  fi
  log "  loader: md5=$LOADER_MD5 ABI=$LFLAGS (R5-II gate present, issue #27)"

  # d) assemble /app/lib/stage2 and install the wrapper as /app/bin/pgphoto.
  STAGE2="$APP/lib/stage2"
  rm -rf "$STAGE2"
  install -d -m "$P_MODE" -o "$P_UID" -g "$P_GID" \
    "$STAGE2" "$STAGE2/libgphoto2/$LIBGPHOTO2_VERSION" "$STAGE2/libgphoto2_port/$LIBGPHOTO2_PORT_VERSION"
  install -m 755 -o "$P_UID" -g "$P_GID" "$W/s2/libpolaris_stage2.so"  "$STAGE2/libpolaris_stage2.so"
  install -m 755 -o "$P_UID" -g "$P_GID" "$W/s2/pgphoto.stage2ondisk"  "$STAGE2/pgphoto.stage2ondisk"
  install -m 755 -o "$P_UID" -g "$P_GID" "$NEW_CORE"                   "$STAGE2/libgphoto2.so.6"
  install -m 755 -o "$P_UID" -g "$P_GID" "$NEW_PORT"                   "$STAGE2/libgphoto2_port.so.12"
  install -m 755 -o "$P_UID" -g "$P_GID" "$NEW_PTP2"                   "$STAGE2/libgphoto2/$LIBGPHOTO2_VERSION/ptp2.so"
  install -m 755 -o "$P_UID" -g "$P_GID" "$NEW_USB1"                   "$STAGE2/libgphoto2_port/$LIBGPHOTO2_PORT_VERSION/usb1.so"
  # Generate the wrapper from its template (CAMLIBS_VERSION/IOLIBS_VERSION +
  # PENTAX_MAX_CAPTURE_SIZE) so it matches the staged dir layout above. Issue #1:
  # previously this was a checked-in file that hard-coded "2.5.34" / "0.12.2",
  # silently producing a mismatch (and a 14-byte-patch-only noop) for any
  # non-default --libgphoto2. Issue #2: the Pentax capture budget placeholder
  # lets us override libgphoto2's 2 GiB default which is unsafe on Polaris RAM.
  sed -e "s|@CAMLIBS_VERSION@|$LIBGPHOTO2_VERSION|g" \
      -e "s|@IOLIBS_VERSION@|$LIBGPHOTO2_PORT_VERSION|g" \
      -e "s|@PENTAX_MAX_CAPTURE_SIZE@|$PENTAX_MAX_CAPTURE_SIZE|g" \
      /opt/patcher/ondisk/pgphoto.wrapper.in > "$W/pgphoto.wrapper"
  chmod 755 "$W/pgphoto.wrapper"
  install -m "$P_MODE" -o "$P_UID" -g "$P_GID" "$W/pgphoto.wrapper" "$PG"
  log "  assembled /app/lib/stage2 (loader + core + port + ptp2 + usb1 + trampolined binary)"
  log "  installed self-driving wrapper -> /app/bin/pgphoto (execs /app/lib/stage2/pgphoto.stage2ondisk)"

  # Replace the stock /app/restart_gphoto with our single-owner restart helper
  # (issue #33: the stock script's 'pkill /app/bin/pgphoto' matches nothing once
  # the wrapper execs pgphoto.stage2ondisk, so the old instance survives, keeps
  # port 8080, and every replacement dies on bind -> crash loop, issue #34).
  # The helper: PID-file ownership + /proc/$pid/cmdline verification, TERM then
  # bounded wait for process exit AND 8080 unbind, KILL fallback, restart-in-
  # progress lock so the polestar watchdog (checkGphotoTask) can't race it.
  RST="$APP/restart_gphoto"
  if [ -e "$RST" ]; then
    R_UID="$(stat -c %u "$RST")"; R_GID="$(stat -c %g "$RST")"; R_MODE="$(stat -c %a "$RST")"
  else
    R_UID="$P_UID"; R_GID="$P_GID"; R_MODE=755
  fi
  install -m "$R_MODE" -o "$R_UID" -g "$R_GID" /opt/patcher/ondisk/restart_gphoto.sh "$RST"
  log "  installed single-owner restart helper -> /app/restart_gphoto (issue #33/#34)"

  # ALSO place the fresh ptp2/usb1 at the STOCK camlib/iolib paths. This is the
  # path the swapped 2.5.34 core actually dlopens its camlib from at runtime
  # (device-confirmed: NOT the CAMLIBS the wrapper exports — the core resolves
  # camlibs from its stock on-disk layout /app/lib/libgphoto2/<rev>/ptp2.so, and
  # the port loader dlopens usb1 from /app/lib/libgphoto2_port/<rev>/usb1.so).
  # Without this the core would load the STALE stock 2.5.27 ptp2 and the Canon
  # driver would not bind. Stock perms/uid/gid preserved (stock camlib is 0750).
  O_UID="$(stat -c %u "$STOCK_PTP2")"; O_GID="$(stat -c %g "$STOCK_PTP2")"; O_MODE="$(stat -c %a "$STOCK_PTP2")"
  install -m "$O_MODE" -o "$O_UID" -g "$O_GID" "$NEW_PTP2" "$STOCK_PTP2"
  log "  placed fresh ptp2 at stock camlib path: /app/lib/libgphoto2/$(basename "$CAMLIB_DIR")/ptp2.so"
  if [ "$SWAP_USB1" = "1" ]; then
    U_UID="$(stat -c %u "$STOCK_USB1")"; U_GID="$(stat -c %g "$STOCK_USB1")"; U_MODE="$(stat -c %a "$STOCK_USB1")"
    install -m "$U_MODE" -o "$U_UID" -g "$U_GID" "$NEW_USB1" "$STOCK_USB1"
    log "  placed fresh usb1 at stock iolib path: /app/lib/libgphoto2_port/$(basename "$(dirname "$STOCK_USB1")")/usb1.so"
  fi

  # Replace the stock core AND port with the freshly-built matched pair.  The
  # runtime has two libgphoto2 paths:
  # a. Trampolined /app/lib/stage2/libgphoto2.so.6 — loaded by pgphoto.stage2ondisk via absolute path. Working.
  # b. Stock /app/lib/libgphoto2.so.6 2.5.27 — loaded by a child process via relative path lookup.
  #    This path fails with 'No iolibs found in '../lib/libgphoto2_port/0.12.0''.
  # Replacing only the stock core left /app/bin/gphoto2 loading that new core
  # beside the old 2.5.27 port library, which fails on the versioned
  # gp_port_init_localedir symbol (issue #51).  Both active paths must therefore
  # carry the same core/port pair.
  STOCK_CORE="$APP/lib/libgphoto2.so.6"
  STOCK_PORT="$APP/lib/libgphoto2_port.so.12"
  if [ -f "$STOCK_CORE" ]; then
    S_UID="$(stat -c %u "$STOCK_CORE")"; S_GID="$(stat -c %g "$STOCK_CORE")"; S_MODE="$(stat -c %a "$STOCK_CORE")"
    install -m "$S_MODE" -o "$S_UID" -g "$S_GID" "$NEW_CORE" "$STOCK_CORE"
    log "  replaced stock libgphoto2.so.6 with fresh 2.5.34 core at /app/lib/libgphoto2.so.6"
  fi
  if [ -f "$STOCK_PORT" ]; then
    S_UID="$(stat -c %u "$STOCK_PORT")"; S_GID="$(stat -c %g "$STOCK_PORT")"; S_MODE="$(stat -c %a "$STOCK_PORT")"
    install -m "$S_MODE" -o "$S_UID" -g "$S_GID" "$NEW_PORT" "$STOCK_PORT"
    log "  replaced stock libgphoto2_port.so.12 with fresh matched port at /app/lib/libgphoto2_port.so.12"
  fi
fi

# Preserve source identity inside the flashable image, not only in the build
# output beside FwPkt.zip. This lets a running device prove which exact clean
# libgphoto2 checkout produced its embedded stack (issue #1/#13).
[ -f "$W/out/source-provenance.env" ] || die "source provenance was not generated"
install -m 644 -o 0 -g 0 "$W/out/source-provenance.env" \
  "$APP/openpolaris-libgphoto2-provenance.txt"
log "embedded libgphoto2 provenance -> /app/openpolaris-libgphoto2-provenance.txt"

# ---------------------------------------------------------------------------
# 7. OPTIONAL (SSH_PUBKEY, issue #31): authorise a public key for root SSH
#    debugging. Ported from upstream blaineam/benro-polaris-firmware-patcher
#    commit 004c057 ("Add optional --ssh-key debug access").
#
#    The stock firmware ALREADY runs OpenSSH — /etc/init.d/rcS ends with
#    `/usr/local/bin/sshd`, and its sshd_config has `PermitRootLogin yes` +
#    `AuthorizedKeysFile .ssh/authorized_keys`. The only thing missing is a key
#    in /root/.ssh (rootfs), which this tool never touches.
#
#    So instead of modifying anything, we ADD the optional boot hook the stock
#    /app/bootapp already calls if present:
#        if [ -f "/app/network_telnetd.sh" ];then cd /app; ./network_telnetd.sh; fi
#    The hook appends the key to /root/.ssh/authorized_keys at boot. One new
#    appfs file; every existing file stays exactly as the mode above left it.
#    Fail-closed: if bootapp doesn't call a hook we can safely claim, we abort
#    rather than edit bootapp itself.
#
#    Decision (2026-09-06, issue #31): opt-in and OFF by default — the Polaris
#    is its own AP and the stock root password is blank, so SSH exposure is
#    unchanged unless this flag is passed. The hook is additive: it never
#    removes the password path, so it cannot lock us out.
# ---------------------------------------------------------------------------
SSH_HOOK=""
if [ -n "${SSH_PUBKEY:-}" ]; then
  log "ssh debug: authorising public key(s) for root@polaris…"
  BOOTAPP="$APP/bootapp"
  [ -f "$BOOTAPP" ] || die "SSH_PUBKEY set but /app/bootapp is missing from this appfs — refusing to guess a boot hook"
  for cand in network_telnetd.sh start_agent.sh; do
    grep -q "$cand" "$BOOTAPP" || continue          # bootapp must actually call it
    if [ -e "$APP/$cand" ]; then
      warn "  /app/$cand already exists in this firmware — leaving it alone, trying the next hook"
      continue
    fi
    SSH_HOOK="$cand"; break
  done
  [ -n "$SSH_HOOK" ] || die "SSH_PUBKEY: no free boot hook that /app/bootapp calls (looked for network_telnetd.sh, start_agent.sh) — refusing to modify bootapp"

  printf '%s\n' "$SSH_PUBKEY" > "$W/ssh_keys.txt"
  python3 /opt/patcher/gen_ssh_hook.py \
      --keys "$W/ssh_keys.txt" --hook-name "$SSH_HOOK" --out "$W/ssh_hook.sh" \
      || die "SSH_PUBKEY: invalid public key material (see the error above)"

  # sshd lives in the rootfs, which this tool ships byte-identical. Warn (don't
  # abort) if it isn't there — the hook is harmless either way.
  grep -aq 'sshd' /in/camera/rootfs.ubifs 2>/dev/null \
    || warn "  no 'sshd' found in this rootfs.ubifs — the key will be installed but nothing may serve SSH"

  # same owner/mode as bootapp itself (which provably has +x — S10mpp runs it)
  B_UID="$(stat -c %u "$BOOTAPP")"; B_GID="$(stat -c %g "$BOOTAPP")"; B_MODE="$(stat -c %a "$BOOTAPP")"
  install -m "$B_MODE" -o "$B_UID" -g "$B_GID" "$W/ssh_hook.sh" "$APP/$SSH_HOOK"
  log "  added /app/$SSH_HOOK (boot hook, $B_MODE $B_UID:$B_GID — same as bootapp) — appends to /root/.ssh/authorized_keys at boot"
  log "  after flashing: ssh -i <your private key> root@<polaris ip>"
fi

# ---------------------------------------------------------------------------
# 8. Repack appfs (geometry read from the stock image) + regenerate firmwareInfo
# ---------------------------------------------------------------------------
/opt/patcher/repack_appfs.sh "$STOCK_APPFS" "$APP" "$W/out/appfs.ubifs"

log "assembling custom FwPkt in /out…"
rm -rf /out/FwPkt; mkdir -p /out/FwPkt/camera /out/FwPkt/gimbal
cp -p /in/camera/config /in/camera/uImage /in/camera/rootfs.ubifs /out/FwPkt/camera/
# Do NOT swallow gimbal copy errors. Issue #21: a silent gimbal drop produced a
# 8-entry zip that the gimbal silently rejected (no NAND write, no warning).
# Fail loudly so a missing/empty /in/gimbal/*.bin is visible at build time.
#
# Use a shell array, not `ls | wc -l`: under `set -euo pipefail`, a non-matching
# glob makes `ls` exit 2 *inside* the command substitution and abort the script
# with a confusing "No such file" instead of the intended die() diagnostic.
shopt -s nullglob
gimbal_bins=( /in/gimbal/*.bin )
shopt -u nullglob
if [ "${#gimbal_bins[@]}" -eq 0 ]; then
  die "no /in/gimbal/*.bin found — refusing to ship a gimbal-less FwPkt (issue #21)"
fi
cp -p "${gimbal_bins[@]}" /out/FwPkt/gimbal/
cp "$W/out/appfs.ubifs" /out/FwPkt/camera/appfs.ubifs
python3 /opt/patcher/gen_firmwareinfo.py /in/firmwareInfo /out/FwPkt > /out/FwPkt/firmwareInfo

# Fail-closed firmwareInfo gate (re-MD5 + re-size every component against
# the just-built /out/FwPkt). Catches the "stale firmwareInfo" failure mode
# described in docs/silent-fwpkt-reject-postmortem.md.
if ! python3 /opt/patcher/verify_firmwareinfo.py /in/firmwareInfo /out/FwPkt; then
  die "firmwareInfo does not match the produced FwPkt -- the Polaris would silently reject this update. Refusing to zip."
fi
log "verified firmwareInfo against produced FwPkt (on-board check will pass)"

# Post-repack content assertion: re-extract the finished appfs and verify that
# bin/pgphoto exists, is executable/non-empty, contains the expected wrapper
# markers, and that lib/stage2/pgphoto.stage2ondisk plus the core/port/camlib/iolib set exist.
# This directly covers the #39 regression boundary (empty /app/bin/ after flash).
log "verifying finished appfs.ubifs contains required runtime files..."
UBIFS_EXTRACT_DIR="$W/appfs_verify"
rm -rf "$UBIFS_EXTRACT_DIR"
mkdir -p "$UBIFS_EXTRACT_DIR"
ubireader_extract_files -k -o "$UBIFS_EXTRACT_DIR" "$W/out/appfs.ubifs" >/dev/null 2>&1
APP_VERIFY="$(find "$UBIFS_EXTRACT_DIR" -maxdepth 3 -name ubifs -type d | head -1)"
[ -n "$APP_VERIFY" ] || die "appfs re-extraction failed"

# Verify bin/pgphoto exists and is executable (extracted paths don't have /app/ prefix)
PG_WRAPPER="$APP_VERIFY/bin/pgphoto"
if [ ! -f "$PG_WRAPPER" ]; then
  die "post-repack assertion failed: bin/pgphoto missing from appfs.ubifs"
fi
if [ ! -x "$PG_WRAPPER" ]; then
  die "post-repack assertion failed: bin/pgphoto is not executable"
fi
# Verify wrapper contains expected markers
if ! grep -q 'pgphoto.stage2ondisk' "$PG_WRAPPER"; then
  die "post-repack assertion failed: bin/pgphoto does not contain expected wrapper markers"
fi
log "  verified bin/pgphoto exists, is executable, and contains wrapper markers"

# Verify Stage-2 runtime files exist in the appfs (extracted paths don't have /app/ prefix)
STAGE2_BIN="$APP_VERIFY/lib/stage2/pgphoto.stage2ondisk"
if [ ! -f "$STAGE2_BIN" ]; then
  die "post-repack assertion failed: lib/stage2/pgphoto.stage2ondisk missing from appfs.ubifs"
fi
STAGE2_LOADER="$APP_VERIFY/lib/stage2/libpolaris_stage2.so"
if [ ! -f "$STAGE2_LOADER" ]; then
  die "post-repack assertion failed: lib/stage2/libpolaris_stage2.so missing from appfs.ubifs"
fi
CORE_LIB="$APP_VERIFY/lib/stage2/libgphoto2.so.6"
if [ ! -f "$CORE_LIB" ]; then
  die "post-repack assertion failed: lib/stage2/libgphoto2.so.6 missing from appfs.ubifs"
fi
PORT_LIB="$APP_VERIFY/lib/stage2/libgphoto2_port.so.12"
if [ ! -f "$PORT_LIB" ]; then
  die "post-repack assertion failed: lib/stage2/libgphoto2_port.so.12 missing from appfs.ubifs"
fi
log "  verified Stage-2 runtime files (lib/stage2/pgphoto.stage2ondisk, lib/stage2/libpolaris_stage2.so, lib/stage2/libgphoto2.so.6, lib/stage2/libgphoto2_port.so.12) exist in appfs.ubifs"

# Build the ZIP at a *temp* path so the validator can fail-closed on the
# *exact* archive we'd ship, and we only atomically rename to the public
# output path on PASS. Issue #21 follow-up: a prior write-then-validate
# sequence left a bad zip at /out/FwPkt.zip on FAIL, contradicting the
# "fail-closed" claim. See container/test_patch_fail_closed.sh.
#
# Note: shutil.make_archive's base name is the FIRST arg and it appends
# ".zip" — so the fallback must build the zip explicitly via zipfile to
# write to a *literal* ".tmp" path. Without this, make_archive would
# write directly to /out/FwPkt.zip and defeat the fail-closed guarantee.
rm -f /out/FwPkt.zip /out/FwPkt.zip.tmp
( cd /out && (
  if command -v zip >/dev/null 2>&1; then
    zip -rqX FwPkt.zip.tmp FwPkt
  else
    python3 -c 'import os,zipfile
zf=zipfile.ZipFile("FwPkt.zip.tmp","w",zipfile.ZIP_DEFLATED)
for root,dirs,files in os.walk("FwPkt"):
  # Explicit directory entries - the on-board polestar_app expects
  # them (matches the layout of the stock Benro-shipped FwPkt.zip).
  rel=os.path.relpath(root,".")
  if rel != ".":
    zi=zipfile.ZipInfo(rel+"/")
    zi.external_attr=(0o755 << 16)
    zf.writestr(zi,"")
  for fn in files:
    p=os.path.join(root,fn); zf.write(p,p)
zf.close()'
  fi
) && mv FwPkt.zip.tmp FwPkt.zip )

# ---------------------------------------------------------------------------
# 8a. Final structural verification of the finished ZIP.
#     The on-board polestar_app silently reboots on any mismatch in zip
#     layout, missing required files, duplicate members, or stock-component
#     drift. Catches everything the firmwareInfo check above can't, e.g.
#     wrong top-level folder name, gimbal files dropped on assembly,
#     accidental copy of a different stock camera binary. Issue #21.
#     Validates the *exact* archive at /out/FwPkt.zip (written by the
#     temp+rename step above). On FAIL, the temp+rename pattern means
#     no publishable /out/FwPkt.zip exists — the only copy is the .tmp
#     which we explicitly remove before die().
# ---------------------------------------------------------------------------
log "verifying finished FwPkt package layout…"
if ! python3 /opt/patcher/validate_fw_package.py /out/FwPkt.zip; then
  rm -f /out/FwPkt.zip /out/FwPkt.zip.tmp
  die "finished-package structural validator FAILED -- refuse to ship. The on-board updater would silently reject this FwPkt."
fi
log "verified FwPkt.zip structure (on-board check will pass)"

# ---------------------------------------------------------------------------
# 8b. FULL mode: emit the reversible on-device bundle.
#     The bundle lets people TEST before flashing (install_stage2.sh /
#     restore_stock.sh, LD_PRELOAD-reversible).
# ---------------------------------------------------------------------------
if [ "$MODE" = "full" ]; then
  BUN=/out/stage2-ondisk
  rm -rf "$BUN"; mkdir -p "$BUN/ondisk" "$BUN/libgphoto2/$LIBGPHOTO2_VERSION" "$BUN/libgphoto2_port/$LIBGPHOTO2_PORT_VERSION"
  cp "$W/s2/libpolaris_stage2.so"  "$BUN/ondisk/"
  cp "$W/s2/pgphoto.stage2ondisk"  "$BUN/ondisk/"
  cp "$W/pgphoto.wrapper" "$BUN/ondisk/"   # generated from .in (see above)
  cp /opt/patcher/ondisk/install_stage2.sh "$BUN/ondisk/"
  cp /opt/patcher/ondisk/restore_stock.sh  "$BUN/ondisk/"
  cp /opt/patcher/ondisk/restart_gphoto.sh "$BUN/ondisk/"
  cp "$NEW_CORE" "$BUN/libgphoto2.so.6"
  cp "$NEW_PORT" "$BUN/libgphoto2_port.so.12"
  cp "$NEW_PTP2" "$BUN/libgphoto2/$LIBGPHOTO2_VERSION/ptp2.so"
  cp "$NEW_USB1" "$BUN/libgphoto2_port/$LIBGPHOTO2_PORT_VERSION/usb1.so"
  chmod +x "$BUN/ondisk/"*.sh "$BUN/ondisk/pgphoto.wrapper" 2>/dev/null || true

  log "  wrote reversible on-device bundle -> /out/stage2-ondisk (install_stage2.sh / restore_stock.sh)"
fi

# Every mode distributes a rebuilt LGPL camlib, and full mode distributes the
# core and port libraries too. Ship the exact post-patch corresponding source;
# an upstream URL alone is insufficient when this build changed the source or
# consumed a local development checkout.
LIC=/out/licenses; rm -rf "$LIC"; mkdir -p "$LIC"
SRCDIR="$(find /work/src -maxdepth 1 -type d -name "libgphoto2-*" | head -1)"
[ -n "$SRCDIR" ] && [ -f "$SRCDIR/COPYING" ] || die "corresponding libgphoto2 source tree not found"
cp "$SRCDIR/COPYING" "$LIC/libgphoto2-COPYING.LGPL-2.1"
log "creating exact corresponding-source archive (this may take a minute)…"
( cd "$SRCDIR" && make dist-xz >/tmp/libgphoto2-dist.log 2>&1 ) || {
  tail -80 /tmp/libgphoto2-dist.log >&2; die "could not create corresponding-source archive";
}
SOURCE_ARCHIVE="$(find "$SRCDIR" -maxdepth 1 -type f -name 'libgphoto2-*.tar.xz' | sort | tail -1)"
[ -n "$SOURCE_ARCHIVE" ] || die "make dist-xz produced no source archive"
cp "$SOURCE_ARCHIVE" "$LIC/"
cp "$W/out/source-provenance.env" /out/build-source-provenance.txt
cat > "$LIC/README-LGPL.txt" <<EOF
The custom appfs in this output contains freshly-built libgphoto2
$LIBGPHOTO2_VERSION components under LGPL-2.1.

The adjacent $(basename "$SOURCE_ARCHIVE") is the exact corresponding source
used for these binaries after all patcher transformations. It includes the
complete preferred form for modification and its build system. The source was
generated before firmware repacking and contains no Benro firmware.

See this patcher's NOTICE and container/build_ptp2.sh for the build recipe.
EOF
log "  wrote exact LGPL corresponding source -> /out/licenses/$(basename "$SOURCE_ARCHIVE")"

if [ -n "$SSH_HOOK" ]; then
  log "SSH debug access is ENABLED in this image (/app/$SSH_HOOK):"
  log "    after flashing:  ssh -i <your private key> root@<polaris ip>"
  log "    anyone with that private key has root on the device over the network."
fi
# ---------------------------------------------------------------------------
# 8c. SSH hook (issue #31): also emit it standalone, so anyone who already has
#     device access (serial console, or the root password) can enable key login
#     WITHOUT flashing — and so the exact script that went into the appfs is
#     auditable.
# ---------------------------------------------------------------------------
if [ -n "$SSH_HOOK" ]; then
  SSHOUT=/out/ssh-debug; rm -rf "$SSHOUT"; mkdir -p "$SSHOUT"
  install -m 755 "$W/ssh_hook.sh" "$SSHOUT/$SSH_HOOK"
  cat > "$SSHOUT/README.txt" <<EOF
SSH debug access
================

The custom firmware in ../FwPkt now contains ONE extra appfs file:

    /app/$SSH_HOOK

It is the optional boot hook the stock /app/bootapp already calls if it exists,
so no existing firmware file had to be modified to add it. At every boot it
appends your public key(s) to /root/.ssh/authorized_keys. The stock firmware
already runs OpenSSH (/usr/local/bin/sshd, started by /etc/init.d/rcS, with
PermitRootLogin yes) — only the key was missing.

After flashing:

    ssh -i <your private key> root@<polaris ip>

Install it WITHOUT flashing (if you already have device access):

    scp $SSH_HOOK root@<polaris ip>:/app/$SSH_HOOK
    ssh root@<polaris ip> 'chmod +x /app/$SSH_HOOK && /app/$SSH_HOOK'
    # (it also runs itself on every subsequent boot)

Remove it:

    rm /app/$SSH_HOOK
    # and drop your key from /root/.ssh/authorized_keys
    # or reflash stock firmware, which restores both partitions

SECURITY: anyone holding the matching PRIVATE key gets root on this Polaris
over the network. The device's sshd also still accepts the stock root password,
which this tool does not change.
EOF
  log "  wrote standalone ssh hook -> /out/ssh-debug/$SSH_HOOK (install without flashing; see README.txt)"
fi

log "----------------------------------------------------------------------"
if [ "$MODE" = "full" ]; then
  log "DONE (mode: FULL libgphoto2 — core+port+ptp2+usb1 swap, on-disk trampoline)."
else
  log "DONE (mode: ptp2-only — legacy camlib+iolib swap, stock 2.5.27 core kept)."
fi
log "Custom firmware written to /out :"
( cd /out && find FwPkt -type f | sort | sed 's/^/    /' )
log "    FwPkt.zip  md5=$(md5sum /out/FwPkt.zip 2>/dev/null | cut -d' ' -f1)"
log "custom appfs.ubifs md5=$(md5sum /out/FwPkt/camera/appfs.ubifs | cut -d' ' -f1)"
if [ "$MODE" = "full" ]; then
  log "Before flashing you can TEST reversibly on-device:"
  log "    copy /out/stage2-ondisk to the camera and run ondisk/install_stage2.sh"
  log "    (revert with ondisk/restore_stock.sh). See docs/HOW-IT-WORKS.md."
fi
log "----------------------------------------------------------------------"
warn "FLASH AT YOUR OWN RISK. Verify on your own device. Keep your stock FwPkt"
warn "as the factory-restore image. See README.md."
