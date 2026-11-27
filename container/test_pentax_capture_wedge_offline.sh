#!/bin/bash
# Offline reproduction of the K-1 II capture wedge, using the real admission logic.
#
# Why this exists: the wedge (docs/evidence/capture-wedge-unsafe-activity-20261126)
# currently requires hardware plus a reboot to even observe. A failed timed bulb latches
# params->pentax.capture_output_pending, and every later capture is refused with
# GP_ERROR_CAMERA_BUSY because pentax_admission_apply_output_obligation() only releases
# the latch when the camera reports PENTAX_ADMISSION_BLOCK_NONE. The K-1 II reports
# field104=0x0000000e, whose PROCESSING bit is inside PENTAX_CONDITION_ACTIVITY_UNSAFE,
# so the strict reason is UNSAFE_ACTIVITY forever and the release condition can never be
# satisfied. Killing pgphoto does not help either -- it breaks the app<->pgphoto IPC link,
# so capture then fails from polestar_app with state:-1. Reboot is the only exit.
#
# The logic under test lives in the libgphoto2 fork, which needs a full autotools
# configure to build (config.h, generated gphoto2-endian.h). These four functions have no
# dependency on any of that, so they are extracted verbatim and compiled standalone --
# same approach as container/test_stage2_init_trace.sh. If the extraction finds nothing
# the test fails loudly rather than passing vacuously.
set -eu

dir="$(cd "$(dirname "$0")" && pwd)"
cc="${CC:-gcc}"
command -v "$cc" >/dev/null 2>&1 || { echo "SKIP: no C compiler" >&2; exit 77; }

# Locate the fork. LGP_SRC overrides; otherwise try the checkouts this project uses.
LGP="${LGP_SRC:-}"
if [ -z "$LGP" ]; then
    for c in "$HOME/lgp-v117-src" "$HOME/libgphoto2-v101-src"; do
        [ -f "$c/camlibs/ptp2/pentax-utils.c" ] && LGP="$c" && break
    done
fi
[ -n "$LGP" ] || { echo "SKIP: libgphoto2 fork not found (set LGP_SRC)" >&2; exit 77; }
UTILS="$LGP/camlibs/ptp2/pentax-utils.c"
HDR="$LGP/camlibs/ptp2/pentax-utils.h"
[ -f "$UTILS" ] && [ -f "$HDR" ] || { echo "SKIP: $UTILS not found" >&2; exit 77; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT HUP INT TERM

# --- extract the logic under test, verbatim ------------------------------------------
extract() {   # extract() <function-name> <out-file>
    # pentax-utils.c puts the return type on its own line (K&R style):
    #
    #     const char *
    #     pentax_admission_block_reason_name (...)
    #     {
    # Starting at the name alone therefore yields a body with no signature, which
    # compiles as an implicit int and turns every `return "..."` into a pointer-to-int
    # error under -Werror. Carry the preceding line when it is a type rather than the
    # tail of a statement or a comment.
    awk -v fn="$1" '
        $0 ~ "^"fn" \\(" && !p {
            if (prev != "" && prev !~ /[{};]$/ && prev !~ /^[[:space:]]*\*/)
                print prev
            p = 1
        }
        { prev = $0 }
        p { print }
        p && /^}$/ { exit }
    ' "$UTILS" >> "$2"
}
: > "$work/extracted.inc"
for f in pentax_get_u32le pentax_admission_block_reason \
         pentax_output_obligation_releasable pentax_admission_block_reason_name \
         pentax_orphan_candidate_claimable; do
    extract "$f" "$work/extracted.inc"
done
for f in pentax_get_u32le pentax_admission_block_reason pentax_output_obligation_releasable \
         pentax_orphan_candidate_claimable; do
    grep -q "^$f (" "$work/extracted.inc" || {
        echo "FAIL: could not extract $f from $UTILS" >&2
        echo "      it was renamed or its shape changed; update this test deliberately." >&2
        exit 1
    }
done

# Pull the real bit definitions and enums rather than restating them, so a change to the
# unsafe mask is reflected here automatically.
awk '/^#define PENTAX_CONDITION_ACTIVITY_SHOOTING/,/PENTAX_CONDITION_ACTIVITY_SELF_TIMER\)/' \
    "$HDR" > "$work/bits.inc"
