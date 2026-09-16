#define STAGE2_NO_CONSTRUCTOR 1
#include "stage2_loader.c"

#include <assert.h>

static int fake_preview_result;
static int fake_preview_calls;
static int fake_capture_result;
static int fake_capture_calls;
static int fake_capture_last_type;

static int fake_get_abilities(void *camera, void *abilities)
{
    (void)camera;
    strcpy((char *)abilities, "Pentax K-3 Mark III (PTP mode)");
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

static int fake_capture(void *camera, int type, void *path, void *context)
{
    (void)camera;
    (void)path;
    (void)context;
    fake_capture_calls++;
    fake_capture_last_type = type;
    return fake_capture_result;
}

static void reset_fixture(void)
{
    g_real_gp_camera_get_abilities = fake_get_abilities;
    g_real_gp_camera_capture_preview = fake_capture_preview;
    g_real_gp_camera_capture = fake_capture;
    g_pentax_preview_timeouts = 0;
    g_pentax_preview_backoff_until = 0;
    g_pentax_preview_last_fetch = 0;
    g_pentax_capture_failures = 0;
    g_pentax_capture_backoff_until = 0;
    fake_preview_result = 0;
    fake_preview_calls = 0;
    fake_capture_result = 0;
    fake_capture_calls = 0;
    fake_capture_last_type = -1;
}

int main(void)
{
    int camera;

    setenv("STAGE2_TETHER_CAPTURE", "1", 1);
    setenv("STAGE2_PENTAX_PREVIEW_BACKOFF", "1", 1);
    setenv("STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_SECS", "0", 1);
    setenv("STAGE2_PENTAX_PREVIEW_BACKOFF_MAX", "1", 1);
    setenv("STAGE2_PENTAX_PREVIEW_BACKOFF_SECS", "60", 1);
    setenv("STAGE2_PENTAX_CAPTURE_BACKOFF_MAX", "1", 1);
    setenv("STAGE2_PENTAX_CAPTURE_BACKOFF_SECS", "60", 1);

    /* A preview failure opens only the preview cooldown.  A still capture must
     * still reach the real camera call and must not erase preview state. */
    reset_fixture();
    fake_preview_result = -2;
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == -2);
    assert(g_pentax_preview_backoff_until > time(NULL));
    assert(g_pentax_capture_backoff_until == 0);
    assert(stage2_shim_gp_camera_capture(&camera, STAGE2_GP_CAPTURE_IMAGE,
                                         NULL, NULL) == 0);
    assert(fake_capture_calls == 1);
    assert(g_pentax_preview_backoff_until > time(NULL));

    /* A still-capture failure opens only the capture cooldown.  Preview must
     * still reach its real call and must not erase capture state. */
    reset_fixture();
    fake_capture_result = -6;
    assert(stage2_shim_gp_camera_capture(&camera, STAGE2_GP_CAPTURE_IMAGE,
                                         NULL, NULL) == -6);
    assert(g_pentax_capture_backoff_until > time(NULL));
    assert(g_pentax_preview_backoff_until == 0);
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == 0);
    assert(fake_preview_calls == 1);
    assert(g_pentax_capture_backoff_until > time(NULL));

    /* Non-image capture types are exact pass-through, even while the still
     * capture cooldown is active, and do not mutate still-capture state. */
    fake_capture_result = -9;
    assert(stage2_shim_gp_camera_capture(&camera, 1, NULL, NULL) == -9);
    assert(fake_capture_calls == 2);
    assert(fake_capture_last_type == 1);
    assert(g_pentax_capture_failures == 1);
    assert(g_pentax_capture_backoff_until > time(NULL));

    puts("stage2 backoff isolation: PASS");
    return 0;
}
