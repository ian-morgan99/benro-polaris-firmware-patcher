#!/bin/sh
# test_shell_no_bare_fragments.sh — catch stray short lines in shell scripts
#
# Why this exists. tests/run_prerelease_gate.sh shipped with two bare command lines,
# `s` and `ped`, on 2026-11-09 (caught by review on PR #298). They were not intended
# code: they are the tail fragments of "as" and "shipped" from a comment that had been
# pasted in already hard-wrapped at terminal width, so the wrapped remainder landed on
# its own line outside the comment. The result was two commands the gate executes.
#
# Why it passed silently. The gate runs `set -uo pipefail` -- no `-e`. A missing command
# returns 127 and execution continues, so the defect was invisible to `bash -n`
# (syntactically valid), to `--help`, and to a green run. Only reading the file or running
# with `set -x` would show it. The general hazard: a hard-wrapped paste can inject
# executable lines into a script and nothing in the existing toolchain notices.
#
# How it decides, so it does not become noise. A bare short line is legitimate in shell in
# exactly two ways, and both are enumerated per file rather than guessed:
#   1. it is a shell keyword or builtin (fi, done, else, esac, do, then, ...), or
#   2. it is a call to a function defined in that same file -- `purge` is called bare at
#      line 65 of container/astro/ondisk/polaris-autojoin.sh and defined at line 36.
# Anything else with that shape is reported.
#
# Scope: tracked files only, so build output under out/ cannot fail the gate. That matters
# concretely: out/ holds copies of these same scripts and would double every finding.
#
# Usage: test_shell_no_bare_fragments.sh [repo-root]

set -eu

ROOT=${1:-$(cd "$(dirname "$0")/.." && pwd)}
[ -d "$ROOT" ] || { echo "[bare-fragments] FAIL: no such root: $ROOT" >&2; exit 1; }

KEYWORDS=' fi done else esac do then echo wait set trap exit return break continue local export read shift unset eval exec cd true false test printf cat sync umask ulimit mount umount kill sleep '

FILELIST=$(mktemp "${TMPDIR:-/tmp}/bare-frags.XXXXXX")
trap 'rm -f "$FILELIST"' EXIT HUP INT TERM

if command -v git >/dev/null 2>&1 && git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    git -C "$ROOT" ls-files '*.sh' > "$FILELIST"
else
    find "$ROOT" -name '*.sh' -not -path '*/.git/*' -not -path "$ROOT/out/*" > "$FILELIST"
fi

checked=0
offenders=0

while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    f="$ROOT/$rel"
    [ -f "$f" ] || continue
    checked=$((checked+1))

    # Functions defined in this file may be called bare; that is normal shell.
    funcs=$(grep -oE '^[A-Za-z_][A-Za-z0-9_]*\(\)|^[[:space:]]*function [A-Za-z_][A-Za-z0-9_]*' "$f" 2>/dev/null \
            | sed -e 's/().*$//' -e 's/^[[:space:]]*function //' | sort -u)

    # Only lines that are *entirely* 1-5 lowercase letters can be a stray fragment.
    while IFS= read -r hit; do
        [ -n "$hit" ] || continue
        lineno=${hit%%:*}
        tok=${hit#*:}
        case "$KEYWORDS" in *" $tok "*) continue;; esac
        if printf '%s\n' "$funcs" | grep -qxF -- "$tok"; then continue; fi
        echo "[bare-fragments] STRAY: $rel:$lineno -> '$tok' executes as a command (not a keyword, not a function defined in this file)" >&2
        offenders=$((offenders+1))
    done <<EOF
$(grep -nE '^[a-z]{1,5}$' "$f" 2>/dev/null || true)
EOF
done < "$FILELIST"

if [ "$offenders" -gt 0 ]; then
    echo "[bare-fragments] FAIL: $offenders stray bare command line(s)." >&2
    echo "[bare-fragments] Usually the tail of a hard-wrapped comment paste. With 'set -uo pipefail' and no -e," >&2
    echo "[bare-fragments] these return 127 and the script carries on, so a green run proves nothing." >&2
    exit 1
fi

echo "[bare-fragments] PASS: no stray bare command lines in $checked tracked shell files"
