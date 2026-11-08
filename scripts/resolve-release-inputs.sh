#!/usr/bin/env bash
# resolve-release-inputs.sh — print the stock FwPkt and libgphoto2-main paths a
# release build needs, or say exactly why it could not find one.
#
# WHY THIS EXISTS. Across several sessions I asserted "the stock firmware is not
# present" and "there is no clean libgphoto2 checkout", and treated the firmware
# release as blocked. Both claims were false, every time. The inputs have always
# been on disk:
#
#   stock FwPkt        PrivateResearch/firmware-packets/4.0.0.32--stock/FwPkt.zip
#   libgphoto2 main    LibGphoto2-v86-main  (branch main, clean)
#
# The claims came from searching the wrong tree by the wrong name: globbing for
# "*FwPkt*" or "firmwareInfo" under $HOME at shallow depth, and running
# `git rev-parse` in the workspace root directory named LibGphoto2, which is NOT
# a git repository. A failed lookup was then reported as a missing input. That is
# a search bug wearing the costume of a blocker, and it cost multiple sessions of
# "blocked, need the firmware" back-and-forth.
#
# So: never conclude an input is absent from a glob you chose yourself. Run this.
# It searches the known locations first, then falls back to a filesystem-wide
# search, and distinguishes "not found" from "found but unusable" (dirty, wrong
# branch, no FwPkt.zip in the packet directory) -- and prints every rejection
# under --verbose so a near-miss is visible instead of silent.
#
# Two subtleties this script had to get right, both learned by getting them wrong:
#
#   * `.git` is not always a directory. LibGphoto2-v86-main is a LINKED WORKTREE,
#     so its .git is a one-line file ("gitdir: ..."). A `[ -d "$d/.git" ]` test
#     rejects it, and also rejects any subdirectory of a repository. Ask git
#     instead (--is-inside-work-tree) and resolve to the work-tree root, because
#     build-release-candidate.sh wants the source root, not an arbitrary subdir.
#   * Two stock packets exist with identical FwPkt.zip md5 (4.0.0.32--stock and
#     4.0.0.32--stock-reference). A naive reverse sort picks "-reference". Prefer
#     the exact "--stock" name so the canonical packet is what gets reported.
#
# Usage:
#   scripts/resolve-release-inputs.sh              # print both paths
#   scripts/resolve-release-inputs.sh --shell      # eval-able assignments
#   scripts/resolve-release-inputs.sh --verbose    # show what was rejected and why
#
# Exit 0 only when BOTH inputs resolved to usable paths. Never exits 0 with an
# empty path, so a caller cannot accidentally pass "" to the release script.
set -uo pipefail

SHELL_OUT=0
VERBOSE=0
for a in "$@"; do
  case "$a" in
    --shell)   SHELL_OUT=1 ;;
    --verbose) VERBOSE=1 ;;
    -h|--help) sed -n '2,36p' "$0"; exit 0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

note() { [ "$VERBOSE" = "1" ] && echo "  [$1] $2" >&2 || true; }

RESEARCH="${POLARIS_RESEARCH:-$HOME/Documents/VSCodeProjects/PrivateResearch}"
PROJECTS="${POLARIS_PROJECTS:-$HOME/Documents/VSCodeProjects}"

STOCK_ROOTS=(
  "$RESEARCH/firmware-packets"
  "$PROJECTS/PrivateResearch/firmware-packets"
  "$HOME/polaris-build-73"
  "$HOME/in"
)

# A stock packet is a directory holding FwPkt.zip (ideally with
# firmwareInfo.stock.txt beside it), or a bare FwPkt.zip. build-release-
# candidate.sh accepts either form; it forwards it as --fwpkt/--stock.
find_stock() {
  local root cand
  for root in "${STOCK_ROOTS[@]}"; do
    [ -d "$root" ] || { note skip "no such root: $root"; continue; }
    # Canonical packet first: a directory whose name ends in exactly "--stock".
    cand=$(find "$root" -maxdepth 1 -type d -name '*--stock' -print 2>/dev/null | sort | head -1)
    if [ -n "$cand" ] && [ -f "$cand/FwPkt.zip" ]; then
      if [ -f "$cand/firmwareInfo.stock.txt" ]; then
        note ok "canonical stock packet with firmwareInfo: $cand"
      else
        note ok "canonical stock packet (no firmwareInfo beside it): $cand"
      fi
      printf '%s\n' "$cand"; return 0
    fi
    # Then any other stock-labelled packet.
    while IFS= read -r cand; do
      if [ -f "$cand/FwPkt.zip" ]; then
        note ok "stock-labelled packet: $cand"
        printf '%s\n' "$cand"; return 0
      fi
      note reject "no FwPkt.zip inside: $cand"
    done < <(find "$root" -maxdepth 1 -type d -name '*stock*' ! -name '*--stock' 2>/dev/null | sort)
    # Then any packet directory containing a zip, newest first.
    while IFS= read -r cand; do
      [ -f "$cand/FwPkt.zip" ] && { note ok "packet dir: $cand"; printf '%s\n' "$cand"; return 0; }
    done < <(find "$root" -maxdepth 1 -type d 2>/dev/null | sort -r)
    # Last, a loose zip.
    cand=$(find "$root" -maxdepth 2 -name 'FwPkt*.zip' -print -quit 2>/dev/null)
    [ -n "$cand" ] && { note ok "loose zip: $cand"; printf '%s\n' "$cand"; return 0; }
  done
  # Filesystem-wide fallback. Slow, but it is the difference between "absent" and
  # "I looked in one place".
  local hit
  hit=$(find "$HOME" -maxdepth 7 -name 'FwPkt.zip' -print -quit 2>/dev/null)
  if [ -n "$hit" ]; then
    note ok "found by filesystem search: $hit"
    printf '%s\n' "$(dirname "$hit")"; return 0
  fi
  return 1
}

