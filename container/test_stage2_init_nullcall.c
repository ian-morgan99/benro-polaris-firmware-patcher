/* Issue #124 regression test: the #121 settle probe in
 * stage2_pentax_enable_keep_live_view() must not call a NULL
 * g_real_gp_widget_get_value during camera init.
 *
 * Test cases (per TA spec):
 *   1. pentaxpclvmode lookup succeeds, gp_widget_get_value resolved ->
 *      probe runs, settle window armed when d035==1.
 *   2. pentaxpclvmode lookup succeeds, gp_widget_get_value MISSING (NULL) ->
 *      probe skipped safely, no crash, keep-LV still enabled.
 *   3. pentaxpclvmode lookup fails -> probe skipped, keep-LV still enabled.
 *   4. d035==0 (live view not active) -> settle window NOT armed.
 *   5. d035==1 (live view active) -> settle window IS armed.
 */
#define STAGE2_NO_CONSTRUCTOR 1
#include "stage2_loader.c"

#include <assert.h>
#include <stdio.h>

/* ---- fakes ---------------------------------------------------------- */
static int fake_init_calls;
static int fake_get_single_config_result;
static const char *fake_get_single_config_name; /* which widget was requested */
static void *fake_lvwidget;                     /* non-NULL sentinel for lvmode */
#define FAKE_LV_WIDGET      ((void *)0x1)
#define FAKE_KEEP_LV_WIDGET ((void *)0x2)
static int fake_widget_get_value_result;
static int fake_widget_get_value_val;           /* what the fake returns in *value */
static int fake_widget_set_value_int_calls;
static int fake_set_single_config_calls;

static int fake_gp_camera_init(void *camera, void *context)
{
    (void)camera; (void)context;
    fake_init_calls++;
    return 0; /* GP_OK */
}

static int fake_get_abilities(void *camera, void *abilities)
{
    (void)camera;
    strcpy((char *)abilities, "Pentax K-3 Mark III (MTP mode)");
    return 0;
}

/* Returns a widget for "pentaxpclvmode" and "pentaxpclvkeep";
 * returns fake_get_single_config_result for the requested name. */
static int fake_get_single_config(void *camera, const char *name,
                                  void **widget_out, void *context)
{
    (void)camera; (void)context;
    fake_get_single_config_name = name;
    if (strcmp(name, "pentaxpclvmode") == 0) {
        *widget_out = fake_lvwidget;
        return 0; /* GP_OK */
    }
    if (strcmp(name, "pentaxpclvkeep") == 0) {
        *widget_out = FAKE_KEEP_LV_WIDGET;
        return 0;
    }
    *widget_out = NULL;
    return fake_get_single_config_result;
}

static int fake_widget_get_value(void *widget, void *value)
{
    (void)widget;
    *(int *)value = fake_widget_get_value_val;
    return fake_widget_get_value_result;
}

static int fake_widget_set_value_int(void *widget, const void *value)
{
    (void)widget; (void)value;
    fake_widget_set_value_int_calls++;
    return 0;
}

static int fake_set_single_config(void *camera, const char *name,
                                  void *widget, void *context)
{
    (void)camera; (void)name; (void)widget; (void)context;
    fake_set_single_config_calls++;
    return 0;
}

/* ---- fixture reset -------------------------------------------------- */
static void reset_fixture(void)
{
    g_real_gp_camera_init = fake_gp_camera_init;
    g_real_gp_camera_get_abilities = fake_get_abilities;
    g_real_gp_camera_get_single_config = fake_get_single_config;
    g_real_gp_camera_set_single_config = fake_set_single_config;
    g_real_gp_widget_set_value_int = fake_widget_set_value_int;
    g_real_gp_widget_get_value = NULL; /* default: unresolved */
    /* RTLD_DEFAULT is a valid dlsym handle: the fix's
     * dlsym(RTLD_DEFAULT, "gp_widget_get_value") searches the global symbol
     * table and returns NULL (our fake is named fake_widget_get_value), which
     * is exactly the "helper unavailable" case we want to exercise safely. */
    g_stage2_core = RTLD_DEFAULT;

    g_pentax_session_was_open = 0;
    g_pentax_preview_settle_until = 0;

    fake_init_calls = 0;
    fake_get_single_config_result = -1;
    fake_lvwidget = FAKE_LV_WIDGET;
    fake_widget_get_value_result = 0;
    fake_widget_get_value_val = 0;
    fake_widget_set_value_int_calls = 0;
    fake_set_single_config_calls = 0;
}

