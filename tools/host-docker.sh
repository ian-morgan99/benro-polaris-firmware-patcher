#!/bin/sh
# ============================================================================
#  host-docker.sh -- resolve a docker command that actually works from here.
#
#  WHY THIS EXISTS
#  ---------------
#  Every build path in this repo needs one thing: a `docker` that reaches the
#  daemon. Inside the VS Code Flatpak sandbox there is no socket and no docker
#  binary, so the documented route out is `flatpak-spawn --host docker`. That
#  form has a failure mode that took down a release build on 2026-11-09:
#
#      exec flatpak-spawn --host docker "$@"
#
#  `--host docker` asks the HOST to resolve `docker` on the HOST's PATH. If the
#  host's PATH contains a shim of this same shape -- and ~/.local/bin and ~/bin
#  are both on it by default -- the host finds that shim, which then tries to
#  exec flatpak-spawn, which does not exist on the host at all:
#
#      $ docker info
#      /home/ian/bin/docker: 5: exec: /usr/bin/flatpak-spawn: not found   (rc=127)
#
#  The shim calls out to the host, the host calls back into the same file, and
#  the loop ends only because the second hop cannot exec. It looks exactly like
#  "docker is not installed", which is why build-doctor.sh told the operator to
#  install a shim when a shim was already there and was the cause.
#
#  THE RULE: never hand a bare command name to `--host`. Resolve an absolute
#  path on the host and use that. A system location can never be one of our
#  shims, so it cannot recurse.
#
#  USAGE
#     . tools/host-docker.sh
#     POLARIS_DOCKER="$(polaris_docker_prefix)" || die "no usable docker"
#     $POLARIS_DOCKER info
#
#  polaris_docker_prefix prints the command prefix, empty if unusable. It is
#  deliberately a prefix and not a function, so callers can put it in a variable
#  and use it unquoted the way `docker "$@"` is used today.
# ============================================================================

# Absolute locations only. Deliberately excludes $HOME/bin and ~/.local/bin:
# those are exactly where a recursing shim tends to live, and a real docker CLI
# is never installed there.
POLARIS_DOCKER_HOST_CANDIDATES="/usr/bin/docker /usr/local/bin/docker /snap/bin/docker /opt/docker/bin/docker"

polaris_have_flatpak_spawn() {
    command -v flatpak-spawn >/dev/null 2>&1
}

# Absolute path of a working docker on the HOST, or empty. Probed with `test -x`
# rather than by running docker, so it costs milliseconds; liveness is confirmed
# separately by polaris_docker_prefix.
polaris_host_docker_abs() {
    polaris_have_flatpak_spawn || return 0
    for c in $POLARIS_DOCKER_HOST_CANDIDATES; do
        if flatpak-spawn --host test -x "$c" 2>/dev/null; then
            printf '%s\n' "$c"
            return 0
        fi
    done
    return 0
}

# Print a usable docker command prefix, or nothing. Order matters: a plain
# working docker on PATH is preferred, because it is the cheapest and needs no
# portal.
polaris_direct_docker_usable() {
    # If we are already inside one of this repo's docker shims, the plain
    # `docker` on PATH *is* that shim. Probing it would re-enter this script and
    # recurse, so refuse the direct branch outright.
    [ -n "${POLARIS_SHIM_ACTIVE:-}" ] && return 1
    command -v docker >/dev/null 2>&1 || return 1
    case "$(command -v docker 2>/dev/null)" in
        */tools/host-bin/docker) return 1;;
    esac
    docker info >/dev/null 2>&1
}

polaris_docker_prefix() {
    if polaris_direct_docker_usable; then
        printf 'docker\n'
        return 0
    fi
    if polaris_have_flatpak_spawn; then
        abs="$(polaris_host_docker_abs)"
        if [ -n "$abs" ] \
                && flatpak-spawn --host "$abs" info >/dev/null 2>&1; then
            printf 'flatpak-spawn --host %s\n' "$abs"
            return 0
        fi
    fi
    return 1
}

# True when a `docker` exists on PATH but does not work. That is the case the
# operator most needs told about: an existing broken shim, not a missing one.
polaris_docker_shadowed() {
    command -v docker >/dev/null 2>&1 || return 1
    ! docker info >/dev/null 2>&1
}

# Where the HOST resolves `docker` to. This is the check that was missing: the
# sandbox PATH and the host PATH differ, so a shim can be absent here yet first on
# the host's PATH -- which is what `flatpak-spawn --host docker` actually runs.
# Printing it turns "docker is not usable" into "the host runs <path>, which
# cannot exec flatpak-spawn".
polaris_host_docker_resolved() {
    polaris_have_flatpak_spawn || return 0
    flatpak-spawn --host sh -c 'command -v docker 2>/dev/null' 2>/dev/null || true
}
