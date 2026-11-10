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
#     --camlibs LIST        explicit comma-separated camlibs      (default ptp2,pentax)
#     --libgphoto2-source PATH  local libgphoto2 checkout/archive to build
#                              (required in full mode unless vanilla is explicit)
#     --allow-vanilla-source explicitly permit a stock release build without a source input
#     --allow-dirty-source explicitly permit a dirty local Git checkout
#     --allow-dirty-patcher explicitly permit a dirty patcher tree (diagnostic only)
#     --out DIR            output directory                       (default ./out)
#     --ptp2-only          conservative fallback: keep the stock 2.5.27 core, swap
#                          only the ptp2 camlib + usb1 iolib (+ 14-byte pgphoto patch).
#                          DEFAULT (no flag) is the full-libgphoto2 stack swap.
#     --selftest           qemu-emulate the driver load (R5 II registration)
#     --no-fix-typo        do NOT correct the upstream "EOS 5Rm2" model typo
#     --no-usb1            (ptp2-only) do NOT swap the usb1 iolib; patch ptp2 + pgphoto only
#     --enable-usb-scsi    include the optional legacy Pentax K-5 II/K-5 IIs transport
#     --pentax-max-capture-size BYTES  cap Pentax capture file-size (default 268435456 = 256 MiB)
#                                       Issue #2: libgphoto2's 2 GiB default is unsafe on Polaris RAM.
#     --ssh-key FILE|KEY   opt-in: authorise a public key for root SSH debugging
#                          (issue #31). FILE may be a path to an authorized_keys
#                          file or the key line(s) themselves. OFF by default —
#                          without it the build is byte-for-byte unchanged.
#     --build-id ID        embed a human-readable build identifier (e.g.
#                          "6.0.0.54.1") into /app/openpolaris-libgphoto2-provenance.txt
#                          so patcher-only builds (same libgphoto2 commit, different
#                          patcher) are distinguishable at runtime. OFF by default.
#     --display-fwver VER  override the camera's four-part base plus optional
#                          numeric build suffix used in the app-visible code-780
#                          version (e.g. 4.0.0.32.22). Independent of --build-id.
#     --image NAME         docker image tag              (default polaris-patcher)
#
#  READ THE README AND DISCLAIMERS FIRST.  Tested ONLY against FwVer 4.0.0.32
#  with a Canon EOS R5 Mark II.  Flashing firmware is at YOUR OWN RISK.
# ============================================================================
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
FWPKT=""; VER="2.5.34"; VER_SET=0; PORTVER="0.12.2"; CAMLIBS="ptp2,pentax"; LGSRC=""; ALLOW_DIRTY=0; ALLOW_DIRTY_PATCHER=0; ALLOW_VANILLA=0; OUT="$HERE/out"; SELFTEST=0; FIXTYPO=1; SWAPUSB1=1; ENABLE_USB_SCSI=0; IMG="polaris-patcher"; MODE="full"; PENTAX_MAX_CAPTURE_SIZE="268435456"; SSHKEY=""; BUILDID=""; DISPLAY_FWVER=""

while [ $# -gt 0 ]; do
  case "$1" in
    --fwpkt) FWPKT="$2"; shift 2;;
    --libgphoto2) VER="$2"; VER_SET=1; shift 2;;
    --libgphoto2-port) PORTVER="$2"; shift 2;;
    --camlibs) CAMLIBS="$2"; shift 2;;
    --libgphoto2-source) LGSRC="$2"; shift 2;;
    --allow-dirty-source) ALLOW_DIRTY=1; shift;;
    --allow-dirty-patcher) ALLOW_DIRTY_PATCHER=1; shift;;
    --allow-vanilla-source) ALLOW_VANILLA=1; shift;;
    --out) OUT="$2"; shift 2;;
    --ptp2-only) MODE="ptp2only"; shift;;
    --selftest) SELFTEST=1; shift;;
    --no-fix-typo) FIXTYPO=0; shift;;
    --no-usb1) SWAPUSB1=0; shift;;
    --enable-usb-scsi) ENABLE_USB_SCSI=1; shift;;
    --pentax-max-capture-size) PENTAX_MAX_CAPTURE_SIZE="$2"; shift 2;;
    --ssh-key) SSHKEY="$2"; shift 2;;
    --build-id) BUILDID="$2"; shift 2;;
    --display-fwver) DISPLAY_FWVER="$2"; shift 2;;
    --image) IMG="$2"; shift 2;;
    -h|--help) sed -n '2,32p' "$0"; exit 0;;
    *) echo "unknown option: $1" >&2; exit 1;;
  esac
done

