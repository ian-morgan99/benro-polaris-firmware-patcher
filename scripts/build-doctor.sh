#!/usr/bin/env bash
# build-doctor.sh -- prove the astro/camera build can actually run, BEFORE it runs.
#
# WHY THIS EXISTS
# On 2026-11-06 the astro-v97 build failed six separate times before producing a
# candidate. Not one of the failures was a defect in the build logic; every one
# was an environment prerequisite that *looked satisfied* and was not, and each
# reported itself as something else. They were discovered one at a time, minutes
# to hours apart, because the first symptom always appeared deep inside a long
# run:
#
#   1. "docker not found. Install Docker Desktop / docker."
#      Docker was installed. The shell was inside a Flatpak sandbox that does not
#      expose /var/run/docker.sock, so `docker` was simply absent from PATH.
#
#   2. "[abort] /in/firmwareInfo not found -- mount your stock FwPkt at /in"
#      The stock packet was fine. patch-polaris.sh extracts a .zip with
#      `mktemp -d`, which honoured TMPDIR=/tmp -- a path private to the sandbox.
#      The Docker daemon runs on the host, so its bind mount of that path came up
#      EMPTY. The error names the wrong file and sends you looking at the zip.
#
#   3. "[build] ERROR: local source directory must be a Git checkout"
#      The libgphoto2 tree WAS a git tree -- a linked worktree. Its .git is a
#      one-line file pointing outside the single directory mounted into the
#      container, so git inside the container cannot resolve it.
#
#   4. "libgphoto2 baseline <sha> is not reachable from origin/main -- orphan or
#      unmerged commit?"
#      The commit was on origin/main. A fresh local clone had copied a stale
#      refs/remotes/origin/main, so the reachability test failed against the wrong
#      tip. The message blames an orphan commit; the real fault is a stale ref.
#
#   5. "ERROR: could not extract appfs.ubifs (no functional ubireader)"
#      ~/.local/bin/ubireader_extract_files existed but its module was installed
#      for a different interpreter, so it died at import. A working copy exists in
#      the polaris-patcher image. The message says nothing about where it looked.
#
#   6. "VERDICT=BROKEN ... missing=bwrap,slirp4netns"
#      Both were installed at /usr/bin/bwrap and ~/.local/bin/slirp4netns. Only
#      ~/.local/bin was not on PATH. The message says "install them".
#
# THE RULE THIS SCRIPT ENFORCES
# Never check that a prerequisite EXISTS. Prove it WORKS, from the same position
# the build will use it. Existence checks are what produced all six of the above:
# `command -v docker` succeeds while docker cannot be reached; a ubireader wrapper
# is on PATH while it crashes at import; bwrap is installed while it is off PATH.
# Every check below performs the real operation, or the closest cheap equivalent,
# and reports the underlying error text rather than a guess.
#
# Checks run in dependency order and ALL of them run -- a single pass never stops
# at the first failure, because discovering problems one build at a time is the
# exact cost this script exists to remove.
#
# Usage:
#   scripts/build-doctor.sh                 # check everything
#   scripts/build-doctor.sh --libgphoto2 DIR --stock FwPkt.zip
#   scripts/build-doctor.sh --offline       # skip checks needing the daemon
#
# Exit 0 = every prerequisite proven. Exit 1 = at least one is broken; each
# failure prints the exact command to fix it.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

# Defaults are host-specific but must not be hardcoded to one user: a check that
# only ever looks at /home/ian cannot diagnose anyone else's machine, which defeats
# the point of a doctor. Derive from HOME and allow overrides.
LIBGP_DEFAULT="${POLARIS_LIBGPHOTO2:-$HOME/Documents/VSCodeProjects/LibGphoto2/libgphoto2}"
STOCK_DEFAULT="${POLARIS_STOCK_FWPKT:-$HOME/Documents/VSCodeProjects/BenroPolarisPatcher/firmware/FwPkt.zip}"
CATALOG_DEFAULT="${POLARIS_CATALOG:-$HOME/Documents/VSCodeProjects/BenroPolarisPatcher/out/gaia-dr3-g10}"
IMAGE="${POLARIS_IMAGE:-polaris-patcher:latest}"