/* ---- tests ---------------------------------------------------------- */

/* Case 1: probe runs when gp_widget_get_value is resolved and d035==1. */
static void test_probe_runs_when_resolved_d035_1(void)
{
    reset_fixture();
    g_real_gp_widget_get_value = fake_widget_get_value;
    fake_widget_get_value_val = 1; /* live view active */

    int camera;
    int ret = stage2_shim_gp_camera_init(&camera, NULL);
    assert(ret == 0);
    assert(fake_init_calls == 1);
    /* settle window must be armed */
    assert(g_pentax_session_was_open == 1);
    assert(g_pentax_preview_settle_until > stage2_monotonic_secs());
    /* keep-LV was still enabled */
    assert(fake_widget_set_value_int_calls == 1);
    assert(fake_set_single_config_calls == 1);
    printf("  PASS: probe runs when resolved, d035=1 -> settle armed\n");
}

/* Case 2: gp_widget_get_value is NULL (missing) -> probe skipped, no crash. */
static void test_probe_skipped_when_missing(void)
{
    reset_fixture();
    /* g_real_gp_widget_get_value stays NULL; g_stage2_core is a fake handle
     * so the fix's dlsym will return NULL and the guard skips the probe. */
    assert(g_real_gp_widget_get_value == NULL);

    int camera;
    int ret = stage2_shim_gp_camera_init(&camera, NULL);
    assert(ret == 0);
    assert(fake_init_calls == 1);
    /* settle window NOT armed (probe was skipped) */
    assert(g_pentax_session_was_open == 0);
    assert(g_pentax_preview_settle_until == 0);
    /* keep-LV still enabled (the probe is optional, not init-critical) */
    assert(fake_widget_set_value_int_calls == 1);
    assert(fake_set_single_config_calls == 1);
    printf("  PASS: probe skipped when gp_widget_get_value missing, no crash\n");
}

/* Case 3: pentaxpclvmode lookup fails -> probe skipped. */
static void test_probe_skipped_when_lookup_fails(void)
{
    reset_fixture();
    g_real_gp_widget_get_value = fake_widget_get_value;
    /* Make the lvmode lookup fail by returning a non-OK code.
     * We do this by setting fake_lvwidget to NULL and having the fake
     * return 0 (GP_OK) but with a NULL widget -> the `lvwidget` check fails. */
    fake_lvwidget = NULL;

    int camera;
    int ret = stage2_shim_gp_camera_init(&camera, NULL);
    assert(ret == 0);
    assert(g_pentax_session_was_open == 0);
    /* keep-LV still enabled */
    assert(fake_widget_set_value_int_calls == 1);
    printf("  PASS: probe skipped when pentaxpclvmode lookup returns no widget\n");
}

/* Case 4: d035==0 (live view not active) -> settle NOT armed. */
static void test_settle_not_armed_when_d035_0(void)
{
    reset_fixture();
    g_real_gp_widget_get_value = fake_widget_get_value;
    fake_widget_get_value_val = 0; /* live view NOT active */

    int camera;
    int ret = stage2_shim_gp_camera_init(&camera, NULL);
    assert(ret == 0);
    assert(g_pentax_session_was_open == 0);
    assert(g_pentax_preview_settle_until == 0);
    /* keep-LV still enabled */
    assert(fake_widget_set_value_int_calls == 1);
    printf("  PASS: settle not armed when d035=0\n");
}

/* Case 5: d035==1 (live view active) -> settle IS armed. */
static void test_settle_armed_when_d035_1(void)
{
    reset_fixture();
    g_real_gp_widget_get_value = fake_widget_get_value;
    fake_widget_get_value_val = 1;

    int camera;
    int ret = stage2_shim_gp_camera_init(&camera, NULL);
    assert(ret == 0);
    assert(g_pentax_session_was_open == 1);
    assert(g_pentax_preview_settle_until > stage2_monotonic_secs());
    printf("  PASS: settle armed when d035=1\n");
}

int main(void)
{
    setenv("STAGE2_PENTAX_KEEP_LV", "1", 1);
    setenv("STAGE2_PENTAX_PREVIEW_SETTLE_SECS", "5", 1);

    printf("[test_stage2_init_nullcall] Issue #124 regression tests\n");
    test_probe_runs_when_resolved_d035_1();
    test_probe_skipped_when_missing();
    test_probe_skipped_when_lookup_fails();
    test_settle_not_armed_when_d035_0();
    test_settle_armed_when_d035_1();
    printf("[test_stage2_init_nullcall] ALL PASS\n");
    return 0;
}
