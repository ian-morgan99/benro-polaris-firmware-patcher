#!/usr/bin/env sh
# ============================================================================
#  Benro Polaris libgphoto2 patcher — macOS / Linux launcher
#
#  Everything runs inside Docker, so the only host requirement is Docker.
#
#  Usage:
#     ./patch-polaris.sh --fwpkt <FwPkt-folder-or-zip> [options]
#
#  Options:
#     --fwpkt PATH         stock FwPkt folder (has firmwareInfo) or FwPkt.zip  [required]
#     --libgphoto2 VER     libgphoto2 release to build            (default 2.5.34)
#     --libgphoto2-port VER  libgphoto2_port release tag         (default 0.12.2)
#     --libgphoto2-source PATH  local libgphoto2 checkout to build (optional)
#     --allow-dirty-source explicitly permit a dirty local Git checkout
#     --out DIR            output directory                       (default ./out)
#     --ptp2-only          conservative fallback: keep the stock 2.5.27 core, swap
#                          only the ptp2 camlib + usb1 iolib (+ 14-byte pgphoto patch).
#                          DEFAULT (no flag) is the full-libgphoto2 stack swap.
#     --selftest           qemu-emulate the driver load (R5 II registration)
#     --no-fix-typo        do NOT correct the upstream "EOS 5Rm2" model typo
#     --no-usb1            (ptp2-only) do NOT swap the usb1 iolib; patch ptp2 + pgphoto only
#     --pentax-max-capture-size BYTES  cap Pentax capture file-size (default 268435456 = 256 MiB)
#                                       Issue #2: libgphoto2's 2 GiB default is unsafe on Polaris RAM.
#     --cellular-modules DIR  inject pre-built kernel modules from DIR (Phase 3
#                             cellular). Expects usbserial.ko, option.ko,
#                             cdc_acm.ko, qcserial.ko — built against the
#                             device kernel (Linux 4.9.37 hi3559v200).  When
#                             omitted, the patcher still places a no-op loader
#                             and the script can be wired up by a later patch.
#     --image NAME         docker image tag              (default polaris-patcher)
#
#  READ THE README AND DISCLAIMERS FIRST.  Tested ONLY against FwVer 4.0.0.32
#  with a Canon EOS R5 Mark II.  Flashing firmware is at YOUR OWN RISK.
# ============================================================================
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
FWPKT=""; VER="2.5.34"; VER_SET=0; PORTVER="0.12.2"; LGSRC=""; ALLOW_DIRTY=0; OUT="$HERE/out"; SELFTEST=0; FIXTYPO=1; SWAPUSB1=1; IMG="polaris-patcher"; MODE="full"; PENTAX_MAX_CAPTURE_SIZE="268435456"; CELMODS=""

while [ $# -gt 0 ]; do
  case "$1" in
    --fwpkt) FWPKT="$2"; shift 2;;
    --libgphoto2) VER="$2"; VER_SET=1; shift 2;;
    --libgphoto2-port) PORTVER="$2"; shift 2;;
    --libgphoto2-source) LGSRC="$2"; shift 2;;
    --allow-dirty-source) ALLOW_DIRTY=1; shift;;
    --out) OUT="$2"; shift 2;;
    --ptp2-only) MODE="ptp2only"; shift;;
    --selftest) SELFTEST=1; shift;;
    --no-fix-typo) FIXTYPO=0; shift;;
    --no-usb1) SWAPUSB1=0; shift;;
    --pentax-max-capture-size) PENTAX_MAX_CAPTURE_SIZE="$2"; shift 2;;
    --cellular-modules) CELMODS="$2"; shift 2;;
    --image) IMG="$2"; shift 2;;
    -h|--help) sed -n '2,34p' "$0"; exit 0;;
    *) echo "unknown option: $1" >&2; exit 1;;
  esac
done

if [ -n "$CELMODS" ]; then
  [ -d "$CELMODS" ] || { echo "error: --cellular-modules: '$CELMODS' is not a directory" >&2; exit 1; }
  CELMODS="$(cd "$CELMODS" && pwd)"
fi

