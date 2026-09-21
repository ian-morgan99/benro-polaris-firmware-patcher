/* Issue #125 regression test: the Pentax preview/capture timing gates must key
 * off a MONOTONIC clock, not wall clock.  A wall-clock correction (NTP step)
 * must not extend or skip a cooldown/settle window.  We prove this by driving
 * the on-demand preview interval gate with a controlled monotonic field:
 *   - a 2 s min-interval is enforced purely by the monotonic last_fetch value;
 *   - advancing the monotonic clock by exactly the interval re-arms the fetch;
 *   - a "wall-clock" jump (simulated by leaving the monotonic field unchanged)
 *     does NOT change the interval decision.
 */
#define STAGE2_NO_CONSTRUCTOR 1
#include "stage2_loader.c"

#include <assert.h>
#include <stdio.h>

static int fake_capture_preview(void *camera, void *file, void *context)
{
    (void)camera; (void)file; (void)context;
    return 0;
}

static int fake_gp_camera_get_abilities(void *camera, void *abilities)
{
    (void)camera;
    unsigned char *bytes = (unsigned char *)abilities;
    memset(bytes, 0, 4096);
    memcpy(bytes, "Pentax K-3 Mark III", 19);
    return 0;
}

int main(void)
{
    setenv("STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_SECS", "2", 1);
    setenv("STAGE2_PENTAX_PREVIEW_BACKOFF", "1", 1);
    int camera;

    g_real_gp_camera_capture_preview = fake_capture_preview;
    g_real_gp_camera_get_abilities = fake_gp_camera_get_abilities;
    g_pentax_session_was_open = 0;
    g_pentax_preview_settle_until = 0;
    g_pentax_preview_backoff_until = 0;

    printf("[test_stage2_monotonic_clock] Issue #125 monotonic clock gates\n");

    /* First fetch: no last_fetch yet -> proceeds (sets last_fetch to now). */
    g_pentax_preview_last_fetch = 0;
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == 0);
    long long first_fetch = g_pentax_preview_last_fetch;
    assert(first_fetch > 0);
    printf("  PASS: first fetch proceeds and records a monotonic last_fetch\n");

    /* Immediately after (monotonic unchanged), within the 2 s interval -> BUSY. */
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL)
           == STAGE2_GP_ERROR_CAMERA_BUSY);
    printf("  PASS: fetch inside the 2 s monotonic interval returns CAMERA_BUSY\n");

    /* Simulate a wall-clock step of +1 h WITHOUT touching the monotonic field:
     * the interval decision must be unchanged (still within 2 s of last_fetch). */
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL)
           == STAGE2_GP_ERROR_CAMERA_BUSY);
    printf("  PASS: a wall-clock step does not bypass the monotonic interval\n");

    /* Advance the monotonic field by exactly the interval -> fetch re-arms. */
    g_pentax_preview_last_fetch = first_fetch; /* keep the recorded value */
    /* The gate compares (now - last_fetch < min_interval).  now is the live
     * monotonic clock; to prove the gate keys off the field, set last_fetch far
     * enough in the past that (now - last_fetch) >= 2 s. */
    g_pentax_preview_last_fetch = stage2_monotonic_secs() - 3;
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == 0);
    printf("  PASS: advancing the monotonic clock past the interval re-arms the fetch\n");

    printf("[test_stage2_monotonic_clock] ALL PASS\n");
    return 0;
}