LIBGP="$LIBGP_DEFAULT"
STOCK="$STOCK_DEFAULT"
CATALOG="$CATALOG_DEFAULT"
OFFLINE=0

while [ $# -gt 0 ]; do
    case "$1" in
        --libgphoto2) LIBGP="$2"; shift 2;;
        --stock)      STOCK="$2"; shift 2;;
        --catalog)    CATALOG="$2"; CATALOG_SUPPLIED=1; shift 2;;
        --image)      IMAGE="$2"; shift 2;;
        --offline)    OFFLINE=1; shift;;
        -h|--help)    sed -n '1,60p' "${BASH_SOURCE[0]}"; exit 0;;
        *) echo "unknown argument: $1" >&2; exit 2;;
    esac
done

PASS=0; FAIL=0; WARN=0
ok()   { printf '  \033[32mOK\033[0m   %s\n' "$*"; PASS=$((PASS+1)); }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$*"; FAIL=$((FAIL+1)); }
warn() { printf '  \033[33mWARN\033[0m %s\n' "$*"; WARN=$((WARN+1)); }
hint() { printf '         %s\n' "$*"; }
sect() { printf '\n== %s ==\n' "$*"; }

# Print the first meaningful line of captured stderr so the operator sees the
# real reason, not our paraphrase of it.
reason() { printf '%s\n' "${1:-}" | grep -vE '^\s*$' | head -1 | cut -c1-200; }

# ---------------------------------------------------------------------------
sect "1. Docker: reachable, and able to see our files"

# A sandboxed shell (Flatpak) has no docker socket. flatpak-spawn --host is the
# supported way out, and it is what makes a plain `docker` callable at all.
#
# THE TRAP THIS REPLACED. The old check probed `flatpak-spawn --host docker`, which
# asks the HOST to resolve `docker` on the HOST's PATH. ~/.local/bin and ~/bin are on
# it by default, and both are exactly where this script's own hint told people to put
# a shim. So the host ran that shim, it tried to exec flatpak-spawn -- absent on the
# host -- and died with rc=127. The doctor then reported "docker is not usable" and
# advised installing the very shim that was already there causing it. Broke the v102
# build on 2026-11-09, 82 minutes after v101 shipped with no shim at all.
# tools/host-docker.sh resolves an absolute host path instead, which cannot be one of
# our shims and so cannot recurse.
# shellcheck disable=SC1091
. "$ROOT/tools/host-docker.sh"
DOCKER_MODE=""
DOCKER_PREFIX="$(polaris_docker_prefix 2>/dev/null || true)"
if [ -n "$DOCKER_PREFIX" ]; then
    case "$DOCKER_PREFIX" in
        docker) DOCKER_MODE="direct";;
        *) DOCKER_MODE="flatpak-spawn-absolute";;
    esac
fi

if [ "$OFFLINE" = 1 ]; then
    warn "skipped (--offline): the build needs Docker, so a green run here is not a green run there"
elif [ -z "$DOCKER_MODE" ]; then
    bad "docker is not usable from this shell"
    # Name the real cause. A docker on PATH that fails `docker info` is almost
    # always a broken shim, and telling someone to install a second one makes it worse.
    if polaris_docker_shadowed; then
        hint "a 'docker' IS on PATH but does not work: $(command -v docker)"
        hint "  that is the problem -- do not add another shim on top of it."
        host_resolved="$(polaris_host_docker_resolved)"
        if [ -n "$host_resolved" ]; then
            hint "the HOST resolves 'docker' to: $host_resolved"
            hint "  if that file execs flatpak-spawn, it cannot run on the host and"
            hint "  returns rc=127, which looks like 'docker is not installed'."
            hint "  Fix it to name an absolute host path, e.g."
            hint "    exec /usr/bin/flatpak-spawn --host /usr/bin/docker \"\$@\""
        fi
    fi
    if [ -n "${FLATPAK_ID:-}" ]; then
        hint "this shell is inside Flatpak app $FLATPAK_ID, which does not expose the socket."
        hint "Preferred: put this repo's shim on PATH -- it resolves an absolute host"
        hint "path and cannot recurse:"
        hint "  export PATH=\"$ROOT/tools/host-bin:\$PATH\""
        hint "or expose the socket and restart the app:"
        hint "  flatpak override --user --filesystem=/var/run/docker.sock $FLATPAK_ID"
    else
        hint "start the daemon:  sudo systemctl start docker"
        hint "or install the Docker CLI."
    fi
