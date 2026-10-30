/* Opt-in API timing must not change arguments, results, errno, or call count. */
#include <errno.h>
#include <time.h>
static int clock_calls, fail_clock_call;
static int fake_clock_gettime(clockid_t clock_id, struct timespec *value)
{
    if (clock_id != CLOCK_MONOTONIC)
        return -1;
    clock_calls++;
    if (clock_calls == fail_clock_call) {
        errno = EFAULT;
        return -1;
    }
    value->tv_sec = clock_calls;
    value->tv_nsec = 0;
    return 0;
}
#define clock_gettime fake_clock_gettime
#define STAGE2_NO_CONSTRUCTOR 1
#include "stage2_loader.c"
#include <assert.h>

static int get_calls, tree_calls, set_calls, get_result = -2;
static void *const camera_arg = (void *)0x1234;
static void *const widget_arg = (void *)0x2345;
static void *const context_arg = (void *)0x3456;

static int fake_get(void *camera, const char *name, void **widget, void *context)
{
    assert(camera == camera_arg && strcmp(name, "exposurecompensation") == 0);
    assert(widget && context == context_arg && errno == EDOM);
    get_calls++;
    errno = EIO;
    return get_result;
}

static int fake_set(void *camera, const char *name, void *widget, void *context)
{
    assert(camera == camera_arg && strcmp(name, "iso") == 0);
    assert(widget == widget_arg && context == context_arg && errno == EDOM);
    set_calls++;
    errno = ENOSPC;
    return -6;
}

static int fake_tree(Stage2Camera *camera, Stage2CameraWidget **widget, Stage2Context *context)
{
    assert(camera == camera_arg && widget && context == context_arg && errno == EDOM);
    tree_calls++;
    *widget = widget_arg;
    errno = EBUSY;
    return 0;
}

int main(void)
{
    FILE *logs = tmpfile();
    assert(logs);
    int saved_stderr = dup(STDERR_FILENO);
    assert(saved_stderr >= 0 && dup2(fileno(logs), STDERR_FILENO) >= 0);
    g_real_gp_camera_get_single_config = fake_get;
    g_real_gp_camera_set_single_config = fake_set;
    g_real_gp_camera_get_config = NULL;
    unsetenv("STAGE2_SHUTTER_FALLBACK");
    unsetenv("STAGE2_TETHER_CAPTURE");
    unsetenv("STAGE2_CONFIG_TIMING");
    assert(stage2_config_tree_slot_target((void *)fake_tree) == (void *)fake_tree);
    assert(g_real_gp_camera_get_config == NULL);
    void *widget = NULL;
    errno = EDOM;
    assert(stage2_shim_gp_camera_get_single_config(camera_arg, "exposurecompensation", &widget, context_arg) == -2);
    assert(errno == EIO && get_calls == 1 && widget == NULL);
    errno = EDOM;
    assert(stage2_shim_gp_camera_set_single_config(camera_arg, "iso", widget_arg, context_arg) == -6);
    assert(errno == ENOSPC && set_calls == 1);
    fflush(stderr);
    assert(ftell(logs) == 0 && clock_calls == 0);

    assert(setenv("STAGE2_CONFIG_TIMING", "1", 1) == 0);
    assert(stage2_config_tree_slot_target((void *)fake_tree) == (void *)stage2_timed_get_config);
    assert(g_real_gp_camera_get_config == fake_tree);
    errno = EDOM;
    assert(stage2_shim_gp_camera_get_single_config(camera_arg, "exposurecompensation", &widget, context_arg) == -2);
    assert(errno == EIO && get_calls == 2 && widget == NULL);
    errno = EDOM;
    assert(stage2_shim_gp_camera_set_single_config(camera_arg, "iso", widget_arg, context_arg) == -6);
    assert(errno == ENOSPC && set_calls == 2);
    Stage2CameraWidget *tree_widget = NULL;
    errno = EDOM;
    assert(stage2_timed_get_config(camera_arg, &tree_widget, context_arg) == 0);
    assert(errno == EBUSY && tree_calls == 1 && tree_widget == widget_arg);
    get_result = 0;
    widget = NULL;
    errno = EDOM;
    assert(stage2_shim_gp_camera_get_single_config(camera_arg, "exposurecompensation", &widget, context_arg) == STAGE2_GP_ERROR_CAMERA_BUSY);
    assert(get_calls == 3 && widget == NULL);
    get_result = -2;
    fflush(stderr);
    assert(fseek(logs, 0, SEEK_SET) == 0);
    char text[2048] = {0};
    assert(fread(text, 1, sizeof(text) - 1, logs) > 0);
    assert(strstr(text, "op=get-single name=exposurecompensation core-ret=-2"));
    assert(strstr(text, "op=get-single name=exposurecompensation core-ret=0"));
    assert(strstr(text, "GP_OK without widget for exposurecompensation"));
    assert(strstr(text, "op=set-single name=iso core-ret=-6"));
    assert(strstr(text, "op=get-tree name=- core-ret=0"));
    assert(strstr(text, " tid="));
    assert(strstr(text, " start=") && strstr(text, " end="));
    assert(fseek(logs, 0, SEEK_END) == 0);
    long log_end = ftell(logs);
    fail_clock_call = clock_calls + 1; /* start clock fails */
    errno = EDOM;
    assert(stage2_shim_gp_camera_get_single_config(camera_arg, "exposurecompensation", &widget, context_arg) == -2);
    assert(errno == EIO && get_calls == 4);
    fail_clock_call = clock_calls + 2; /* end clock fails */
    errno = EDOM;
    assert(stage2_shim_gp_camera_set_single_config(camera_arg, "iso", widget_arg, context_arg) == -6);
    assert(errno == ENOSPC && set_calls == 3);
    fflush(stderr);
    assert(ftell(logs) == log_end);
    assert(dup2(saved_stderr, STDERR_FILENO) >= 0);
    close(saved_stderr);
    fclose(logs);
    puts("config timing preserves arguments, return codes, errno, and call count");
    return 0;
}
