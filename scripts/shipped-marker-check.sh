#!/usr/bin/env bash
# shipped-marker-check.sh — prove a shipped libgphoto2 artifact actually contains the fixes
# its provenance claims.
#
# Why this exists: on 2026-11-05 the v95 candidate (astro-v95-k1ii-shutter-gate-20261104) passed
# every existing gate -- structural validation, install manifest, provenance registry hash, and
# "libgphoto2 capture contract" -- yet its shipped ptp2.so did not contain 4fba11d81, the #251
# deferred-Bulb-cancel fix that patcher#251 keeps open as safety-critical. Two separate blind spots:
#
#   1. The provenance registry hash verifies an artifact matches *itself*. It never asks whether the
#      artifact contains the code the pin is supposed to carry.
#   2. The driver contract test ran against whatever tree --libgphoto2-src pointed at (3fb26e536,
#      which had the fix) instead of the SHA the package was built from (855f718e, which does not).
#      At 855f718e the contract test itself lacks the assertion, so it would have passed vacuously.
#
# Reachability and ancestry prove nothing about *content*, and a green gate that tests the wrong tree
# proves less than nothing -- it proves the check was run.
#
# Method: take the shipped-code commits the baseline carries that the candidate does not (by patch-id,
# so a cherry-picked equivalent counts as carried). For each, derive a string literal the commit
# introduced that survives to the baseline tip. Release .so files are stripped, so symbols are useless
# and literals are the only handle. Then one loop yields both verdicts:
#
#   marker PRESENT in the candidate artifact  -> LEAK.    The build contains code its stated pin does
#                                                  not carry. Provenance and artifact disagree.
#   marker ABSENT from the candidate but PRESENT in [reference.so] -> MISSING. A correct build of the
#                                                  baseline does contain it, so its absence is a real
#                                                  regression, not a compilation artifact.
#   marker absent from both                   -> UNVERIFIABLE by literal. Reported, never guessed.
#
# The reference argument is what makes MISSING trustworthy. Whether a literal survives compilation
# depends on the macro used: GP_LOG_D text survives in these builds, ptp_debug text does not. Without
# a reference an absolute presence test reported 16 MISSING on v95 including commits that are provably
# ancestors of the built SHA, and it flagged 6aa3e4e66 whose literal the feature branch later reworded.
# Comparing against an artifact compiled the same way removes that entire class of noise. Without a
# reference, MISSING is skipped and reported as such -- never silently treated as clean.
#
# Usage: shipped-marker-check.sh <ptp2.so> <libgphoto2-src> <built-sha> <baseline-sha> [reference.so]
#
# Exit 0 only if neither LEAK nor MISSING fires.
set -uo pipefail

SO="${1:?usage: $0 <ptp2.so> <libgphoto2-src> <built-sha> <baseline-sha> [reference.so]}"
L="${2:?libgphoto2 source checkout}"
BUILT="${3:?sha the package was built from}"
BASE="${4:?baseline pin the candidate must carry}"
REF="${5:-}"

[ -f "$SO" ] || { echo "ERROR: no such artifact: $SO"; exit 1; }
git -C "$L" cat-file -e "${BUILT}^{commit}" 2>/dev/null || { echo "ERROR: $BUILT not in $L"; exit 1; }
git -C "$L" cat-file -e "${BASE}^{commit}" 2>/dev/null || { echo "ERROR: $BASE not in $L"; exit 1; }

# Scope every pathspec to the sources that actually compile into THIS artifact. A camlib .so contains
# only its own directory: markers from camlibs/pentax or libgphoto2 core are absent from ptp2.so for
# reasons unrelated to any fix, and testing them produced 18 false MISSING results on a correct v94
# build. Derive the scope from the artifact name rather than assuming it.
BASE_NAME=$(basename "$SO")
case "$BASE_NAME" in
        libgphoto2.so) PATHSPEC="libgphoto2 include" ;;
        *.so)          CAMLIB="${BASE_NAME%.so}"; PATHSPEC="camlibs/$CAMLIB" ;;
        *)             echo "ERROR: unrecognized artifact name '$BASE_NAME' (expected <camlib>.so or libgphoto2.so)"; exit 1 ;;
esac

echo "artifact : $SO"
echo "built    : $BUILT"
echo "baseline : $BASE"
echo "scope    : $PATHSPEC  (derived from $BASE_NAME)"
echo

# Release builds keep GP_LOG_D text; a build with logging compiled out has no pentax-bulb literals at
# all, and then every marker test would report "absent" for reasons unrelated to the fix. Detect that
# up front so an unassessable artifact is never mistaken for a clean one.
#
# NB: never use `grep -q` downstream of another command in this script. It exits on first match, the
# upstream command takes SIGPIPE, and under pipefail the pipeline returns 141 -- which reads as "no
# match" even when the literal is present. That exact bug made this script report INCONCLUSIVE against
# a real v95 ptp2.so that demonstrably contains ten pentax-bulb literals. Count instead.
if [ "$(strings "$SO" | grep -c 'pentax-bulb:')" -eq 0 ]; then
        echo "RESULT: INCONCLUSIVE -- artifact carries no pentax-bulb log literals at all."
        echo "        Debug logging appears compiled out, so string markers cannot discriminate."
        echo "        Do not treat this as a pass. Re-check against a release build that keeps GP_LOG_D."
        exit 1
fi

# Shipped-code commits in the baseline that the candidate does not carry, by patch-id (exact content).
# patch-id misses rewritten commits, which is why each survivor then gets a content test below. The
# built-side set is materialised once: recomputing it per commit is O(n^2), and piping awk into
# `grep -q` would short-circuit and fail the pipeline under pipefail in the same way as above.
TMPD=$(mktemp -d); trap 'rm -rf "$TMPD"' EXIT
git -C "$L" log -p --format="%H" "$BUILT" -- $PATHSPEC 2>/dev/null |
        git -C "$L" patch-id --stable 2>/dev/null | awk '{print $1}' | sort -u > "$TMPD/built.pids"