grep -q "PENTAX_CONDITION_ACTIVITY_UNSAFE" "$work/bits.inc" || {
    echo "FAIL: could not extract PENTAX_CONDITION_ACTIVITY_UNSAFE from $HDR" >&2; exit 1; }

cat > "$work/harness.c" <<'EOF'
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

typedef enum { PENTAX_ADMISSION_STRICT = 0, PENTAX_ADMISSION_OUTPUT_SAFE = 1 } PentaxAdmissionPolicy;
typedef enum {
    PENTAX_ADMISSION_BLOCK_NONE = 0,
    PENTAX_ADMISSION_BLOCK_UNREADABLE,
    PENTAX_ADMISSION_BLOCK_UNSAFE_ACTIVITY,
    PENTAX_ADMISSION_BLOCK_TRANSFER_CANDIDATE_AVAILABLE,
    PENTAX_ADMISSION_BLOCK_SELECTOR_PRESENT,
    PENTAX_ADMISSION_BLOCK_OUTPUT_UNRESOLVED
} PentaxAdmissionBlockReason;

#include "bits.inc"
#include "extracted.inc"

#define MIN_SIZE 508
static int failures;
static void check(int cond, const char *what) {
    if (!cond) { printf("FAIL: %s\n", what); failures++; }
    else       { printf("ok:   %s\n", what); }
}

/* Build a conditions payload with the three fields admission reads. The buffer is static
 * so callers may keep the pointer; each call rewrites it in place. */
static unsigned char *frame(uint32_t capture32, uint32_t candidate36, uint32_t activity104) {
    static unsigned char buf[MIN_SIZE + 8];
    memset(buf, 0, sizeof buf);
    buf[32] = capture32 & 0xff;        buf[33] = (capture32 >> 8)  & 0xff;
    buf[34] = (capture32 >> 16) & 0xff; buf[35] = (capture32 >> 24) & 0xff;
    buf[36] = candidate36 & 0xff;      buf[37] = (candidate36 >> 8) & 0xff;
    buf[38] = (candidate36 >> 16) & 0xff; buf[39] = (candidate36 >> 24) & 0xff;
    buf[104] = activity104 & 0xff;     buf[105] = (activity104 >> 8) & 0xff;
    buf[106] = (activity104 >> 16) & 0xff; buf[107] = (activity104 >> 24) & 0xff;
    return buf;
}