[ -n "$FWPKT" ] || { echo "error: --fwpkt is required" >&2; exit 1; }
if [ -n "$DISPLAY_FWVER" ]; then
  case "$DISPLAY_FWVER" in *[!0-9.]*|.*|*..*|*.)
    echo "error: --display-fwver must be dotted numeric components, e.g. 4.0.0.32.22" >&2
    exit 1;;
  esac
  DISPLAY_FWVER_PARTS=$(printf '%s' "$DISPLAY_FWVER" | awk -F. '{print NF}')
  [ "$DISPLAY_FWVER_PARTS" -eq 4 ] || [ "$DISPLAY_FWVER_PARTS" -eq 5 ] || {
    echo "error: --display-fwver must have four components plus an optional build counter" >&2; exit 1; }
fi
case "$CAMLIBS" in
  *[!a-zA-Z0-9_,-]*|,*|*,|*,,*) echo "error: invalid --camlibs list: $CAMLIBS" >&2; exit 1;;
esac
case ",$CAMLIBS," in
  *,ptp2,*) : ;;
  *) echo "error: production Polaris builds require ptp2 (Canon/Pentax PTP path)" >&2; exit 1;;
esac
# Normalise --out to an absolute path BEFORE docker run: a relative path like
# "out/k3iii-128fix" is parsed by the docker CLI as a *named volume* (invalid
# characters) instead of a host directory, so the run dies with exit 125.
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
# docker must be callable as plain `docker`, because every `docker run -v` below
# is written that way. Inside the VS Code Flatpak sandbox there is no docker binary
# at all, so put this repo's shim first on PATH. tools/host-bin/docker resolves an
# ABSOLUTE host path via tools/host-docker.sh; it deliberately does not run
# `flatpak-spawn --host docker`, because that asks the host to resolve `docker` on
# the host's PATH, where ~/.local/bin and ~/bin sit by default -- if either holds a
# shim of that same shape the host runs it, it cannot exec flatpak-spawn, and it
# dies with rc=127 reading exactly like "docker is not installed". That is what
# stopped the v102 build (#308).
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    if [ -x "$HERE/tools/host-bin/docker" ]; then
        PATH="$HERE/tools/host-bin:$PATH"
        export PATH
    fi
fi
command -v docker >/dev/null 2>&1 || { echo "error: docker not found. Install Docker Desktop / docker." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "error: a 'docker' exists but cannot reach a daemon:" >&2
    echo "       $(command -v docker)" >&2
    echo "       run scripts/build-doctor.sh, which names the exact cause." >&2
    exit 1; }
docker info >/dev/null 2>&1 || { echo "error: docker daemon not running." >&2; exit 1; }
PATCHER_COMMIT="unknown"
PATCHER_DIRTY_HASH=""
if git -C "$HERE" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  PATCHER_COMMIT=$(git -C "$HERE" rev-parse HEAD)
  PATCHER_STATUS=$(git -C "$HERE" status --porcelain --untracked-files=all)
  if [ -n "$PATCHER_STATUS" ]; then
    PATCHER_DIRTY_HASH=$(cd "$HERE" && {
      git diff --binary HEAD
      git ls-files --others --exclude-standard -z | sort -z | xargs -0 -r sha256sum
    } | sha256sum | awk '{print $1}')
    if [ "$ALLOW_DIRTY_PATCHER" -ne 1 ]; then
      echo "error: patcher tree is dirty (hash $PATCHER_DIRTY_HASH); refusing release build" >&2
      echo "       commit/stash all patcher changes, or use --allow-dirty-patcher for diagnostic-only output" >&2
      exit 1
    fi
    echo "warning: dirty patcher tree opted in (hash $PATCHER_DIRTY_HASH); output is diagnostic-only" >&2
  fi
else
  echo "error: patcher directory is not a Git worktree; refusing provenance-unsafe release build" >&2
  exit 1
fi
if [ "$MODE" = "full" ] && [ -z "$LGSRC" ] && [ "$ALLOW_VANILLA" -ne 1 ]; then
  echo "error: full mode requires --libgphoto2-source so a stock release cannot silently replace the project fork." >&2
  echo "       Use --allow-vanilla-source only for an intentional, provenance-marked stock build." >&2
  exit 1
fi
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
# STAGE is where a .zip gets unpacked, and it is bind-mounted into the container
# as /in. mktemp honours TMPDIR, which matters more than it looks: inside a
# Flatpak sandbox /tmp is private to the sandbox while the Docker daemon runs on
# the host, so mounting a /tmp path yields an EMPTY /in. The patcher then reports
# "[abort] /in/firmwareInfo not found -- mount your stock FwPkt at /in", which
# points at the zip and not at TMPDIR. That cost two build attempts on 2026-11-06.
# The preflight below catches it; run scripts/build-doctor.sh to check first.
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

