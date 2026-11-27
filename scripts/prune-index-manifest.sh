#!/usr/bin/env bash
# prune-index-manifest.sh — reduce astrometry/.md5sums.txt to files actually shipped.
#
# Upstream's md5sums.txt covers the whole 4100 series (4107..4119). fetch-indexes.sh
# copies it verbatim, but we ship only the subset that overlaps the configured focal
# range (ten files, 4110..4119). So the copied manifest names three index files that
# are deliberately absent.
#
# On the device `md5sum -c .md5sums.txt` then reports, for each absent file:
#     md5sum: can't open 'index-4107.fits': No such file or directory
#     index-4107.fits: FAILED
# Those phantom failures read exactly like corruption on a healthy card. On 2026-11-26
# a genuinely truncated index-4110.fits sat in that same directory and the real failure
# was nearly missed while time went into chasing the phantoms. A check whose PASS is
# unreachable cannot report a real problem, so we prune to files actually present:
# PASS means verified, FAIL means a real problem, and nothing is reported for what we
# never shipped.
#
# This MUST run before ASTRO-MANIFEST.sha256 is generated. It previously ran inside the
# archive step, after that manifest had already been hashed, so the digest recorded the
# unpruned file while the tree shipped the pruned one. The kit installer verifies the
# staged tree against that manifest and therefore refused every v119 candidate with
# "./astrometry/.md5sums.txt: FAILED ... 1 of 726 computed checksums did NOT match" —
# a packaging ordering bug, not transfer corruption.
#
# Usage: prune-index-manifest.sh <SD_ROOT>
#   where <SD_ROOT>/astrometry/.md5sums.txt is the manifest to prune in place.
# Exits 0 with no change if there is no astrometry tree or no manifest; exits 1 loudly
# if a manifest exists but matches no shipped index file (fail closed, never ship an
# empty manifest).

set -euo pipefail

SD_ROOT="${1:-}"
[ -n "$SD_ROOT" ] || { echo "usage: $0 <SD_ROOT>" >&2; exit 2; }
[ -d "$SD_ROOT" ] || { echo "ERROR: SD_ROOT not a directory: $SD_ROOT" >&2; exit 2; }

cd "$SD_ROOT"
[ -f astrometry/.md5sums.txt ] || exit 0

tmp_md5=$(mktemp) || exit 1
while read -r sum name; do
    [ -n "$name" ] || continue
    f=${name#\*}
    [ -f "astrometry/$f" ] && printf '%s *%s\n' "$sum" "$f" >> "$tmp_md5"
done < astrometry/.md5sums.txt

if [ -s "$tmp_md5" ]; then
    mv "$tmp_md5" astrometry/.md5sums.txt || exit 1
else
    rm -f "$tmp_md5"
    echo "ERROR: astrometry/.md5sums.txt matched no shipped index files" >&2
    exit 1
fi