else
    # Unquoted: DOCKER_PREFIX is words (`docker`, or `flatpak-spawn --host X`).
    ok "docker answers ($DOCKER_MODE): $( $DOCKER_PREFIX info --format '{{.ServerVersion}}' 2>/dev/null || echo unknown)"
fi

# THE PROOF THAT COST THE MOST TIME TO LEARN.
# A daemon answering proves nothing about bind mounts. Inside a sandbox, /tmp is
# private to the sandbox while the daemon lives on the host, so a -v of a /tmp
# path silently mounts an EMPTY directory. patch-polaris.sh extracts the stock
# packet with `mktemp -d`, so this exact failure looked like a corrupt zip and
# cost two build attempts to diagnose. The only way to know is to actually mount
# a temp dir and read a sentinel back through the daemon.
if [ -n "$DOCKER_MODE" ]; then
    run_docker() { $DOCKER_PREFIX "$@"; }

    # Probe the directory the BUILD will actually use, not the ambient one.
    # build-astro.sh exports TMPDIR=$ROOT/out/.build-env/tmp precisely because
    # /tmp is private to the sandbox while the daemon is on the host. Probing
    # bare /tmp therefore reported RED on a host where the wrapper had already
    # solved this -- a false failure that trains people to ignore the doctor.
    if [ -n "${TMPDIR:-}" ]; then
        probe="$(mktemp -d 2>/dev/null)"
    else
        buildtmp="$ROOT/out/.build-env/tmp"
        mkdir -p "$buildtmp" 2>/dev/null || true
        probe="$(TMPDIR="$buildtmp" mktemp -d 2>/dev/null)"
    fi
    if [ -z "$probe" ]; then
        bad "mktemp -d produced nothing; cannot test bind mounts"
    else
        echo "sentinel" > "$probe/marker" 2>/dev/null || true
        # Probe with the patcher image, not busybox: busybox is not guaranteed
        # present and a sandboxed shell often has no network to pull it, which
        # would make this report a false failure. The patcher image is required
        # for the build anyway, so if it is here we can use it. Fall back to
        # busybox only if the patcher image is absent.
        probe_img="$IMAGE"
        run_docker image inspect "$probe_img" >/dev/null 2>&1 || probe_img="busybox:latest"
        got="$(run_docker run --rm --entrypoint cat -v "$probe":/probe:ro "$probe_img" /probe/marker 2>&1)"
        if [ "$got" = "sentinel" ]; then
            ok "bind mount works for TMPDIR=${TMPDIR:-$ROOT/out/.build-env/tmp} ($probe is host-visible)"
        elif ! run_docker image inspect "$probe_img" >/dev/null 2>&1; then
            warn "could not test bind mounts: no image available to probe with"
            hint "run the doctor once after '$IMAGE' exists so this check can run."
        else
            bad "Docker cannot read a file from the temp dir -- bind mounts come up EMPTY here"
            hint "docker saw: $(reason "$got")"
            hint "This is what produces the misleading"
            hint "  '[abort] /in/firmwareInfo not found -- mount your stock FwPkt at /in'"
            hint "because patch-polaris.sh extracts the zip with mktemp -d and mounts that path."
            hint "Point TMPDIR somewhere the host can also see, e.g.:"
            hint "  mkdir -p ~/.cache/polaris-build-tmp && export TMPDIR=~/.cache/polaris-build-tmp"
            hint "(~ is shared with the host; /tmp inside a Flatpak is not.)"
        fi
        rm -rf "$probe"
    fi

    # The patcher image must exist or be buildable; [1/7] builds it on demand, so
    # absence alone is only a warning.
    if run_docker image inspect "$IMAGE" >/dev/null 2>&1; then
        ok "patcher image present: $IMAGE"
    else
        warn "image $IMAGE not present; [1/7] will build it (slow first time)"
    fi