# libgphoto2 must be a real git work tree, on main, clean, and the path returned
# must be the source root (the one holding meson.build / configure.ac), because
# that is what build-release-candidate.sh runs meson against.
#
# It does NOT pick one when several qualify. Two clean main trees exist here in
# DIFFERENT repositories -- LibGphoto2-v86-clone has its own .git, while
# LibGphoto2-v86-main is a linked worktree of LibGphoto2/libgphoto2 -- so their
# origin/main refs are independent and "behind 0" versus "behind 32" is not
# comparable across them. Sorting by commit date or behind-count would silently
# bind a release version to whichever tree happened to sort first, which is the
# exact failure this script exists to prevent: a version must describe one known
# commit set. So every candidate is printed with its sha/date/behind and the
# caller chooses with POLARIS_LIBGPHOTO2.
usable_libgphoto2() {
  local d top br dirty dirs
  # Materialise the directory list first. git reads stdin in some invocations, so
  # a "while read" fed by a process substitution lets git swallow the entries that
  # have not been read yet. With first-match-wins that was invisible; once the whole
  # list is consumed it silently yields ZERO candidates, which then falls through to
  # the filesystem-wide find over $HOME -- and that is what hung for minutes.
  # </dev/null on each git call makes this immune regardless of how git behaves.
  dirs=$(find "$PROJECTS" -maxdepth 3 -type d -name 'libgphoto2*' 2>/dev/null | sort)
  while IFS= read -r d; do
    [ -n "$d" ] || continue
    # Ask git rather than testing for .git: it may be a file (linked worktree)
    # or absent entirely (the directory is inside a repo rooted elsewhere).
    if ! git -C "$d" rev-parse --is-inside-work-tree </dev/null >/dev/null 2>&1; then
      note reject "not inside any git work tree: $d"; continue
    fi
    top=$(git -C "$d" rev-parse --show-toplevel </dev/null 2>/dev/null)
    [ -n "$top" ] || { note reject "no work-tree root: $d"; continue; }
    if [ ! -f "$top/meson.build" ] && [ ! -f "$top/configure.ac" ]; then
      note reject "work-tree root is not a libgphoto2 source root: $top"; continue
    fi
    br=$(git -C "$top" branch --show-current </dev/null 2>/dev/null)
    dirty=$(git -C "$top" status --porcelain </dev/null 2>/dev/null | wc -l | tr -d ' ')
    if [ "$br" != "main" ]; then note reject "on '$br' not main: $top"; continue; fi
    if [ "$dirty" != "0" ]; then note reject "dirty ($dirty paths): $top"; continue; fi
    printf '%s\n' "$top"
  # sort -u is required, not cosmetic: find matches several subdirectories that
  # all resolve to the SAME work-tree root (LibGphoto2-v86-main/libgphoto2 and
  # its build/ subdirs each --show-toplevel to the same place). Without it one
  # checkout counted three times and was printed three times, which both faked
  # an ambiguity error and made the candidate list lie about how many trees exist.
  done <<< "$dirs" | sort -u
}

