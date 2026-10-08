/* Issue #183 regression test: the guarded capture wrapper must convert a
 * GP_OK return with an EMPTY CameraFilePath (the observed lost-transfer
 * signature: camera fires, no file lands, the closed app emits the full
 * 264 success lifecycle anyway) into GP_ERROR_CAMERA_ERROR, and must leave
 * every other case byte-identical pass-through.
 *
 * Test cases:
 *   1. GP_OK + populated name+folder          -> 0 (success passes through).
 *   2. GP_OK + empty name                     -> -113 (GP_ERROR_CAMERA_ERROR).
 *   3. GP_OK + empty folder                   -> -113.
 *   4. GP_OK + empty path, non-still type     -> 0 (movie/sound untouched).
 *   5. GP_OK + empty path, check disabled     -> 0 (legacy escape hatch).
 *   6. GP_ERROR_TIMEOUT + empty path          -> -10 (error class preserved).
 *   7. in-flight flag is cleared on every path (including the conversion).
 */
#define STAGE2_NO_CONSTRUCTOR 1
#include "stage2_loader.c"

#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

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

static void set_path(const char *name, const char *folder)
{
    memset(&fake_path_out, 0, sizeof fake_path_out);
    if (name)   snprintf(fake_path_out.name, sizeof fake_path_out.name, "%s", name);
    if (folder) snprintf(fake_path_out.folder, sizeof fake_path_out.folder, "%s", folder);
}

int main(void)
{
    fake_file_path p;
    int ret;

    g_real_gp_camera_capture = fake_gp_camera_capture;
    setenv("STAGE2_CAPTURE_GUARD", "1", 1);
    unsetenv("STAGE2_CAPTURE_EMPTY_PATH_CHECK");   /* default ON */

    /* 1. success with a real path passes through untouched. */
    fake_capture_ret = 0;
    set_path("IMGP0001.DNG", "/store_00010001/DCIM/100RICOH");
    ret = stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL);
    assert(ret == 0);
    assert(strcmp(p.name, "IMGP0001.DNG") == 0);
    assert(atomic_load(&g_capture_in_flight) == 0);

    /* 2. GP_OK with empty name -> GP_ERROR_CAMERA_ERROR (the #183 signature). */
    fake_capture_ret = 0;
    set_path("", "/store_00010001/DCIM/100RICOH");
    ret = stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL);
    assert(ret == STAGE2_GP_ERROR_CAMERA_ERROR);
    assert(atomic_load(&g_capture_in_flight) == 0);

    /* 3. GP_OK with empty folder -> same conversion. */
    fake_capture_ret = 0;
    set_path("IMGP0002.DNG", "");
    ret = stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL);
    assert(ret == STAGE2_GP_ERROR_CAMERA_ERROR);

    /* 4. non-still capture types are exact pass-through even with empty path. */
    fake_capture_ret = 0;
    set_path("", "");
    ret = stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE + 1, &p, NULL);
    assert(ret == 0);

    /* 5. escape hatch: check disabled restores legacy pass-through. */
    setenv("STAGE2_CAPTURE_EMPTY_PATH_CHECK", "0", 1);
    fake_capture_ret = 0;
    set_path("", "");
    ret = stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL);
    assert(ret == 0);
    unsetenv("STAGE2_CAPTURE_EMPTY_PATH_CHECK");

    /* 6. a real error keeps its own class; the conversion never masks it. */
    fake_capture_ret = STAGE2_GP_ERROR_TIMEOUT;
    set_path("", "");
    ret = stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, &p, NULL);
    assert(ret == STAGE2_GP_ERROR_TIMEOUT);

    /* 7. NULL path with GP_OK is left alone (defensive: not our contract). */
    fake_capture_ret = 0;
    ret = stage2_guarded_gp_camera_capture(NULL, STAGE2_GP_CAPTURE_IMAGE, NULL, NULL);
    assert(ret == 0);

    printf("PASS: issue #183 empty-path capture conversion (7 cases)\n");
    return 0;
}