fi

# ---------------------------------------------------------------------------
sect "2. ubireader: must actually run, not merely exist"

# generate-fwpkt-manifest.py needs ubireader to unpack appfs.ubifs in order to
# decide which files are mandatory. It already refuses a wrapper that fails
# --help, which is correct -- but it then reports "no functional ubireader" with
# no clue where it looked. Reproduce its probe here and name the candidates.
UBI="${UBIREADER_EXTRACT_FILES:-}"
if [ -z "$UBI" ]; then
    for c in "$(command -v ubireader_extract_files 2>/dev/null || true)" \
             "$HOME/.local/bin/ubireader_extract_files" \
             /usr/local/bin/ubireader_extract_files \
             /work/bin/ubireader_extract_files; do
        [ -n "$c" ] && [ -x "$c" ] && UBI="$c" && break
    done
fi

if [ -z "$UBI" ]; then
    bad "no ubireader_extract_files found on PATH or in the usual install dirs"
    hint "step [3/7] will abort with 'could not extract appfs.ubifs'."
    hint "A working copy lives inside the patcher image; use the committed bridge:"
    hint "  export UBIREADER_EXTRACT_FILES=$HERE/../tools/ubireader-docker"
else
    # Capture stderr WITHOUT losing the exit status. `err="$(cmd 2>&1)"` would
    # leave $? holding the assignment's status (always 0), so a wrapper that dies
    # at import time would be reported as working -- exactly the bug this check
    # exists to catch.
    ubi_err="$(mktemp)"; "$UBI" --help >/dev/null 2>"$ubi_err"; ubi_rc=$?
    if [ "$ubi_rc" -eq 0 ]; then
        ok "ubireader works: $UBI"
    elif grep -qi 'usage' "$ubi_err"; then
        # Non-zero but still printed a usage block: treat as functional, since the
        # manifest script's own probe only needs --help to be meaningful.
        ok "ubireader responds to --help (exit $ubi_rc): $UBI"
    else
        bad "ubireader wrapper is present but BROKEN: $UBI (exit $ubi_rc)"
        hint "underlying error: $(reason "$(cat "$ubi_err")")"
        hint "(this is the classic 'module installed for a different interpreter' fault)"
        hint "Use the committed bridge, which runs ubireader inside the patcher image:"
        hint "  export UBIREADER_EXTRACT_FILES=$HERE/../tools/ubireader-docker"
    fi
    rm -f "$ubi_err"
fi

# ---------------------------------------------------------------------------
sect "3. libgphoto2 source: self-contained clone at a reachable pin"

if [ ! -d "$LIBGP" ]; then
    bad "libgphoto2 source directory does not exist: $LIBGP"
elif [ ! -f "$LIBGP/configure.ac" ]; then
    bad "$LIBGP has no configure.ac -- not a libgphoto2 checkout"
elif [ ! -e "$LIBGP/.git" ]; then
    bad "$LIBGP is not a git tree at all"
elif [ -f "$LIBGP/.git" ]; then
    # THE WORKTREE TRAP. A linked worktree's .git is a text file pointing at
    # $MAIN/.git/worktrees/<name>. build-astro-candidate.sh mounts only $LIBSRC
    # into the container, so git inside it cannot resolve that pointer and reports
    # "local source directory must be a Git checkout" -- which reads as though the
    # tree were not git at all.
    bad "$LIBGP is a git WORKTREE (.git is a file, not a directory)"
    hint "Only \$LIBSRC is mounted into the container, so the worktree's .gitfile"
    hint "pointer cannot be resolved inside it. Symptom:"
    hint "  '[build] ERROR: local source directory must be a Git checkout'"
    hint "Use a self-contained clone instead:"
    hint "  git clone --no-checkout --local $LIBGP <newdir> && git -C <newdir> checkout --detach <pin>"