find_libgphoto2() {
  # An explicit override wins, but is still validated rather than trusted.
  if [ -n "${POLARIS_LIBGPHOTO2:-}" ]; then
    local p="$POLARIS_LIBGPHOTO2" br dirty
    if ! git -C "$p" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      echo "ERROR: POLARIS_LIBGPHOTO2='$p' is not inside a git work tree" >&2; return 1
    fi
    p=$(git -C "$p" rev-parse --show-toplevel)
    br=$(git -C "$p" branch --show-current 2>/dev/null)
    dirty=$(git -C "$p" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    [ "$br" = "main" ] || { echo "ERROR: POLARIS_LIBGPHOTO2='$p' is on '$br', not main" >&2; return 1; }
    [ "$dirty" = "0" ] || { echo "ERROR: POLARIS_LIBGPHOTO2='$p' is dirty ($dirty paths)" >&2; return 1; }
    note ok "explicit override: $p"
    printf '%s\n' "$p"; return 0
  fi

  # Compute the list ONCE. Running usable_libgphoto2 twice re-walks the tree, and
  # invoking git inside "while read" over a process substitution lets git consume
  # the loop's stdin -- which made this hang until timeout. A variable plus a
  # here-string avoids both.
  local list n=0 first=""
  list=$(usable_libgphoto2)
  while IFS= read -r top; do
    [ -z "$top" ] && continue
    n=$((n + 1))
    [ -z "$first" ] && first="$top"
  done <<< "$list"

  if [ "$n" = "1" ]; then
    note ok "single usable candidate"
    printf '%s\n' "$first"; return 0
  fi
  if [ "$n" -gt 1 ]; then
    echo "ERROR: $n clean libgphoto2 checkouts on main -- refusing to guess." >&2
    echo "       A release version is bound to one exact commit set, so picking" >&2
    echo "       the wrong tree silently produces a version that describes" >&2
    echo "       commits that were not built. Choose with POLARIS_LIBGPHOTO2=<path>." >&2
    echo "" >&2
    while IFS= read -r top; do
      [ -z "$top" ] && continue
      printf '  %-58s %s  behind-origin/main=%s\n' \
        "$top" \
        "$(git -C "$top" log -1 --format='%h %ci' </dev/null 2>/dev/null | cut -d' ' -f1-2)" \
        "$(git -C "$top" rev-list --count HEAD..origin/main </dev/null 2>/dev/null || echo '?')" >&2
    done <<< "$list"
    echo "" >&2
    echo "       Note: 'behind' counts against each tree's OWN origin/main, and" >&2
    echo "       these trees are in different repositories, so the numbers are not" >&2
    echo "       comparable to each other." >&2
    # 2, not 1: ambiguity already produced a specific, actionable message. The
    # caller must not append its generic "nothing found" text on top of it, which
    # would tell the reader to go searching when the real problem is that there
    # are too many matches and one must be chosen.
    return 2
  fi

  # Filesystem-wide fallback for the same reason as the stock search.
  local hit
  hit=$(find "$HOME" -maxdepth 7 -type f -name meson.build -path '*libgphoto2*' -print -quit 2>/dev/null)
  if [ -n "$hit" ]; then
    top=$(dirname "$hit")
    if git -C "$top" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      top=$(git -C "$top" rev-parse --show-toplevel)
      br=$(git -C "$top" branch --show-current 2>/dev/null)
      dirty=$(git -C "$top" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
      if [ "$br" = "main" ] && [ "$dirty" = "0" ]; then
        note ok "found by filesystem search: $top"
        printf '%s\n' "$top"; return 0
      fi
      note reject "filesystem hit unusable (branch '$br', dirty $dirty): $top"
    fi
  fi
  return 1
}

STOCK=$(find_stock)
SRC=$(find_libgphoto2); SRC_RC=$?

ok=1
[ -n "$STOCK" ] || { echo "ERROR: no stock FwPkt found." >&2
  echo "       Searched: ${STOCK_ROOTS[*]}" >&2
  echo "       plus a filesystem-wide find for FwPkt.zip under \$HOME." >&2
  echo "       Expected shape: <research>/firmware-packets/<ver>--stock/FwPkt.zip" >&2
  ok=0; }
# rc=2 means ambiguity, which already printed its own candidate list; do not
# follow it with "nothing found", which contradicts it.
[ "$SRC_RC" = "2" ] && ok=0
[ -z "$SRC" ] && [ "$SRC_RC" != "2" ] && { echo "ERROR: no clean libgphoto2 checkout on main found." >&2
  echo "       Searched: $PROJECTS/libgphoto2* and a filesystem-wide find." >&2
  echo "       Note the workspace root 'LibGphoto2' is NOT a git repository, and" >&2
  echo "       'LibGphoto2-v86-main' is a LINKED WORKTREE whose .git is a file --" >&2
  echo "       this script asks git rather than testing for a .git directory." >&2
  ok=0; }
[ "$ok" = "1" ] || exit 1

if [ "$SHELL_OUT" = "1" ]; then
  printf 'POLARIS_STOCK_FWPKT=%q\n' "$STOCK"
  printf 'POLARIS_LIBGPHOTO2=%q\n' "$SRC"
else
  echo "stock_fwpkt=$STOCK"
  echo "libgphoto2=$SRC"
fi