int main(void) {
    printf("PENTAX_CONDITION_ACTIVITY_UNSAFE = 0x%08x\n", PENTAX_CONDITION_ACTIVITY_UNSAFE);

    /* The mask must match what the device prints. Clog_000038 on the K-1 II rig and
     * o-v13v both report unsafe-mask=0x00109a03; if this diverges, the header and the
     * field the camera sends no longer describe the same thing. */
    check(PENTAX_CONDITION_ACTIVITY_UNSAFE == 0x00109a03u,
          "unsafe mask equals the value logged by the device (0x00109a03)");

    /* The wedge as actually recorded. Clog_000038 on the K-1 II rig, captures 4..7, all
     * identical: field32=0x00000001 field36=0x00000001 field104=0x0000000e. So the body
     * is reporting an active capture AND a candidate handle on itself AND PROCESSING.
     * This is not a stale flag -- there really is an undownloaded object (the SP_0047.jpg
     * that the failed timed bulb wrote but never delivered). */
    PentaxAdmissionBlockReason wedged =
        pentax_admission_block_reason(frame(1, 1, 0x0000000eu), MIN_SIZE, PENTAX_ADMISSION_STRICT);
    PentaxAdmissionBlockReason wedged_safe =
        pentax_admission_block_reason(frame(1, 1, 0x0000000eu), MIN_SIZE, PENTAX_ADMISSION_OUTPUT_SAFE);

    check(wedged == PENTAX_ADMISSION_BLOCK_UNSAFE_ACTIVITY,
          "strict policy refuses the recorded wedge state as unsafe-activity");
    /* Clog prints output-safe-reason=transfer-candidate-available for the same frame, so
     * the two policies disagree about the same payload. That disagreement is where any
     * recovery has to come from. */
    check(wedged_safe == PENTAX_ADMISSION_BLOCK_TRANSFER_CANDIDATE_AVAILABLE,
          "output-safe policy sees transfer-candidate-available on the same frame (as logged)");

    /* The refusing bit is PROCESSING (0x2), which is inside the unsafe mask. Bits 2-3 of
     * 0x0e (0x0c) are not named by any constant in pentax-utils.h, so they cannot be the
     * cause -- nothing tests them. */
    check((0x0000000eu & PENTAX_CONDITION_ACTIVITY_UNSAFE) == 0x00000002u,
          "the refusing bit in 0x0e is PROCESSING (0x2), not an undefined bit");

    /* The dead end. With the latch set and the camera in this state the obligation cannot
     * be released: pentax_output_obligation_releasable requires reason == NONE, and the
     * strict reason is UNSAFE_ACTIVITY for as long as PROCESSING is reported. Reboot is
     * the only exit observed. */
    check(!pentax_output_obligation_releasable(wedged, 0, 1, 1),
          "latched obligation is NOT releasable in the recorded wedge state");

    /* Contrast that proves the state is not permanent: the same latch does release once
     * the body reports a fully idle frame. A bounded wait for that reading is therefore a
     * legitimate escape path -- but note it requires the candidate to be gone too, so it
     * cannot clear a body that genuinely still owes an object. */
    PentaxAdmissionBlockReason idle =
        pentax_admission_block_reason(frame(0, 0, 0x00000000u), MIN_SIZE, PENTAX_ADMISSION_STRICT);
    check(idle == PENTAX_ADMISSION_BLOCK_NONE,
          "field32=0 field36=0 field104=0 admits (the camera CAN report idle)");
    check(pentax_output_obligation_releasable(idle, 0, 0, 0),
          "latched obligation IS releasable on a fully idle frame");

    /* Guards any future fix: an object still on the body must never be silently forgotten,
     * and a capture we are still serving owns whatever the camera owes. */
    check(!pentax_output_obligation_releasable(PENTAX_ADMISSION_BLOCK_NONE, 0, 0, 9),
          "obligation not released while a candidate is on the body");
    check(!pentax_output_obligation_releasable(PENTAX_ADMISSION_BLOCK_NONE, 1, 0, 0),
          "obligation not released while our own capture is in flight");

    /* THE DEAD END, precisely. Issue #175 added an orphan-recovery path: if a candidate
     * is on the body and none of ours is in flight, claim it (transfer/publish/delete)
     * instead of refusing forever. In the recorded wedge that path is unreachable:
     *
     *   - pentax_admission_block_reason checks activity FIRST, so PROCESSING makes the
     *     strict reason UNSAFE_ACTIVITY and the capture/candidate branches are never
     *     reached -- even though field36=1 (a real handle) is right there.
     *   - pentax_orphan_candidate_claimable lists UNSAFE_ACTIVITY among the reasons it
     *     will NOT claim, so recovery is skipped and the shutter is refused again.
     *
     * The log proves the candidate is visible: the same frame yields
     * output-safe-reason=transfer-candidate-available. So the exact situation #175 was
     * written for -- orphan present, none of ours in flight -- is defeated purely by the
     * strict reason being UNSAFE_ACTIVITY rather than a candidate reason. */
    check(pentax_orphan_candidate_claimable(wedged_safe, 0, 1),
          "orphan IS claimable under output-safe policy (candidate present, none ours)");
    check(!pentax_orphan_candidate_claimable(wedged, 0, 1),
          "but NOT claimable under strict UNSAFE_ACTIVITY -- this is the dead end");

    printf("\n%s\n", failures ? "FAILED" : "ALL PASS");
    return failures ? 1 : 0;
}
EOF

if ! "$cc" -O0 -std=gnu11 -Wall -Wextra -Werror -I"$work" -o "$work/harness" "$work/harness.c" 2>"$work/cc.err"; then
    echo "FAIL: harness did not compile" >&2
    sed 's/^/    /' "$work/cc.err" >&2
    exit 1
fi
"$work/harness"