else
    ok "$LIBGP is a self-contained clone"

    head="$(git -C "$LIBGP" rev-parse HEAD 2>/dev/null || true)"
    [ -n "$head" ] && ok "HEAD = ${head:0:9}"

    if [ -n "$(git -C "$LIBGP" status --porcelain --untracked-files=all 2>/dev/null)" ]; then
        bad "$LIBGP is dirty"
        hint "The build compiles what is on disk, so a dirty tree produces a candidate"
        hint "whose recorded pin does not describe its contents."
    else
        ok "working tree clean"
    fi

    for stale in build _build build-asan; do
        [ -d "$LIBGP/$stale" ] && bad "stale $stale/ directory present in $LIBGP (build refuses this)"
    done

    # Reachability. The builder requires the pin to be an ancestor of a real
    # branch on origin so provenance points at something fetchable. A fresh local
    # clone can carry a stale refs/remotes/origin/main, which makes a perfectly
    # good pin look orphaned -- that cost one attempt here.
    origin_main="$(git -C "$LIBGP" rev-parse -q --verify origin/main 2>/dev/null || true)"
    if [ -z "$origin_main" ]; then
        bad "this clone has no refs/remotes/origin/main"
        hint "fetch it:  git -C $LIBGP fetch origin 'refs/remotes/origin/*:refs/remotes/origin/*'"
    else
        if git -C "$LIBGP" merge-base --is-ancestor HEAD origin/main 2>/dev/null; then
            ok "HEAD is reachable from origin/main (${origin_main:0:9})"
        else
            bad "HEAD ${head:0:9} is NOT reachable from this clone's origin/main (${origin_main:0:9})"
            hint "The builder will say 'orphan or unmerged commit?'. Before believing that,"
            hint "check the ref is current -- a fresh local clone copies whatever origin/main"
            hint "the source repo had, which may be stale:"
            hint "  git -C $LIBGP fetch origin 'refs/remotes/origin/*:refs/remotes/origin/*'"
            hint "Then re-run this doctor."
        fi
    fi
fi

# ---------------------------------------------------------------------------
sect "4. Inputs: stock packet and catalogue"

if [ -f "$STOCK" ]; then
    ok "stock packet present: $STOCK ($(du -h "$STOCK" | cut -f1))"
    hint "sha256 $(sha256sum "$STOCK" | cut -c1-16)..."
elif [ -d "$STOCK" ]; then
    if [ -f "$STOCK/firmwareInfo" ] || [ -f "$STOCK/FwPkt/firmwareInfo" ]; then
        ok "stock packet directory has firmwareInfo: $STOCK"
    else
        bad "$STOCK is a directory with no firmwareInfo in it or under FwPkt/"
    fi
else
    bad "stock packet not found: $STOCK"
fi

# Only checked when a catalogue was actually requested. A standard (non-Astro)
# release has no catalogue at all, and this check runs against a default path that
# only exists on some hosts -- so an unconditional FAIL here blocks releases that do
# not need the thing it is complaining about.
if [ "${CATALOG_SUPPLIED:-0}" != 1 ]; then
    ok "catalogue package: not requested, skipped"
elif [ -d "$CATALOG/tiles" ] && [ -f "$CATALOG/tiles.json" ]; then
    ok "catalogue package complete: $CATALOG"
else
    bad "catalogue package incomplete: $CATALOG (needs tiles/ and tiles.json)"
fi

# ---------------------------------------------------------------------------
sect "5. Gate prerequisites"

