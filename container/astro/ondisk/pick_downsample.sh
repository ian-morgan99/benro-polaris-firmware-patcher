# ============================================================================
#  pick_downsample.sh -- one downsample policy for every solve path.
#
#  SOURCED ONLY. Deliberately has no shebang: it defines a function and has no
#  main body, so executing it would do nothing. tests/
#  test_verify_published_candidate.py treats a shebangless .sh in ondisk/ as
#  sourced-only and exempt from the exec bit, which is exactly what this is.
#
#      . "$ASTRO/pick_downsample.sh"
#      DS=$(pick_downsample "$FRAME")
#
#  Why this exists (#341). polaris-align.sh defaulted DOWNSAMPLE to the literal
#  4, which is chosen for an ~6000 px camera frame. The WebUI upload path passes
#  no DOWNSAMPLE at all, so a phone-downscaled upload was decoded at 1/4 whatever
#  its real size: a 1920x1280 JPEG becomes 480x320 and yields single-digit stars,
#  which no triangle solver can match against an all-sky index. It reports
#  "search_exhausted", which reads like missing index files but is not.
#  polaris-autosolve.sh already had the size-aware rule; this lifts it out so the
#  two cannot drift apart again.
#
#  Cost, and why it is acceptable here: reading the dimensions needs one decode
#  pass at --downsample 8. autosolve already pays that because it wants the frame
#  dimensions for its own log line regardless. In align this runs only when
#  DOWNSAMPLE is unset -- i.e. the upload/manual path, which is the broken one --
#  because autosolve passes DOWNSAMPLE explicitly on every capture call. A full
#  capture therefore still pays nothing extra.
#
#  Side effect: if FRAME_DIMS_FILE is set and non-empty, "W x H" is written there
#  while we are already reading the file. That preserves what autosolve used to do
#  inline; callers that do not care simply leave it unset.
# ============================================================================

pick_downsample() {
    # ${1:-} and the :- guards below matter: polaris-autosolve.sh runs with set -u,
    # so an unset variable here would abort the whole capture loop.
    _img="${1:-}"
    _dims=""
    if [ -x "$ASTRO/polaris-extract" ] && [ -f "$_img" ]; then
        _dims=$("$ASTRO/polaris-extract" --jpeg "$_img" --downsample 8 2>/dev/null \
                | sed -n 's/^# full resolution *\([0-9][0-9]*\) *x *\([0-9][0-9]*\).*/\1 x \2/p')
    fi
    if [ -n "${FRAME_DIMS_FILE:-}" ]; then
        printf '%s' "$_dims" > "$FRAME_DIMS_FILE" 2>/dev/null || :
    fi
    _w=$(echo "$_dims" | sed -n 's/^\([0-9]*\) .*/\1/p')
    # Unknown size: keep the historical default rather than guessing small, which
    # would decode a large frame at full resolution and stall the capture loop.
    [ -n "$_w" ] || { echo 4; return; }
    if   [ "$_w" -ge "${DS_LARGE_MIN:-6000}" ]; then echo 4
    elif [ "$_w" -ge "${DS_MEDIUM_MIN:-3000}" ]; then echo 2
    else                                              echo 1
    fi
}