mapfile -t missing < <(
        git -C "$L" log --format="%H" "$BASE" --not "$BUILT" -- $PATHSPEC 2>/dev/null |
        while read -r c; do
                pid=$(git -C "$L" show -p --format="%H" "$c" -- $PATHSPEC 2>/dev/null | git -C "$L" patch-id --stable 2>/dev/null | awk '{print $1}')
                [ -n "$pid" ] || continue
                if ! grep -cx "$pid" "$TMPD/built.pids" >/dev/null; then
                        echo "$c"
                fi
        done
)

if [ "${#missing[@]}" -eq 0 ]; then
        echo "no shipped-code commits missing from the candidate"
        echo "RESULT: PASS -- nothing to verify"
        exit 0
fi

echo "shipped-code commits in baseline but not carried by the candidate: ${#missing[@]}"

have_ref=0
if [ -n "$REF" ] && [ -f "$REF" ]; then
        if [ "$BASE_NAME" = "$(basename "$REF")" ]; then
                have_ref=1
                echo "reference: $REF"
        else
                echo "reference: IGNORED -- $(basename "$REF") is not the same component as $BASE_NAME"
        fi
else
        echo "reference: none supplied -- MISSING cannot be evaluated, only LEAK"
fi
echo

leak=0; missing_fix=0; unverifiable=0
for c in "${missing[@]}"; do
        p=$(git -C "$L" rev-parse "$c^")
        # A literal this commit introduced that still exists at the baseline tip. Two conditions, and
        # dropping either produced a distinct bug:
        #   * not excluding the parent tree flagged 8f5789f0a on "PENTAX K-3 Mark III Monochrome", a
        #     literal the feature branch added independently, so it is in 855f718e too and finding it
        #     in the .so proves nothing about that commit;
        #   * not requiring survival at BASE flagged commits whose literal a later baseline commit
        #     reworded, e.g. 6aa3e4e66's "expected=0x%04x, actual=0x%04x".
        marker=""
        while read -r s; do
                [ -z "$s" ] && continue
                git -C "$L" grep -cF -- "$s" "$p" -- $PATHSPEC >/dev/null 2>&1 && continue
                git -C "$L" grep -cF -- "$s" "$BASE" -- $PATHSPEC >/dev/null 2>&1 || continue
                marker="$s"; break
        done < <(git -C "$L" show --format="" "$c" -- $PATHSPEC |
                        grep -oE '"[A-Za-z][^"\\]{18,60}"' | tr -d '"' | sort -u)

        short="${c:0:9}"; subj=$(git -C "$L" log -1 --format='%s' "$c" | cut -c1-46)
        if [ -z "$marker" ]; then
                printf "  %-10s %-48s UNVERIFIABLE (no literal introduced that survives to the pin)\n" "$short" "$subj"
                unverifiable=$((unverifiable+1))
                continue
        fi

        hit=$(strings "$SO" | grep -cF -- "${marker:0:60}")
        if [ "$hit" -gt 0 ]; then
                # Present in the artifact. That is only a leak if the built tree does not contain the
                # literal by some other route. 8f5789f0a's "PENTAX K-3 Mark III Monochrome" is new
                # relative to its own parent and survives to the pin, but the feature branch added the
                # same string independently, so it is in 855f718e too -- finding it in ptp2.so says
                # nothing about whether this commit was applied.
                if git -C "$L" grep -cF -- "$marker" "$BUILT" -- $PATHSPEC >/dev/null 2>&1; then
                        printf "  %-10s %-48s INCONCLUSIVE (literal also in the built tree by another path)\n" "$short" "$subj"
                        unverifiable=$((unverifiable+1))
                else
                        printf "  %-10s %-48s LEAK -- code present although commit is not\n" "$short" "$subj"
                        echo "             marker: ${marker:0:70}"
                        leak=1
                fi
                continue
        fi

        if [ "$have_ref" -eq 1 ]; then
                if [ "$(strings "$REF" | grep -cF -- "${marker:0:60}")" -gt 0 ]; then
                        printf "  %-10s %-48s MISSING -- present in reference, absent here\n" "$short" "$subj"
                        echo "             marker: ${marker:0:70}"
                        missing_fix=1
                        continue
                fi
        fi
        printf "  %-10s %-48s absent (consistent with the pin)\n" "$short" "$subj"
done

echo
if [ "$leak" -ne 0 ]; then
        echo "RESULT: FAIL (LEAK) -- the artifact contains code the claimed pin does not carry."
        echo "        The build and its provenance disagree; do not ship this package."
        exit 1
fi
if [ "$missing_fix" -ne 0 ]; then
        echo "RESULT: FAIL (MISSING) -- the artifact lacks fixes the baseline pin carries."
        echo "        This is the v95 signature: provenance is accurate, the pin is regressed."
        echo "        Do not describe this release as carrying the baseline."
        exit 1
fi
if [ "$have_ref" -eq 0 ]; then
        echo "RESULT: INCONCLUSIVE -- no LEAK found, but MISSING could not be evaluated without a"
        echo "        reference artifact known to carry the baseline. Agreement with a regressed pin is"
        echo "        exactly the v95 failure, so this is not a pass. Supply the shipped v94 ptp2.so."
        exit 1
fi
echo "RESULT: PASS -- no leaked code and no baseline fix missing from the artifact"
[ "$unverifiable" -gt 0 ] && echo "NOTE: $unverifiable commit(s) added no surviving literal and remain unchecked by this method."
exit 0