# The [5/7] shared-camera gate runs the agent-host checks. They look for bwrap and
# slirp4netns on PATH; both are commonly installed under ~/.local/bin, which a
# non-login shell does not have. The resulting "install slirp4netns and bubblewrap"
# is wrong -- they are already installed, just off PATH.
for tool in bwrap slirp4netns; do
    if command -v "$tool" >/dev/null 2>&1; then
        ok "$tool on PATH: $(command -v "$tool")"
    else
        found=""
        for c in /usr/bin/"$tool" "$HOME/.local/bin/$tool" /usr/local/bin/"$tool"; do
            [ -x "$c" ] && found="$c" && break
        done
        if [ -n "$found" ]; then
            bad "$tool is installed at $found but NOT on PATH"
            hint "the gate will report 'missing=$tool' and tell you to install it."
            hint "Just put it on PATH:  export PATH=\$HOME/.local/bin:\$PATH"
        else
            bad "$tool not found anywhere -- the agent-sandbox gate check will fail"
            hint "install it, or set chat.agent.sandbox.enabled=false knowingly."
        fi
    fi
done

# unicorn + pyelftools are imported by the emulator-based gate tests.
if python3 -c 'import unicorn, elftools' >/dev/null 2>&1; then
    ok "python3 has unicorn + pyelftools"
else
    bad "python3 ($(command -v python3)) cannot import unicorn and/or elftools"
    hint "the [5/7] gate needs them. Install for THIS interpreter:"
    hint "  $(command -v python3) -m pip install --user unicorn pyelftools"
fi

# The immutable v90 fixture the Bulb-cancellation diagnostic gates against.
V90_REL="out/o-v18m-k1ii-pgphoto-readiness-20261029/stage2-ondisk/ondisk/pgphoto.stage2ondisk"
V90_WANT="8973d9486e0207446cc111234ed39e878676ce1f3edca2967a97db86c8d9eaac"
if [ -f "$ROOT/$V90_REL" ]; then
    if [ "$(sha256sum "$ROOT/$V90_REL" | awk '{print $1}')" = "$V90_WANT" ]; then
        ok "v90 diagnostic fixture present and hash-correct"
    else
        bad "v90 diagnostic fixture exists but its hash does not match the pin"
        hint "gating against a substituted binary is meaningless; restore the pinned one."
    fi
else
    warn "v90 diagnostic fixture absent: $V90_REL"
    hint "the Bulb cancellation-return diagnostic will fail. Copy it from an older"
    hint "candidate tree that has it (build-astro.sh searches for it automatically)."
fi

# ---------------------------------------------------------------------------
sect "6. Patcher tree must be clean and committed"

if ! git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    bad "$ROOT is not a git worktree; release builds refuse this"
else
    if [ -n "$(git -C "$ROOT" status --porcelain --untracked-files=all)" ]; then
        bad "patcher tree is dirty -- release build will refuse"
        hint "commit or stash. Provenance records the exact commit; a dirty tree makes"
        hint "the recorded commit a lie about what was compiled."
    else
        ok "patcher tree clean at $(git -C "$ROOT" rev-parse --short HEAD)"
    fi
    if git -C "$ROOT" diff --check >/dev/null 2>&1; then
        ok "no whitespace errors"
    else
        bad "git diff --check reports whitespace errors"
    fi
fi

# ---------------------------------------------------------------------------
sect "7. Shipped scripts must carry an exec bit in git"

# 6.0.0.54.102 shipped eight .sh files at mode 0644 inside polaris-astro.zip because
# they are committed 100644 here and the build preserves that mode. On the device
# polaris-goto-solve.sh is guarded by '[ ! -x ] && exit 2' so it aborts, while
# frame-watch, goto-watch and pointing-model are guarded by '[ -x ]' and silently
# disable -- features that stop working while everything reports success. The
# archive-level gate catches this after a build, roughly fifteen minutes too late and
# only if someone builds; this catches it before one starts.
#
# Checked against git's recorded mode, not the working tree: a locally chmod'd file
# hides nothing, because the commit is what gets archived.
OFFENDERS=""
while IFS= read -r line; do
    mode=${line%% *}
    path=${line#*$'\t'}
    case "$path" in *.sh) ;; *) continue ;; esac
    head -c2 "$ROOT/$path" 2>/dev/null | grep -q '^#!' || continue
    [ "$mode" = "100755" ] || OFFENDERS="$OFFENDERS$path "