[ -n "$FWPKT" ] || { echo "error: --fwpkt is required" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "error: docker not found. Install Docker Desktop / docker." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "error: docker daemon not running." >&2; exit 1; }
if [ -n "$LGSRC" ]; then
  [ "$VER_SET" -eq 0 ] || { echo "error: --libgphoto2 and --libgphoto2-source are mutually exclusive" >&2; exit 1; }
  if [ -d "$LGSRC" ]; then
    [ -f "$LGSRC/configure.ac" ] || { echo "error: source checkout lacks configure.ac" >&2; exit 1; }
    LGSRC="$(cd "$LGSRC" && pwd)"
  elif [ -f "$LGSRC" ]; then
    LGSRC="$(cd "$(dirname "$LGSRC")" && pwd)/$(basename "$LGSRC")"
  else
    echo "error: --libgphoto2-source must be a checkout or source archive" >&2; exit 1
  fi
fi

# --- resolve input into a folder that contains firmwareInfo -----------------
STAGE="$(mktemp -d)"; trap 'rm -rf "$STAGE"' EXIT
IN=""
if [ -d "$FWPKT" ] && [ -f "$FWPKT/firmwareInfo" ]; then
  IN="$FWPKT"
elif [ -d "$FWPKT" ] && [ -f "$FWPKT/FwPkt/firmwareInfo" ]; then
  IN="$FWPKT/FwPkt"
elif [ -f "$FWPKT" ]; then                      # a .zip
  echo "[*] extracting $FWPKT …"
  if command -v unzip >/dev/null 2>&1; then unzip -oq "$FWPKT" -d "$STAGE";
  elif command -v python3 >/dev/null 2>&1; then python3 -m zipfile -e "$FWPKT" "$STAGE";
  else echo "error: need 'unzip' or 'python3' to read the zip, or pass an unzipped folder." >&2; exit 1; fi
  if [ -f "$STAGE/firmwareInfo" ]; then IN="$STAGE";
  elif [ -f "$STAGE/FwPkt/firmwareInfo" ]; then IN="$STAGE/FwPkt";
  else echo "error: could not find firmwareInfo inside the zip." >&2; exit 1; fi
else
  echo "error: --fwpkt must be a FwPkt folder (with firmwareInfo) or a FwPkt.zip" >&2; exit 1
fi

mkdir -p "$OUT"
echo "[*] building docker image '$IMG' (first run only)…"
# NOT quiet, and the exit code IS checked with a clear message: a silent build
# failure used to let this script sail on against a stale image and print [✓]
# over output that was never produced (issue #29).
if ! docker build -t "$IMG" -f "$HERE/docker/Dockerfile" "$HERE"; then
  echo "error: docker build failed. The build output above says why; nothing was patched." >&2
  exit 1
fi

echo "[*] running patcher (mode: $MODE)…"
set --
if [ -n "$LGSRC" ]; then set -- "$@" -v "$LGSRC:/libgphoto2-source-input:ro"; fi
if [ -n "$CELMODS" ]; then set -- "$@" -v "$CELMODS:/cellular-modules-input:ro"; fi
docker run --rm \
  -e MODE="$MODE" \
  -e LIBGPHOTO2_VERSION="$VER" -e LIBGPHOTO2_PORT_VERSION="$PORTVER" \
  -e PENTAX_MAX_CAPTURE_SIZE="$PENTAX_MAX_CAPTURE_SIZE" \
  -e FIX_R5M2_TYPO="$FIXTYPO" -e SELFTEST="$SELFTEST" \
  -e SWAP_USB1="$SWAPUSB1" \
  -e ALLOW_DIRTY_SOURCE="$ALLOW_DIRTY" \
  -e CELLULAR_MODULES_DIR="${CELMODS:+/cellular-modules-input}" \
  "$@" \
  -v "$IN":/in:ro -v "$OUT":/out \
  "$IMG"

echo
echo "[✓] Output in: $OUT"
echo "    - $OUT/FwPkt/         (unpacked custom firmware)"
echo "    - $OUT/FwPkt.zip      (copy this to your SD card)"
echo "    Keep your STOCK FwPkt as the factory-restore image."
