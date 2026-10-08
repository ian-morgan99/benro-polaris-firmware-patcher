/* #188: exercise the production slot selector and composed capture boundary. */
#define STAGE2_NO_CONSTRUCTOR 1
#include "stage2_loader.c"
#include <assert.h>

typedef struct { char name[128]; char folder[1024]; } fake_path;
static int core_result, core_calls, saw_marker, init_result, init_calls;
static void *expected_camera, *expected_path, *expected_context;
static int expected_type, probe_init;
static fake_path core_path;

static int fake_init(void *camera, void *context)
{
    assert(camera == expected_camera && context == expected_context);
    init_calls++;
    return STAGE2_GP_ERROR_TIMEOUT;
}

static int fake_capture(void *camera, int type, void *path, void *context)
{
    assert(camera == expected_camera && path == expected_path &&
           context == expected_context && type == expected_type);
    core_calls++;
    saw_marker = atomic_load(&g_capture_in_flight);
    if (probe_init)
        init_result = stage2_shim_gp_camera_init(camera, context);
    if (path)
        memcpy(path, &core_path, sizeof core_path);
    return core_result;
}

int main(void)
{
    int camera, context;
    expected_camera = &camera;
    expected_context = &context;
    g_real_gp_camera_init = fake_init;
    unsetenv("STAGE2_REASSERT_CRASH_HANDLER");

    for (int trace = 0; trace < 2; trace++)
    for (int guard = 0; guard < 2; guard++)
    for (int check = 0; check < 2; check++) {
        setenv("STAGE2_CAPTURE_TRACE", trace ? "1" : "0", 1);
        setenv("STAGE2_CAPTURE_GUARD", guard ? "1" : "0", 1);
        setenv("STAGE2_CAPTURE_EMPTY_PATH_CHECK", check ? "1" : "0", 1);
        stage2_gp_camera_capture_fn target = (stage2_gp_camera_capture_fn)
            stage2_capture_slot_target("gp_camera_capture", (void *)fake_capture);
        assert(target == ((trace || guard || check) ?
               stage2_guarded_gp_camera_capture : fake_capture));
        assert(stage2_capture_slot_target("gp_camera_exit", (void *)fake_capture)
               == (void *)fake_capture);
        for (int shot = 1; shot <= 3; shot++)
        for (int scenario = 0; scenario < 6; scenario++) {
            fake_path out = {{0}, {0}};
            memset(&core_path, 0, sizeof core_path);
            strcpy(core_path.name, "IMGP0001.DNG");
            strcpy(core_path.folder, "/store/DCIM");
            expected_path = &out;
            expected_type = STAGE2_GP_CAPTURE_IMAGE;
            core_result = 0;
            int expected_result = 0;
            if (scenario == 1 || scenario == 3 || scenario == 4)
                core_path.name[0] = '\0';
            if (scenario == 2)
                core_path.folder[0] = '\0';
            if (scenario == 1 || scenario == 2)
                expected_result = check ? STAGE2_GP_ERROR_CAMERA_ERROR : 0;
            if (scenario == 3)
                expected_result = core_result = STAGE2_GP_ERROR_TIMEOUT;
            if (scenario == 4)
                expected_type = STAGE2_GP_CAPTURE_IMAGE + 1;
            if (scenario == 5)
                expected_path = NULL;
            atomic_store(&g_capture_in_flight, 0);
            core_calls = init_calls = 0;
            probe_init = shot == 1 && scenario == 0;
            int ret = target(&camera, expected_type, expected_path, &context);
            assert(ret == expected_result && core_calls == 1);
            assert(saw_marker == (guard || check));
            assert(atomic_load(&g_capture_in_flight) == 0);
            if (expected_path)
                assert(memcmp(&out, &core_path, sizeof out) == 0);
            if (probe_init) {
                assert(init_result == (guard ? STAGE2_GP_ERROR_CAMERA_BUSY :
                                      STAGE2_GP_ERROR_TIMEOUT));
                assert(init_calls == (guard ? 0 : 1));
                /* Protection must release the marker before the next init. */
                assert(stage2_shim_gp_camera_init(&camera, &context) ==
                       STAGE2_GP_ERROR_TIMEOUT);
            }
        }
    }
    /* Preserve default trace-off/guard-off/check-on selection and unresolved
     * core behavior, without leaking an in-flight marker. */
    unsetenv("STAGE2_CAPTURE_TRACE");
    unsetenv("STAGE2_CAPTURE_GUARD");
    unsetenv("STAGE2_CAPTURE_EMPTY_PATH_CHECK");
    assert(stage2_capture_slot_target("gp_camera_capture", (void *)fake_capture)
           == (void *)stage2_guarded_gp_camera_capture);
    g_real_gp_camera_capture = NULL;
    assert(stage2_guarded_gp_camera_capture(&camera, 0, NULL, &context) == -1);
    assert(atomic_load(&g_capture_in_flight) == 0);
    puts("PASS: capture composition (8 combinations x 3 shots x 6 scenarios)");
    return 0;
}