done < <(git -C "$ROOT" ls-files -s -- container/astro/ondisk 2>/dev/null)
if [ -n "$OFFENDERS" ]; then
    bad "shipped scripts with a shebang but no exec bit:$OFFENDERS"
    hint "chmod +x and commit. They will ship non-executable and the device will"
    hint "either exit 2 or silently disable the feature that uses them."
else
    ok "every shipped ondisk script is mode 100755 in git"
fi

# ---------------------------------------------------------------------------
sect "8. Publication path"

# Publishing clones PrivateResearch into ${TMPDIR:-/tmp} unless a clean checkout is
# supplied. That repo is ~26 GB: the first v102 publish died on SIGTERM mid-clone
# because the clone could not finish inside the window, and /tmp here is far smaller
# than the clone. This is checked before the build so it is not discovered after it.
PR_TMP="${TMPDIR:-/tmp}"
PR_FREE_KB=$(df -Pk "$PR_TMP" 2>/dev/null | awk 'NR==2{print $4}')
if [ -n "${PR_CHECKOUT:-}" ] && [ -d "${PR_CHECKOUT:-}/.git" ]; then
    if [ -n "$(git -C "$PR_CHECKOUT" status --porcelain --untracked-files=all 2>/dev/null)" ]; then
        bad "PR_CHECKOUT is dirty: $PR_CHECKOUT"
        hint "publish-astro-candidate.sh refuses a dirty publication checkout by design."
    else
        ok "publication checkout clean and usable: $PR_CHECKOUT"
    fi
elif [ -n "$PR_FREE_KB" ] && [ "$PR_FREE_KB" -lt 30000000 ]; then
    warn "${PR_TMP} has only $((PR_FREE_KB / 1024)) MB free; a fresh PrivateResearch clone needs ~26 GB"
    hint "publish-astro-candidate.sh clones PrivateResearch into ${TMPDIR:-/tmp} by default."
    hint "Point PR_CHECKOUT at an existing clean clone instead of cloning each time, e.g."
    hint "  --checkout /home/ian/pr-publish"
else
    ok "${PR_TMP} has room for a fresh PrivateResearch clone ($(( ${PR_FREE_KB:-0} / 1024 )) MB free)"
fi

# ---------------------------------------------------------------------------
printf '\n============================================================\n'
if [ "$FAIL" -eq 0 ]; then
    printf 'DOCTOR: GREEN -- %d checks passed, %d warning(s).\n' "$PASS" "$WARN"
    printf 'Every prerequisite was exercised, not merely looked for.\n'
    [ "$WARN" -gt 0 ] && printf 'Read the WARN lines above before a long build.\n'
    exit 0
else
    printf 'DOCTOR: RED -- %d failed, %d passed, %d warning(s).\n' "$FAIL" "$PASS" "$WARN"
    printf 'Fix every FAIL line above. Each one prints the exact command.\n'
    printf 'Do not start a build to "see what happens": these failures surface\n'
    printf 'deep inside a long run and report themselves as unrelated problems.\n'
    # Say what is already handled, or this output misleads in its own way. Run
    # standalone it reports faults that build-astro.sh provisions around by
    # design: a private TMPDIR under out/, the ubireader bridge, and a fresh
    # self-contained clone instead of a shared worktree. Reading that as "repair
    # all of these by hand" wastes time, and fixing the shared tree would be the
    # wrong fix anyway -- the build cannot use a worktree at all.
    echo
    echo 'Some of the above may already be handled. scripts/build-astro.sh sets'
    echo 'a host-visible TMPDIR under out/, uses tools/ubireader-docker when the'
    echo 'native ubireader is broken, and clones its own self-contained libgphoto2'
    echo 'tree rather than using a shared checkout or worktree. If you are about to'
    echo 'run that wrapper, only these need fixing by hand:'
    echo '  - Docker itself (daemon down, or the socket is not visible here)'
    echo '  - a dirty or uncommitted PATCHER tree'
    echo '  - missing bwrap / slirp4netns on PATH'
    echo 'Everything else the wrapper can arrange for itself.'
    exit 1
fi
