/* Generic Stage-2 config safety regression test.
 *
 * A camera reconnect can make the underlying get_single_config call return
 * GP_OK with a RADIO/MENU widget containing no choices.  That is not a usable
 * success for the Benro protocol: serialising it as RD:0;V:;R:; makes the
 * downstream parser index an empty list.  The loader must reject it as a
 * transient CAMERA_BUSY result, while preserving valid choice and non-choice
 * widgets for every camera model.
 */
#define STAGE2_NO_CONSTRUCTOR 1
#include "stage2_loader.c"

#include <assert.h>
#include <stdio.h>

struct fake_widget {
    int type;
    int choices;
};

static struct fake_widget widget;
static int fake_get_ret;
static int fake_type_ret;
static int fake_choice_ret;
static int fake_free_calls;

static int fake_get_single_config(void *camera, const char *name,
                                  void **widget_out, void *context)
{
    (void)camera;
    (void)name;
    (void)context;
    if (fake_get_ret == 0)
        *widget_out = &widget;
    return fake_get_ret;
}

static int fake_get_null_config(void *camera, const char *name,
                                void **widget_out, void *context)
{
    (void)camera;
    (void)name;
    (void)context;
    *widget_out = NULL;
    return 0;
}

static int fake_widget_get_type(void *value, int *type)
{
    (void)value;
    if (fake_type_ret != 0)
        return fake_type_ret;
    *type = widget.type;
    return 0;
}

static int fake_widget_count_choices(void *value)
{
    (void)value;
    if (fake_choice_ret != 0)
        return fake_choice_ret;
    return widget.choices;
}

static void fake_widget_free(void *value)
{
    assert(value == &widget);
    fake_free_calls++;
}

static void reset_fixture(void)
{
    g_stage2_core = NULL;
    g_real_gp_camera_get_single_config = fake_get_single_config;
    g_real_gp_widget_get_type = fake_widget_get_type;
    g_real_gp_widget_count_choices = fake_widget_count_choices;
    g_real_gp_widget_free = fake_widget_free;
    fake_get_ret = 0;
    fake_type_ret = 0;
    fake_choice_ret = 0;
    fake_free_calls = 0;
    widget.type = STAGE2_GP_WIDGET_RADIO;
    widget.choices = 0;
}

int main(void)
{
    int camera;
    void *out;

    printf("[test_stage2_empty_choice_guard] generic config safety\n");

    /* Empty RADIO and MENU widgets are rejected and released. */
    reset_fixture();
    out = NULL;
    assert(stage2_shim_gp_camera_get_single_config(&camera, "iso", &out, NULL)
           == STAGE2_GP_ERROR_CAMERA_BUSY);
    assert(out == NULL);
    assert(fake_free_calls == 1);

    reset_fixture();
    widget.type = STAGE2_GP_WIDGET_MENU;
    out = NULL;
    assert(stage2_shim_gp_camera_get_single_config(&camera, "whitebalance", &out,
                                                   NULL)
           == STAGE2_GP_ERROR_CAMERA_BUSY);
    assert(out == NULL);
    assert(fake_free_calls == 1);

    /* Missing inspection helpers also fail closed without calling a NULL
     * function pointer. */
    reset_fixture();
    g_real_gp_widget_get_type = NULL;
    out = NULL;
    assert(stage2_shim_gp_camera_get_single_config(&camera, "iso", &out, NULL)
           == STAGE2_GP_ERROR_CAMERA_BUSY);
    assert(out == NULL);
    assert(fake_free_calls == 1);

    reset_fixture();
    g_real_gp_widget_free = NULL;
    out = NULL;
    assert(stage2_shim_gp_camera_get_single_config(&camera, "iso", &out, NULL)
           == STAGE2_GP_ERROR_CAMERA_BUSY);
    assert(out == NULL);
    assert(fake_free_calls == 0);

    /* A valid one-choice widget is retained; this preserves bulb-style lists. */
    reset_fixture();
    widget.choices = 1;
    out = NULL;
    assert(stage2_shim_gp_camera_get_single_config(&camera, "shutterspeed", &out,
                                                   NULL) == 0);
    assert(out == &widget);
    assert(fake_free_calls == 0);

    /* Text widgets do not have choices and remain valid. */
    reset_fixture();
    widget.type = STAGE2_GP_WIDGET_TEXT;
    out = NULL;
    assert(stage2_shim_gp_camera_get_single_config(&camera, "status", &out, NULL)
           == 0);
    assert(out == &widget);
    assert(fake_free_calls == 0);

    /* Inspection failure is fail-closed rather than a false success. */
    reset_fixture();
    fake_type_ret = -1;
    out = NULL;
    assert(stage2_shim_gp_camera_get_single_config(&camera, "aperture", &out,
                                                   NULL)
           == STAGE2_GP_ERROR_CAMERA_BUSY);
    assert(out == NULL);
    assert(fake_free_calls == 1);

    /* A real camera error remains unchanged and is never treated as an empty
     * widget condition. */
    reset_fixture();
    fake_get_ret = -7;
    out = (void *)0x1;
    assert(stage2_shim_gp_camera_get_single_config(&camera, "iso", &out, NULL)
           == -7);
    assert(out == (void *)0x1);
    assert(fake_free_calls == 0);

    /* GP_OK with a NULL widget is also rejected. */
    reset_fixture();
    out = NULL;
    /* The fake normally returns a widget, so emulate the malformed NULL result
     * by replacing the underlying function for this one call. */
    g_real_gp_camera_get_single_config = fake_get_null_config;
    assert(stage2_shim_gp_camera_get_single_config(&camera, "iso", &out, NULL)
           == STAGE2_GP_ERROR_CAMERA_BUSY);
    assert(out == NULL);
    assert(fake_free_calls == 0);

    printf("[test_stage2_empty_choice_guard] ALL PASS\n");
    return 0;
}
