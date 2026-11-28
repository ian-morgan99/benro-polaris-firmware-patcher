#define STAGE2_NO_CONSTRUCTOR 1
#include <time.h>
static long long clock_ms = 60000;
static int fixture_clock(clockid_t id, struct timespec *ts)
{
    if (id != CLOCK_MONOTONIC)
        return clock_gettime(id, ts);
    ts->tv_sec = clock_ms / 1000;
    ts->tv_nsec = (clock_ms % 1000) * 1000000;
    return 0;
}
#define clock_gettime fixture_clock
#include "stage2_loader.c"

#include <assert.h>

static int fake_preview_result;
static int fake_preview_calls;
static int fake_preview_ms;

static const char *fake_model_string = "Pentax K-3 Mark III (PTP mode)";

static int fake_get_abilities(void *camera, void *abilities)
{
    (void)camera;
    strcpy((char *)abilities, fake_model_string);
    return 0;
}

static int fake_capture_calls;
static int fake_capture_saw_in_flight;

static int fake_capture(void *camera, int type, void *path, void *context)
{
    (void)camera;
    (void)type;
    (void)path;
    (void)context;
    fake_capture_calls++;
    fake_capture_saw_in_flight = atomic_load(&g_capture_in_flight);
    return 0;
}

static int fake_init_result;
static int fake_init_calls;

static int fake_init_passthrough(void *camera, void *context)
{
    (void)camera;
    (void)context;
    fake_init_calls++;
    return fake_init_result;
}

static int fake_capture_preview(void *camera, void *file, void *context)
{
    (void)camera;
    (void)file;
    (void)context;
    fake_preview_calls++;
    clock_ms += fake_preview_ms;
    return fake_preview_result;
}

static void reset_fixture(void)
{
    g_real_gp_camera_get_abilities = fake_get_abilities;
    g_real_gp_camera_capture_preview = fake_capture_preview;
    g_real_gp_camera_capture = fake_capture;
    fake_capture_calls = 0;
    fake_capture_saw_in_flight = -1;
    atomic_store(&g_capture_in_flight, 0);
    g_pentax_preview_timeouts = 0;
    g_pentax_preview_backoff_until = 0;
    g_pentax_preview_last_fetch = 0;
    g_k1ii_preview_prompt = 0;
    fake_preview_ms = 0;
    fake_preview_result = 0;
    fake_preview_calls = 0;
    fake_model_string = "Pentax K-3 Mark III (PTP mode)";
}

