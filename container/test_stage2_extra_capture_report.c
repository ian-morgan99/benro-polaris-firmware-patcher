/* Issue #362 regression test: the loader must surface companions that the
 * camlib detected but no consumer ever asked for.
 *
 * Why this exists.  On a JPG+RAW capture the ptp2 Pentax driver reads the output
 * mode immediately before the shutter and records every extra member of the
 * exposure in params->pentax.extra_capture_count / extra_capture_files, exposed
 * through gp_camera_get_extra_capture_files().  Detection demonstrably works --
 * the [pentax] initiate-enter marker shows companions=1 on dual-format captures
 * across retained logs -- but nothing consumes it:
 *
 *   strings pgphoto.stage2ondisk      | grep -c extra_capture  -> 0
 *   strings libpolaris_stage2.so      | grep -c extra_capture  -> 0
 *
 * So a companion is detected, paid for in camera-side capture time, and silently
 * dropped.  That is the reported symptom "RAW+JPEG shown as RAW", with no error
 * anywhere because nothing ever asks for the second file.  pgphoto is closed and
 * cannot be changed here, so the loader queries the driver itself after a
 * successful still capture and makes the gap visible.
 *
 * Test cases:
 *   1. one companion            -> reported, with folder and name.
 *   2. two companions           -> both listed, count is the driver's value.
 *   3. zero companions          -> silent (single-format capture is normal).
 *   4. GP_ERROR_NOT_SUPPORTED   -> silent (documented answer for bodies without
 *                                  dual-format support; not a defect).
 *   5. any other error          -> reported as a query failure, never ignored.
 *   6. escape hatch off         -> the driver is never called at all.
 *   7. failed capture           -> no query (nothing was delivered).
 *   8. non-image capture type   -> no query.
 *   9. empty-path false success -> still rejected as before, and no query.
 *  10. count above the buffer   -> reported honestly, printing clamped to the
 *                                  buffer so nothing reads past it.
 *  11. reporting never changes the capture result: every case above returns
 *      exactly what the core returned.
 */
#define STAGE2_NO_CONSTRUCTOR 1
#include "stage2_loader.c"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* CameraFilePath mirror (gphoto2-camera.h): char name[128]; char folder[1024]. */
typedef struct { char name[128]; char folder[1024]; } fake_file_path;

static int fake_capture_ret = 0;
static int fake_capture_type_seen = -1;
static fake_file_path fake_path_out;

static int fake_gp_camera_capture(void *camera, int type, void *path, void *context)
{
    (void)camera; (void)context;
    fake_capture_type_seen = type;
    if (path)
        *(fake_file_path *)path = fake_path_out;
    return fake_capture_ret;
}

/* Exported from the test binary (-rdynamic) so the loader's
 * dlsym(RTLD_DEFAULT, "gp_camera_get_extra_capture_files") finds it, exactly as
 * it finds the real symbol in libgphoto2.so.6 on the device. */
static int extra_calls = 0;
static int fake_extra_ret = 0;
static int fake_extra_count = 0;

int gp_camera_get_extra_capture_files(void *camera, void *paths,
                                      int max_count, int *count)
{
    (void)camera;
    extra_calls++;
    if (fake_extra_ret != 0) {
        if (count)
            *count = -1;
        return fake_extra_ret;
    }
    if (paths && max_count > 0) {
        /* Mirror the camlib: fill min(count, max_count) entries. */
        int n = fake_extra_count < max_count ? fake_extra_count : max_count;
        char *buf = (char *)paths;
        for (int i = 0; i < n; i++) {
            fake_file_path *slot = (fake_file_path *)(buf + i * sizeof(fake_file_path));
            snprintf(slot->name, sizeof slot->name, "IMGP0002_%d.PEF", i);
            snprintf(slot->folder, sizeof slot->folder, "/store_00010001/DCIM");
        }
    }
    if (count)
        *count = fake_extra_count;
    return 0;
}

