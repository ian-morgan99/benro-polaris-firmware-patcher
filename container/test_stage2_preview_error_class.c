/* Issue #127 regression test: the preview governor must CLASSIFY results before
 * applying policy, not collapse every non-zero result into one transient backoff.
 *   - GP_ERROR_NOT_SUPPORTED (-6): permanent -> capability-disable; subsequent
 *     calls return NOT_SUPPORTED WITHOUT reaching the real core (no endless PTP).
 *   - I/O / no-device (GP_ERROR_IO -7): dead-session signal -> counted toward
 *     backoff and surfaced, not silently relabelled as a merely-busy camera.
 *   - transient (timeout -10): bounded backoff as before.
 *   - a fresh init re-arms the disabled capability.
 */
#define STAGE2_NO_CONSTRUCTOR 1
#include "stage2_loader.c"

#include <assert.h>
#include <stdio.h>

static int fake_capture_result;      /* what the real core returns */
static int fake_capture_calls;

static int fake_capture_preview(void *camera, void *file, void *context)
{
    (void)camera; (void)file; (void)context;
    fake_capture_calls++;
    return fake_capture_result;
}

static int fake_gp_camera_get_abilities(void *camera, void *abilities)
{
    (void)camera;
    unsigned char *bytes = (unsigned char *)abilities;
    memset(bytes, 0, 4096);
    memcpy(bytes, "Pentax K-3 Mark III", 19);
    return 0;
}

static void reset_fixture(void)
{
    g_real_gp_camera_capture_preview = fake_capture_preview;
    g_real_gp_camera_get_abilities = fake_gp_camera_get_abilities;
    g_pentax_session_was_open = 0;
    g_pentax_preview_settle_until = 0;
    g_pentax_preview_backoff_until = 0;
    g_pentax_preview_last_fetch = 0;
    g_pentax_preview_timeouts = 0;
    g_pentax_preview_disabled = 0;
    g_pentax_preview_session_unhealthy = 0;
    g_pentax_preview_last_terminal = 0;
    fake_capture_result = 0;
    fake_capture_calls = 0;
}

int main(void)
{
    setenv("STAGE2_PENTAX_PREVIEW_BACKOFF", "1", 1);
    setenv("STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_SECS", "0", 1);
    int camera;

    printf("[test_stage2_preview_error_class] Issue #127 error classification\n");

    /* NOT_SUPPORTED -> capability-disable: first call reaches the core, then the
     * flag short-circuits so no further PTP traffic is generated. */
    reset_fixture();
    fake_capture_result = -6;
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == -6);
    assert(fake_capture_calls == 1);
    assert(g_pentax_preview_disabled == 1);
    /* Subsequent calls are short-circuited: the core is NOT called again. */
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == -6);
    assert(fake_capture_calls == 1);
    printf("  PASS: NOT_SUPPORTED disables preview (no endless PTP traffic)\n");

    /* A fresh init re-arms the capability. */
    g_pentax_preview_disabled = 0;   /* what stage2_shim_gp_camera_init does */
    fake_capture_result = 0;
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == 0);
    assert(fake_capture_calls == 2);
    printf("  PASS: a fresh session re-arms the disabled capability\n");

    /* I/O / no-device (-7): a TRANSPORT/SESSION failure.  It must mark the session
     * generation unhealthy and NOT be folded into the transient backoff (which would
     * relabel it as CAMERA_BUSY and delay the rebind path). */
    reset_fixture();
    fake_capture_result = -7;
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == -7);
    assert(g_pentax_preview_session_unhealthy == 1);
    assert(g_pentax_preview_last_terminal == -7);
    assert(g_pentax_preview_timeouts == 0);   /* NOT counted toward the transient backoff */
    printf("  PASS: I/O / no-device marks the session unhealthy (not folded into the BUSY backoff)\n");

    /* Repeated calls after an injected NO_DEVICE/I-O must keep surfacing the original
     * terminal class and NEVER become GP_ERROR_CAMERA_BUSY, and must not resume real
     * preview traffic until a fresh/revalidated session generation exists. */
    {
        int r;
        for (int i = 0; i < 5; i++) {
            r = stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL);
            assert(r == -7);                       /* the original terminal class, not CAMERA_BUSY */
            assert(r != STAGE2_GP_ERROR_CAMERA_BUSY);
        }
        assert(fake_capture_calls == 1);           /* real preview traffic did NOT resume */
        printf("  PASS: repeated calls after NO_DEVICE/I-O never become CAMERA_BUSY and do not resume traffic\n");
    }

    /* A fresh/revalidated session generation (init) clears the unhealthy mark so real
     * preview traffic can resume. */
    {
        g_pentax_preview_session_unhealthy = 0;    /* what stage2_shim_gp_camera_init does */
        g_pentax_preview_last_terminal = 0;
        fake_capture_result = 0;
        assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == 0);
        assert(fake_capture_calls == 2);           /* real preview traffic resumed */
        printf("  PASS: a fresh/revalidated session generation clears the unhealthy mark and resumes traffic\n");
    }

    /* Transient timeout (-10): bounded backoff as before. */
    reset_fixture();
    fake_capture_result = -10;
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == -10);
    assert(g_pentax_preview_timeouts == 1);
    printf("  PASS: transient timeout is counted toward the bounded backoff\n");

    /* Unknown error class (e.g. GP_ERROR_FIXED_LIMIT_EXCEEDED -8): SURFACE the original
     * code -- do NOT silently relabel it as CAMERA_BUSY and do NOT arm the transient
     * backoff. */
    reset_fixture();
    fake_capture_result = -8;   /* GP_ERROR_FIXED_LIMIT_EXCEEDED: not NOT_SUPPORTED, not I/O, not a known transient */
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == -8);
    assert(g_pentax_preview_timeouts == 0);          /* not armed into the transient backoff */
    assert(g_pentax_preview_backoff_until == 0);     /* no BUSY cooldown armed */
    assert(g_pentax_preview_session_unhealthy == 0); /* not a transport failure either */
    printf("  PASS: unknown error is surfaced (not relabelled as CAMERA_BUSY, no backoff armed)\n");

    printf("[test_stage2_preview_error_class] ALL PASS\n");
    return 0;
}
