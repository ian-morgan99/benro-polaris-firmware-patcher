#define STAGE2_NO_CONSTRUCTOR 1
#include "stage2_loader.c"

#include <assert.h>

static int fake_preview_result;
static int fake_preview_calls;

static const char *fake_model_string = "Pentax K-3 Mark III (PTP mode)";

static int fake_get_abilities(void *camera, void *abilities)
{
    (void)camera;
    strcpy((char *)abilities, fake_model_string);
    return 0;
}

static int fake_capture_preview(void *camera, void *file, void *context)
{
    (void)camera;
    (void)file;
    (void)context;
    fake_preview_calls++;
    return fake_preview_result;
}

static void reset_fixture(void)
{
    g_real_gp_camera_get_abilities = fake_get_abilities;
    g_real_gp_camera_capture_preview = fake_capture_preview;
    g_pentax_preview_timeouts = 0;
    g_pentax_preview_backoff_until = 0;
    g_pentax_preview_last_fetch = 0;
    fake_preview_result = 0;
    fake_preview_calls = 0;
    fake_model_string = "Pentax K-3 Mark III (PTP mode)";
}

int main(void)
{
    int camera;
    int direct_capture_target;

    /* Regression for o-v12j/k/n: still capture is installed as the exact
     * resolved core target, never through a Stage-2 wrapper. */
    assert(stage2_capture_slot_target("gp_camera_capture",
                                      &direct_capture_target) ==
           &direct_capture_target);

    setenv("STAGE2_TETHER_CAPTURE", "1", 1);
    setenv("STAGE2_PENTAX_PREVIEW_BACKOFF", "1", 1);
    setenv("STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_SECS", "0", 1);
    setenv("STAGE2_PENTAX_PREVIEW_BACKOFF_MAX", "1", 1);
    setenv("STAGE2_PENTAX_PREVIEW_BACKOFF_SECS", "60", 1);
    /* A known-transient preview failure opens the bounded preview cooldown. */
    reset_fixture();
    fake_preview_result = STAGE2_GP_ERROR_TIMEOUT;
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) ==
           STAGE2_GP_ERROR_TIMEOUT);
    assert(g_pentax_preview_backoff_until > stage2_monotonic_secs());
    assert(g_pentax_preview_backoff_until > stage2_monotonic_secs());

    /* K-1 II model-specific on-demand gate: with no explicit
     * STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_SECS override, a K-1 II defaults to an
     * 8 s interval (aligned to its ~1 frame / 7-8 s live-view cadence) instead
     * of the generic 2 s.  A fetch 3 s ago is therefore still inside the window
     * for a K-1 II (returns busy, no real call) but outside it for any other
     * body (real call proceeds). */
    reset_fixture();
    unsetenv("STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_SECS");
    fake_model_string = "Pentax K-1 Mark II (PTP mode)";
    g_pentax_preview_last_fetch = stage2_monotonic_secs() - 3;
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) ==
           STAGE2_GP_ERROR_CAMERA_BUSY);
    assert(fake_preview_calls == 0); /* gated: no real fetch */

    reset_fixture();
    fake_model_string = "Pentax K-3 Mark III (PTP mode)";
    g_pentax_preview_last_fetch = stage2_monotonic_secs() - 3;
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == 0);
    assert(fake_preview_calls == 1); /* 3 s > generic 2 s default: real fetch */

    puts("stage2 backoff isolation: PASS");
    return 0;
}
