/* Analysis-only probe for #188. Includes the production loader; no camera.
 * --observe verifies/reports baseline facts. --require-protection is a red
 * regression gate until trace and protection compose. Never install this. */
#define STAGE2_NO_CONSTRUCTOR 1
#include "../../../container/stage2_loader.c"
#include <assert.h>

typedef struct { char name[128]; char folder[1024]; } probe_path;
static int result, calls, marker;
static int fake_capture(void *camera, int type, void *path, void *context)
{
    (void)camera; (void)type; (void)path; (void)context;
    calls++;
    marker = atomic_load(&g_capture_in_flight);
    return result; /* Leave the caller's empty path untouched. */
}

int main(int argc, char **argv)
{
    int require = argc == 2 && strcmp(argv[1], "--require-protection") == 0;
    if (argc != 2 || (!require && strcmp(argv[1], "--observe") != 0))
        return 2;
    int violations = 0;
    for (int trace = 0; trace < 2; trace++)
    for (int guard = 0; guard < 2; guard++)
    for (int check = 0; check < 2; check++) {
        setenv("STAGE2_CAPTURE_TRACE", trace ? "1" : "0", 1);
        setenv("STAGE2_CAPTURE_GUARD", guard ? "1" : "0", 1);
        setenv("STAGE2_CAPTURE_EMPTY_PATH_CHECK", check ? "1" : "0", 1);
        stage2_gp_camera_capture_fn target = (stage2_gp_camera_capture_fn)
            stage2_capture_slot_target("gp_camera_capture", (void *)fake_capture);
        assert((trace || guard || check) || target == fake_capture);
        calls = 0;
        for (int shot = 1; shot <= 3; shot++) {
            probe_path path = {{0}, {0}};
            atomic_store(&g_capture_in_flight, 0);
            result = 0;
            int ret = target(NULL, STAGE2_GP_CAPTURE_IMAGE, &path, NULL);
            if (guard && !marker) violations++;
            if (check && ret != STAGE2_GP_ERROR_CAMERA_ERROR) violations++;
            assert(atomic_load(&g_capture_in_flight) == 0);
            result = STAGE2_GP_ERROR_TIMEOUT;
            ret = target(NULL, STAGE2_GP_CAPTURE_IMAGE, &path, NULL);
            assert(ret == STAGE2_GP_ERROR_TIMEOUT);
            assert(atomic_load(&g_capture_in_flight) == 0);
        }
        assert(calls == 6);
        printf("trace=%d guard=%d check=%d marker=%d repeated_timeout=-10\n",
               trace, guard, check, marker);
    }
    printf("protection violations=%d (8 combinations, 3 shots, success/timeout)\n",
           violations);
    if (!require) {
        /* Frozen-source diagnostic, not a green protection/firmware gate. */
        assert(violations == 12);
        puts("OBSERVATION CONFIRMED: trace bypasses enabled protections");
        return 0;
    }
    if (violations) {
        fputs("FAIL: enabled protections must execute with tracing\n", stderr);
        return 1;
    }
    return 0;
}
