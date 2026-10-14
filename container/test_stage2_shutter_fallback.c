/* Issue #187 SHIM #6 (gp_camera_get_single_config shutter-fallback) regression.
 *
 * The #187 source review found that the synthetic-widget path could return
 * success with an incomplete widget: it resolved gp_widget_new +
 * gp_widget_set_name but used g_real_gp_widget_set_value (declared in the SHIM
 * #3 block, only resolved there) and ignored set_name/set_value failures.
 *
 * The fix must: resolve ALL three widget helpers (new/set_name/set_value) plus
 * gp_widget_free; check every return value; free the widget on any failure; and
 * propagate the ORIGINAL camera error unless a complete value-bearing widget is
 * verified. These tests pin that contract.
 *
 * Test cases (STAGE2_SHUTTER_FALLBACK=1, real get_single_config fails with -1):
 *   1. all helpers resolved + set_value succeeds -> returns 0, widget non-NULL,
 *      value "0/1" written, name "shutterspeed".
 *   2. value helper UNRESOLVED (NULL) -> returns the original error (-1), no
 *      widget leaked as success.
 *   3. set_value FAILS -> returns the original error (-1), widget freed.
 *   4. set_name FAILS -> returns the original error (-1), widget freed.
 *   5. gate OFF (default) -> pure pass-through of the original error, no
 *      synthesis attempted.
 */
#define STAGE2_NO_CONSTRUCTOR 1
#include "stage2_loader.c"

#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

/* ---- fakes ---------------------------------------------------------- */
static int fake_get_single_config_calls;
static int fake_get_single_config_ret;
static int fake_gp_camera_get_single_config(void *camera, const char *name,
                                            void **widget_out, void *context)
{
    (void)camera; (void)name; (void)widget_out; (void)context;
    fake_get_single_config_calls++;
    return fake_get_single_config_ret;
}

/* Fake widget: a small struct so we can observe name/value writes. */
struct fake_widget { int type; char name[32]; char value[32]; };
static int fake_widget_new_calls, fake_widget_set_name_calls,
           fake_widget_set_value_calls, fake_widget_free_calls;
static int fake_widget_new_ret, fake_widget_set_name_ret, fake_widget_set_value_ret;

static int fake_gp_widget_new(int type, const char *label, void **widget)
{
    (void)label;
    fake_widget_new_calls++;
    if (fake_widget_new_ret != 0)
        return fake_widget_new_ret;
    struct fake_widget *w = calloc(1, sizeof(*w));
    w->type = type;
    *widget = w;
    return 0;
}

static int fake_gp_widget_set_name(void *widget, const char *name)
{
    fake_widget_set_name_calls++;
    if (fake_widget_set_name_ret != 0)
        return fake_widget_set_name_ret;
    struct fake_widget *w = (struct fake_widget *)widget;
    snprintf(w->name, sizeof(w->name), "%s", name);
    return 0;
}

static int fake_gp_widget_set_value(void *widget, const void *value)
{
    fake_widget_set_value_calls++;
    if (fake_widget_set_value_ret != 0)
        return fake_widget_set_value_ret;
    struct fake_widget *w = (struct fake_widget *)widget;
    snprintf(w->value, sizeof(w->value), "%s", (const char *)value);
    return 0;
}

static void fake_gp_widget_free(void *widget)
{
    fake_widget_free_calls++;
    free(widget);
}

static void reset_fixture(void)
{
    g_real_gp_camera_get_single_config = fake_gp_camera_get_single_config;
    g_real_gp_widget_new      = fake_gp_widget_new;
    g_real_gp_widget_set_name = fake_gp_widget_set_name;
    g_real_gp_widget_set_value = fake_gp_widget_set_value;
    g_real_gp_widget_free     = fake_gp_widget_free;
    /* Keep dlsym out of the loop: with g_stage2_core NULL the lazy-resolve
     * guards are no-ops, so the fakes above are exactly what the shim uses. */
    g_stage2_core = NULL;
    fake_get_single_config_calls = 0;
    fake_get_single_config_ret = -1;   /* real get_config fails (bulb mode) */
    fake_widget_new_calls = fake_widget_set_name_calls = 0;
    fake_widget_set_value_calls = fake_widget_free_calls = 0;
    fake_widget_new_ret = fake_widget_set_name_ret = fake_widget_set_value_ret = 0;
}

int main(void)
{
    int camera;
    void *w = (void *)0x1;   /* sentinel: proves the shim wrote *widget_out */

    printf("[test_stage2_shutter_fallback] Issue #187 SHIM #6 synthetic-widget contract\n");

    /* Case 1: all helpers resolved + set_value succeeds -> success, complete
     * value-bearing widget. */
    reset_fixture();
    setenv("STAGE2_SHUTTER_FALLBACK", "1", 1);
    w = (void *)0x1;
    assert(stage2_shim_gp_camera_get_single_config(&camera, "shutterspeed", &w, NULL) == 0);
    assert(w != (void *)0x1);                       /* a real widget was returned */
    struct fake_widget *fw = (struct fake_widget *)w;
    assert(strcmp(fw->name, "shutterspeed") == 0);
    assert(strcmp(fw->value, "0/1") == 0);          /* value-bearing, as claimed */
    assert(fake_widget_set_value_calls == 1);
    free(fw);

    /* Case 2: value helper UNRESOLVED -> propagate the original error. */
    reset_fixture();
    g_real_gp_widget_set_value = NULL;              /* SHIM #3 never ran */
    w = (void *)0x1;
    assert(stage2_shim_gp_camera_get_single_config(&camera, "shutterspeed", &w, NULL) == -1);
    assert(w == (void *)0x1);                      /* no widget returned on failure */

    /* Case 3: set_value FAILS -> propagate the original error, widget freed. */
    reset_fixture();
    fake_widget_set_value_ret = -1;
    w = (void *)0x1;
    assert(stage2_shim_gp_camera_get_single_config(&camera, "shutterspeed", &w, NULL) == -1);
    assert(w == (void *)0x1);
    assert(fake_widget_free_calls == 1);            /* leaked widget released */

    /* Case 4: set_name FAILS -> propagate the original error, widget freed. */
    reset_fixture();
    fake_widget_set_name_ret = -1;
    w = (void *)0x1;
    assert(stage2_shim_gp_camera_get_single_config(&camera, "shutterspeed", &w, NULL) == -1);
    assert(w == (void *)0x1);
    assert(fake_widget_free_calls == 1);

    /* Case 5: gate OFF (default) -> pure pass-through, no synthesis. */
    reset_fixture();
    unsetenv("STAGE2_SHUTTER_FALLBACK");
    w = (void *)0x1;
    assert(stage2_shim_gp_camera_get_single_config(&camera, "shutterspeed", &w, NULL) == -1);
    assert(w == (void *)0x1);
    assert(fake_widget_new_calls == 0);             /* never attempted synthesis */

    printf("[test_stage2_shutter_fallback] ALL PASS\n");
    return 0;
}
