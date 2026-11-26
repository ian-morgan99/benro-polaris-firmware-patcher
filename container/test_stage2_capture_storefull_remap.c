/* Issue #181 follow-up regression test: the guarded capture wrapper must remap
 * GP_ERROR_FIXED_LIMIT_EXCEEDED (-8) onto GP_ERROR_NO_SPACE (-115).
 *
 * Why this exists.  pgphoto's capture_generic() prints "Could not capture
 * image." for any non-zero gp_camera_capture() result, but then returns only
 * for an explicit allowlist of codes: -6, -3, -112, -115, -53, -60, -110 and
 * -114.  Every other code falls through to the download path and is reported
 * upstream as a successful capture.
 *
 * This libgphoto2 produces -8 for PTP_RC_StoreFull (0x200c) -- a full camera
 * card -- and -8 is not on that list.  On the K-1 II rig two captures returned
 * gp=-8 and both reached the client as "captureImage ret 0" with no file on the
 * card, while codes on the list (-110 x14, -112 x3) propagated normally.  So a
 * full card silently drops frames from an astro stack instead of erroring.
 *
 * GP_ERROR_NO_SPACE (-115) is on pgphoto's list and is the semantically correct
 * code for a full card, so the wrapper can surface the failure without touching
 * pgphoto.
 *
 * Test cases:
 *   1. -8 with remap default-on                 -> -115 (surfaces as an error).
 *   2. -8 with remap explicitly enabled         -> -115.
 *   3. -8 with the documented escape hatch      -> -8  (raw code preserved).
 *   4. -110 is never rewritten                  -> -110 (already propagates).
 *   5. -112 is never rewritten                  -> -112.
 *   6. -115 passes through untouched            -> -115 (no double-remap).
 *   7. success is never rewritten               -> 0.
 *   8. in-flight flag cleared on the remap path -> 0.
 */
#define STAGE2_NO_CONSTRUCTOR 1
#include "stage2_loader.c"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* CameraFilePath mirror (gphoto2-camera.h): char name[128]; char folder[1024]. */
typedef struct { char name[128]; char folder[1024]; } fake_file_path;

static int fake_capture_ret;
static fake_file_path fake_path_out;

static int fake_gp_camera_capture(void *camera, int type, void *path, void *context)
{
    (void)camera; (void)type; (void)context;
    if (path)
        *(fake_file_path *)path = fake_path_out;
    return fake_capture_ret;
}

int main(void)
{
    fake_file_path p;
    int ret;

    g_real_gp_camera_capture = fake_gp_camera_capture;
    setenv("STAGE2_CAPTURE_GUARD", "1", 1);
    unsetenv("STAGE2_CAPTURE_EMPTY_PATH_CHECK");
    unsetenv("STAGE2_CAPTURE_STOREFULL_REMAP");   /* default ON */

    memset(&fake_path_out, 0, sizeof fake_path_out);
    snprintf(fake_path_out.name, sizeof fake_path_out.name, "IMGP0002.DNG");
    snprintf(fake_path_out.folder, sizeof fake_path_out.folder, "/store_00010001/DCIM");

    /* 1. -8 is remapped to -115 by default. */
    fake_capture_ret = STAGE2_GP_ERROR_FIXED_LIMIT_EXCEEDED;
    ret = stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL);
    assert(ret == STAGE2_GP_ERROR_NO_SPACE);

    /* 2. explicitly enabled behaves identically. */
    setenv("STAGE2_CAPTURE_STOREFULL_REMAP", "1", 1);
    ret = stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL);
    assert(ret == STAGE2_GP_ERROR_NO_SPACE);

    /* 3. the documented escape hatch preserves the raw code. */
    setenv("STAGE2_CAPTURE_STOREFULL_REMAP", "0", 1);
    ret = stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL);
    assert(ret == STAGE2_GP_ERROR_FIXED_LIMIT_EXCEEDED);
    unsetenv("STAGE2_CAPTURE_STOREFULL_REMAP");

    /* 4-6. codes already on pgphoto's allowlist are never rewritten. */
    fake_capture_ret = STAGE2_GP_ERROR_CAMERA_BUSY;
    ret = stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL);
    assert(ret == STAGE2_GP_ERROR_CAMERA_BUSY);

    fake_capture_ret = STAGE2_GP_ERROR_CANCEL;
    ret = stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL);
    assert(ret == STAGE2_GP_ERROR_CANCEL);

    fake_capture_ret = STAGE2_GP_ERROR_NO_SPACE;
    ret = stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL);
    assert(ret == STAGE2_GP_ERROR_NO_SPACE);

    /* 7. success is untouched. */
    fake_capture_ret = 0;
    ret = stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL);
    assert(ret == 0);
    assert(strcmp(p.name, "IMGP0002.DNG") == 0);

    /* 8. the in-flight flag is cleared on the remap path too. */
    fake_capture_ret = STAGE2_GP_ERROR_FIXED_LIMIT_EXCEEDED;
    ret = stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL);
    assert(ret == STAGE2_GP_ERROR_NO_SPACE);
    assert(atomic_load(&g_capture_in_flight) == 0);

    printf("PASS: issue #181 storefull -8 -> -115 capture remap (8 cases)\n");
    return 0;
}