int main(void)
{
    int camera;
    int direct_capture_target;

    /* Regression for o-v12j/k/n: with ALL Stage-2 capture policy explicitly
     * disabled (the legacy escape hatch), still capture is installed as the
     * exact resolved core target, never through a Stage-2 wrapper.
     * Issue #183 changes the DEFAULT: the empty-path outcome check is ON by
     * default and installs the guarded wrapper on its own merit (the .60 A/B,
     * 16/16 clean with the wrapper frame, established that boundary is safe). */
    unsetenv("STAGE2_CAPTURE_TRACE");
    setenv("STAGE2_CAPTURE_GUARD", "0", 1);
    setenv("STAGE2_CAPTURE_EMPTY_PATH_CHECK", "0", 1);
    /* Issue #181 follow-up: the storefull remap is ON by default like the #183
     * check, so the legacy escape hatch must name it explicitly to get an
     * un-wrapped gp_camera_capture. */
    setenv("STAGE2_CAPTURE_STOREFULL_REMAP", "0", 1);
    /* Issue #362: companion reporting is ON by default for the same reason, so
     * the escape hatch must name it too -- otherwise "all policy disabled" would
     * silently stop being reachable and this regression would stop testing what
     * its name claims. */
    setenv("STAGE2_EXTRA_CAPTURE_REPORT", "0", 1);
    assert(stage2_capture_slot_target("gp_camera_capture",
                                      &direct_capture_target) ==
           &direct_capture_target);
    setenv("STAGE2_CAPTURE_TRACE", "0", 1);
    assert(stage2_capture_slot_target("gp_camera_capture",
                                      &direct_capture_target) ==
           &direct_capture_target);
    /* #183: with the empty-path check enabled and the #176 guard OFF, the
     * guarded wrapper must still be installed (the check stands on its own). */
    setenv("STAGE2_CAPTURE_EMPTY_PATH_CHECK", "1", 1);
    assert(stage2_capture_slot_target("gp_camera_capture",
                                      &direct_capture_target) !=
           &direct_capture_target);
    assert(g_real_gp_camera_capture ==
           (stage2_gp_camera_capture_fn)&direct_capture_target);
    setenv("STAGE2_CAPTURE_EMPTY_PATH_CHECK", "0", 1);
    /* #181 follow-up: the storefull remap stands on its own merit too -- with
     * every other mode off and only the remap enabled, the wrapper must still
     * be installed, otherwise -8 would reach pgphoto unmapped and be reported
     * as a successful capture. */
    setenv("STAGE2_CAPTURE_STOREFULL_REMAP", "1", 1);
    assert(stage2_capture_slot_target("gp_camera_capture",
                                      &direct_capture_target) !=
           &direct_capture_target);
    assert(g_real_gp_camera_capture ==
           (stage2_gp_camera_capture_fn)&direct_capture_target);
    setenv("STAGE2_CAPTURE_STOREFULL_REMAP", "0", 1);
    /* The additional call boundary is available only when explicitly selected
     * for boundary diagnostics; it must never be silently enabled by default. */
    setenv("STAGE2_CAPTURE_TRACE", "1", 1);
    assert(stage2_capture_slot_target("gp_camera_capture",
                                      &direct_capture_target) !=
           &direct_capture_target);
    assert(g_real_gp_camera_capture ==
           (stage2_gp_camera_capture_fn)&direct_capture_target);
    unsetenv("STAGE2_CAPTURE_TRACE");

    /* Issue #176: the capture-in-flight guard is opt-in, and when armed it must
     * (a) still resolve through the cached real fn, (b) mark the window so the
     * init shim refuses re-entry, and (c) clear the mark on return. */
    unsetenv("STAGE2_CAPTURE_GUARD");
    assert(!stage2_capture_guard_enabled());
    assert(stage2_capture_slot_target("gp_camera_capture",
                                      &direct_capture_target) ==
           &direct_capture_target);
    setenv("STAGE2_CAPTURE_GUARD", "0", 1);
    assert(!stage2_capture_guard_enabled());
    assert(stage2_capture_slot_target("gp_camera_capture",
                                      &direct_capture_target) ==
           &direct_capture_target);
    setenv("STAGE2_CAPTURE_GUARD", "1", 1);
    assert(stage2_capture_guard_enabled());
    assert(stage2_capture_slot_target("gp_camera_capture",
                                      &direct_capture_target) !=
           &direct_capture_target);
    assert(g_real_gp_camera_capture ==
           (stage2_gp_camera_capture_fn)&direct_capture_target);

    /* Armed: a capture marks the window and clears it; a re-init inside the
     * window returns busy without calling the real init. */
    reset_fixture();
    g_real_gp_camera_init = fake_init_passthrough;
    fake_init_calls = 0;
    g_real_gp_camera_capture = fake_capture;
    assert(stage2_guarded_gp_camera_capture(&camera, 0, NULL, NULL) == 0);
    assert(fake_capture_calls == 1);
    assert(fake_capture_saw_in_flight == 1);
    assert(atomic_load(&g_capture_in_flight) == 0);

    /* Outside a capture window the guard must not interfere with init. */
    assert(stage2_capture_guard_enabled());
    assert(atomic_load(&g_capture_in_flight) == 0);
    fake_init_calls = 0;
    fake_init_result = 0;
    assert(stage2_shim_gp_camera_init(&camera, NULL) == 0);
    assert(fake_init_calls == 1);            /* no window -> real init runs */

    /* Inside a window, init is refused with the non-terminal busy class. */
    atomic_store(&g_capture_in_flight, 1);
    fake_init_calls = 0;
    assert(stage2_shim_gp_camera_init(&camera, NULL) == STAGE2_GP_ERROR_CAMERA_BUSY);
    assert(fake_init_calls == 0);            /* refused BEFORE the real init */
    atomic_store(&g_capture_in_flight, 0);

    /* Guard disarmed: the same in-flight state must not change init behaviour. */
    setenv("STAGE2_CAPTURE_GUARD", "0", 1);
    atomic_store(&g_capture_in_flight, 1);
    g_real_gp_camera_init = fake_init_passthrough;
    fake_init_result = 0;
    assert(stage2_shim_gp_camera_init(&camera, NULL) == 0);
    atomic_store(&g_capture_in_flight, 0);
    unsetenv("STAGE2_CAPTURE_GUARD");

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

    /* A K-1 II with no evidence of a prompt frame retains the 8 s floor. */
    reset_fixture();
    unsetenv("STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_SECS");
    fake_model_string = "Pentax K-1 Mark II (PTP mode)";
    g_pentax_preview_last_fetch = clock_ms - 3000;
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) ==
           STAGE2_GP_ERROR_CAMERA_BUSY);
    assert(fake_preview_calls == 0); /* gated: no real fetch */
    clock_ms += 5000;
    fake_preview_ms = 4; /* 21 November v114 camera-side get-frame timing */
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == 0);
    clock_ms += 1995;
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == STAGE2_GP_ERROR_CAMERA_BUSY);
    assert(fake_preview_calls == 1);
    clock_ms++;
    fake_preview_ms = 2000;
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == 0);
    clock_ms += 7999;
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == STAGE2_GP_ERROR_CAMERA_BUSY);
    clock_ms++;
    fake_preview_ms = 4;
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == 0);
    clock_ms += 2000;
    fake_preview_result = STAGE2_GP_ERROR_TIMEOUT;
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == STAGE2_GP_ERROR_TIMEOUT);
    assert(!g_k1ii_preview_prompt);
    fake_preview_result = 0;
    clock_ms += 2000;
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == STAGE2_GP_ERROR_CAMERA_BUSY);
    assert(fake_preview_calls == 4);

    /* A new camera session must not inherit the last interval/settle timer. */
    g_pentax_session_was_open = 1;
    g_pentax_preview_settle_until = stage2_monotonic_secs() + 5;
    assert(stage2_shim_gp_camera_init(&camera, NULL) == 0);
    assert(!g_pentax_preview_settle_until && !g_pentax_preview_last_fetch);
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == 0);
    assert(fake_preview_calls == 5);

    reset_fixture();
    fake_model_string = "Pentax K-3 Mark III (PTP mode)";
    g_pentax_preview_last_fetch = clock_ms - 3000;
    assert(stage2_shim_gp_camera_capture_preview(&camera, NULL, NULL) == 0);
    assert(fake_preview_calls == 1); /* 3 s > generic 2 s default: real fetch */

    puts("stage2 backoff isolation: PASS");
    return 0;
}