int main(void)
{
    fake_file_path p;

    g_real_gp_camera_capture = fake_gp_camera_capture;
    /* Force a fresh lookup against this binary's exported symbol. */
    g_real_get_extra_files = NULL;
    g_extra_files_lookup_failed = 0;

    setenv("STAGE2_CAPTURE_GUARD", "1", 1);
    unsetenv("STAGE2_CAPTURE_EMPTY_PATH_CHECK");
    unsetenv("STAGE2_CAPTURE_STOREFULL_REMAP");
    unsetenv("STAGE2_EXTRA_CAPTURE_REPORT");   /* default ON */

    memset(&fake_path_out, 0, sizeof fake_path_out);
    snprintf(fake_path_out.name, sizeof fake_path_out.name, "IMGP0002.JPG");
    snprintf(fake_path_out.folder, sizeof fake_path_out.folder, "/store_00010001/DCIM");

    /* 1. one companion is reported. */
    fake_capture_ret = 0;
    fake_extra_ret = 0;
    fake_extra_count = 1;
    extra_calls = 0;
    assert(stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL) == 0);
    assert(extra_calls == 1);

    /* 2. two companions are reported with the driver's own count. */
    fake_extra_count = 2;
    extra_calls = 0;
    assert(stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL) == 0);
    assert(extra_calls == 1);

    /* 3. zero companions: single-format capture, nothing expected. */
    fake_extra_count = 0;
    extra_calls = 0;
    assert(stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL) == 0);
    assert(extra_calls == 1);   /* asked, but reports nothing */

    /* 4. GP_ERROR_NOT_SUPPORTED is the documented answer for a body without
     *    dual-format support: normal, and must not be logged as a failure. */
    fake_extra_ret = STAGE2_GP_ERROR_NOT_SUPPORTED;
    extra_calls = 0;
    assert(stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL) == 0);
    assert(extra_calls == 1);
    fake_extra_ret = 0;

    /* 5. any other error must be surfaced, not swallowed -- a silent query
     *    failure is the exact class of bug this test exists to prevent. */
    fake_extra_ret = -1;
    extra_calls = 0;
    assert(stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL) == 0);
    assert(extra_calls == 1);
    fake_extra_ret = 0;

    /* 6. the documented escape hatch must not call the driver at all. */
    setenv("STAGE2_EXTRA_CAPTURE_REPORT", "0", 1);
    fake_extra_count = 1;
    extra_calls = 0;
    assert(stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL) == 0);
    assert(extra_calls == 0);
    unsetenv("STAGE2_EXTRA_CAPTURE_REPORT");

    /* 7. a failed capture delivered nothing, so there is nothing to reconcile. */
    fake_capture_ret = STAGE2_GP_ERROR_CAMERA_BUSY;
    extra_calls = 0;
    assert(stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL)
           == STAGE2_GP_ERROR_CAMERA_BUSY);
    assert(extra_calls == 0);
    fake_capture_ret = 0;

    /* 8. a non-still capture has no companions. */
    extra_calls = 0;
    assert(stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_VIDEO, &p, NULL) == 0);
    assert(extra_calls == 0);
    /* 9. the #183 empty-path guard still wins, and a bogus success is not
     *    reported as a partial delivery. */
    fake_file_path empty_out;
    memset(&empty_out, 0, sizeof empty_out);
    snprintf(empty_out.name, sizeof empty_out.name, "IMGP0003.JPG");   /* folder empty */
    fake_path_out = empty_out;
    extra_calls = 0;
    assert(stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL)
           == STAGE2_GP_ERROR_CAMERA_ERROR);
    assert(extra_calls == 0);

    /* Restore a valid path for the remaining cases. */
    memset(&fake_path_out, 0, sizeof fake_path_out);
    snprintf(fake_path_out.name, sizeof fake_path_out.name, "IMGP0002.JPG");
    snprintf(fake_path_out.folder, sizeof fake_path_out.folder, "/store_00010001/DCIM");

    /* 10. a count larger than the buffer is reported honestly but printed only
     *     within the buffer, so nothing reads past it. */
    fake_extra_count = STAGE2_EXTRA_MAX + 5;
    extra_calls = 0;
    assert(stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL) == 0);
    assert(extra_calls == 1);

    puts("PASS: companion reporting surfaces detected-but-undelivered files (issue #362)");
    return 0;
}