# --ssh-key (issue #31): accept a path to an authorized_keys file or the key
# line(s) themselves; pass the key material through as SSH_PUBKEY.
SSH_PUBKEY=""
if [ -n "$SSHKEY" ]; then
  if [ -f "$SSHKEY" ]; then
    SSH_PUBKEY="$(cat "$SSHKEY")"
  else
    SSH_PUBKEY="$SSHKEY"
  fi
fi

# --- bind-mount preflight ---------------------------------------------------
# Prove the container can actually read the packet BEFORE the long build, using
# the same image and the same mount the real run will use. Without this, an empty
# mount surfaces ~4 minutes later as "[abort] /in/firmwareInfo not found -- mount
# your stock FwPkt at /in", which blames the input file when the fault is that the
# host path is invisible to the daemon (sandbox-private TMPDIR, or a path outside
# what the sandbox/daemon share).
if ! docker run --rm -v "$IN":/in:ro --entrypoint test "$IMG" -e /in/firmwareInfo \
     >/dev/null 2>&1; then
  echo "error: the patcher container cannot see firmwareInfo at /in, although it exists on the host." >&2
  echo "       host path mounted read-only: $IN" >&2
  if [ -d "$STAGE" ] && [ "$IN" = "$STAGE" -o "$IN" = "$STAGE/FwPkt" ]; then
    echo "       That path came from 'mktemp -d' (TMPDIR=${TMPDIR:-/tmp})." >&2
    echo "       The Docker daemon runs on the host and cannot see a sandbox-private" >&2
    echo "       /tmp, so the mount comes up empty. Point TMPDIR at a shared location:" >&2
    echo "         mkdir -p \$HOME/.cache/polaris-build-tmp" >&2
    echo "         export TMPDIR=\$HOME/.cache/polaris-build-tmp" >&2
  else
    echo "       Check that this path is visible to the Docker daemon, not confined" >&2
    echo "       to a sandbox. From a host shell it must exist and be readable." >&2
  fi
  echo "       Diagnose everything at once with: scripts/build-doctor.sh" >&2
  exit 1
fi

echo "[*] running patcher (mode: $MODE)…"
set --
if [ -n "$LGSRC" ]; then set -- -v "$LGSRC:/libgphoto2-source-input:ro"; fi
docker run --rm \
  -e MODE="$MODE" \
  -e LIBGPHOTO2_VERSION="$VER" -e LIBGPHOTO2_PORT_VERSION="$PORTVER" \
  -e POLARIS_CAMLIBS="$CAMLIBS" \
  -e PENTAX_MAX_CAPTURE_SIZE="$PENTAX_MAX_CAPTURE_SIZE" \
  -e FIX_R5M2_TYPO="$FIXTYPO" -e SELFTEST="$SELFTEST" \
  -e SWAP_USB1="$SWAPUSB1" \
  -e POLARIS_ENABLE_USB_SCSI="$ENABLE_USB_SCSI" \
  -e ALLOW_DIRTY_SOURCE="$ALLOW_DIRTY" \
  -e PATCHER_COMMIT="$PATCHER_COMMIT" \
  -e PATCHER_DIRTY_HASH="$PATCHER_DIRTY_HASH" \
  -e ALLOW_VANILLA_SOURCE="$ALLOW_VANILLA" \
  -e SSH_PUBKEY="$SSH_PUBKEY" \
  -e BUILD_ID="$BUILDID" \
  -e DISPLAY_FWVER="$DISPLAY_FWVER" \
  "$@" \
  -v "$IN":/in:ro -v "$OUT":/out \
  "$IMG"

# The patcher container runs as root so it can create the firmware filesystem.
# That leaves the mounted candidate files owned by root, which prevents the
# host-side release builder from adding its immutable release metadata. Return
# ownership of the complete output tree to the invoking user before any host
# validation or publication step runs.
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
echo "[*] returning candidate ownership to host uid=${HOST_UID} gid=${HOST_GID}"
docker run --rm --user 0 \
  --entrypoint /bin/sh \
  -v "$OUT":/out \
  "$IMG" \
  -c 'chown -R "$1:$2" /out' sh "$HOST_UID" "$HOST_GID"

echo
echo "[✓] Output in: $OUT"
echo "    - $OUT/FwPkt/         (unpacked custom firmware)"
echo "    - $OUT/FwPkt.zip      (copy this to your SD card)"
echo "    Keep your STOCK FwPkt as the factory-restore image."
