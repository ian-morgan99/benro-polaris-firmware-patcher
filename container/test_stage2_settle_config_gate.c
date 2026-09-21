/* Issue #128 diagnostic regression test. The preview-settle window may suppress
 * preview traffic, but must NOT discard state-changing CONFIG writes on the
 * assumption that Benro retries them. Both config APIs therefore remain exact
 * pass-through during an armed settle window; preview remains gated.
 *
 * Test cases:
 *   1. settle armed -> set_single_config reaches real core and returns its result.
 *   2. settle armed -> set_config reaches real core and returns its result.
 *   3. settle armed -> capture_preview still returns CAMERA_BUSY, real preview not called.
 *   4. settle expired -> set_single_config reaches real core.
 *   5. fresh session -> set_single_config reaches real core immediately.
 */
#define STAGE2_NO_CONSTRUCTOR 1
#include "stage2_loader.c"

#include <assert.h>
#include <stdio.h>

/* ---- fakes ---------------------------------------------------------- */
static int fake_set_single_config_calls;
static int fake_set_config_calls;
static int fake_capture_preview_calls;

static int fake_gp_camera_set_single_config(void *camera, const char *name,
                                            void *widget, void *context)
{
    (void)camera; (void)name; (void)widget; (void)context;
    fake_set_single_config_calls++;
    return 0;
}

static int fake_gp_camera_set_config(void *camera, void *widget, void *context)
{
    (void)camera; (void)widget; (void)context;
    fake_set_config_calls++;
    return 0;
}

static int fake_capture_preview(void *camera, void *file, void *context)
{
    (void)camera; (void)file; (void)context;
    fake_capture_preview_calls++;
    return 0;
}

/* Provide a Pentax model string so the keep-lv model gate passes. */
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
    g_real_gp_camera_set_single_config = fake_gp_camera_set_single_config;
    g_real_gp_camera_set_config = fake_gp_camera_set_config;
    g_real_gp_camera_capture_preview = fake_capture_preview;
    g_real_gp_camera_get_abilities = fake_gp_camera_get_abilities;
    g_pentax_session_was_open = 0;
    g_pentax_preview_settle_until = 0;
    fake_set_single_config_calls = 0;
    fake_set_config_calls = 0;
    fake_capture_preview_calls = 0;
}

int main(void)
{
    setenv("STAGE2_PENTAX_PREVIEW_SETTLE_SECS", "5", 1);
    int camera;

    printf("[test_stage2_settle_config_gate] Issue #128 config pass-through diagnostic\n");

    /* Case 1: armed window -> set_single_config still reaches real core. */
    reset_fixture();
    g_pentax_session_was_open = 1;
    g_pentax_preview_settle_until = stage2_monotonic_secs() + 5;
    assert(stage2_shim_gp_camera_set_single_config(&camera, "iso", NULL, NULL) == 0);
    assert(fake_set_single_config_calls == 1);
    printf("  PASS: armed preview-settle window does not discard set_single_config\n");

    /* Case 2: armed window -> set_config still reaches real core. */
    reset_fixture();
    g_pentax_session_was_open = 1;
    g_pentax_preview_settle_until = stage2_monotonic_secs() + 5;
    assert(stage2_shim_gp_camera_set_config(&camera, NULL, NULL) == 0);
    assert(fake_set_config_calls == 1);
    printf("  PASS: armed preview-settle window does not discard set_config\n");

    /* Case 3: armed window -> capture_preview gated (existing behaviour). */
    reset_fixture();
    g_pentax_session_was_open = 1;
    g_pentax_preview_settle_until = stage2_monotonic_secs() + 5;
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL)
           == STAGE2_GP_ERROR_CAMERA_BUSY);
    assert(fake_capture_preview_calls == 0);
    printf("  PASS: armed window gates capture_preview (CAMERA_BUSY, no core call)\n");

    /* Case 4: expired window -> set_single_config proceeds to the real core. */
    reset_fixture();
    g_pentax_session_was_open = 1;
    g_pentax_preview_settle_until = stage2_monotonic_secs() - 1; /* already in the past */
    assert(stage2_shim_gp_camera_set_single_config(&camera, "iso", NULL, NULL) == 0);
    assert(fake_set_single_config_calls == 1);
    printf("  PASS: expired window lets set_single_config reach the real core\n");

    /* Case 5: not armed (fresh session) -> set_single_config proceeds immediately. */
    reset_fixture();
    assert(g_pentax_session_was_open == 0);
    assert(stage2_shim_gp_camera_set_single_config(&camera, "iso", NULL, NULL) == 0);
    assert(fake_set_single_config_calls == 1);
    printf("  PASS: fresh session (no settle window) lets set_single_config through\n");

    printf("[test_stage2_settle_config_gate] ALL PASS\n");
    return 0;
}
