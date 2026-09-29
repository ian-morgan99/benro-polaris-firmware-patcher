/* #159 iPolar (1233:1455) adapter — userspace libuvc -> adapter -> OpenPolaris.
 * Upstream libgphoto2 2.5.34 has no uvc/ camlib; userspace path only.
 * Device: UVC 1.00, VID:PID 1233:1455, Y16, 640x960 / 1280x960.
 *
 * TA architecture direction (issue #159, 2026-09-28): once this adapter can
 * produce reliable bounded Y16 frames, feed them through the common
 * camera-source interface into plate solve — do NOT build an iPolar-specific
 * polar-solving stack. Pipeline: iPolar -> UVC/libuvc frame -> common
 * camera-source frame -> plate solve -> polar-axis error calculation.
 * This layer stays focused on: reliable bounded frame acquisition, identity/
 * generation, reconnect, and exposure/gain controls for solvable stars.
 */
#include "stage2_ipolar_adapter.h"
#include <libuvc/libuvc.h>  /* libuvc (built /work/src/libuvc/build/libuvc.so) */
#include <errno.h>

/* Bounded packed-Y16 frame store. Three leased slots prevent the libuvc
 * callback from mutating pixels while the alignment consumer is reading them. */
#define IPOLAR_MAX_FRAME_BYTES (1280 * 960 * 2) /* worst case 1280x960 Y16 */
#define IPOLAR_MIN_WIDTH 640u
#define IPOLAR_MAX_WIDTH 1280u
#define IPOLAR_HEIGHT 960u

static struct {
    uvc_context_t *ctx;
    uvc_device_handle_t *devh;
    uvc_stream_ctrl_t ctrl;
    int streaming;          /* 1 = Y16 stream active */
    struct ipolar_frame_store frames;
    int frames_initialized;
} g_ip;

/* libuvc frame callback: bounded copy of the latest Y16 frame. */
static void ipolar_frame_cb(struct uvc_frame *frame, void *user_ptr)
{
    (void)user_ptr;
    if (frame == NULL || frame->data == NULL || !g_ip.frames_initialized ||
        frame->frame_format != UVC_FRAME_FORMAT_GRAY16 ||
        frame->height != IPOLAR_HEIGHT ||
        (frame->width != IPOLAR_MIN_WIDTH && frame->width != IPOLAR_MAX_WIDTH))
        return;

    /* libuvc may pad rows. The store validates data_bytes against the complete
     * source span and publishes a tightly-packed immutable Y16 frame. */
    (void)ipolar_frame_store_publish(&g_ip.frames, frame->data,
                                     frame->data_bytes, frame->width,
                                     frame->height, frame->step);
}

int ipolar_adapter_init(void)
{
    if (g_ip.ctx != NULL) {
        return 0; /* idempotent */
    }
    int result = ipolar_frame_store_init(&g_ip.frames, IPOLAR_MAX_FRAME_BYTES);
    if (result < 0)
        return result;
    g_ip.frames_initialized = 1;
    uvc_error_t rc = uvc_init(&g_ip.ctx, NULL);
    if (rc < 0) {
        g_ip.ctx = NULL; /* fail-closed: no partial state */
        (void)ipolar_frame_store_destroy(&g_ip.frames);
        g_ip.frames_initialized = 0;
        return rc;
    }
    return 0;
}

int ipolar_adapter_open(uint16_t vid, uint16_t pid)
{
    if (vid != IPOLAR_VID || pid != IPOLAR_PID) return -EINVAL;
    if (g_ip.ctx == NULL) return -ENODEV;
    if (g_ip.devh != NULL) return -EBUSY;
    uvc_device_t *dev = NULL;
    uvc_error_t rc = uvc_find_device(g_ip.ctx, &dev, (int)vid, (int)pid, NULL);
    if (rc < 0 || dev == NULL)
        return (rc < 0) ? rc : -ENODEV;
    rc = uvc_open(dev, &g_ip.devh);
    if (rc < 0 || g_ip.devh == NULL) {
        g_ip.devh = NULL; /* fail-closed */
        uvc_unref_device(dev);
        return (rc < 0) ? rc : -ENODEV;
    }
    uvc_unref_device(dev); /* uvc_find_device takes a ref; release after open */
    return 0;
}

void ipolar_adapter_close(void)
{
    if (g_ip.devh != NULL) {
        if (g_ip.streaming) {
            uvc_stop_streaming(g_ip.devh);
            g_ip.streaming = 0;
        }
        uvc_close(g_ip.devh);
        g_ip.devh = NULL;
    }
    if (g_ip.frames_initialized)
        ipolar_frame_store_invalidate(&g_ip.frames); /* no stale generation after close */
}

/* Release the context + sink buffer (call once at teardown). */
int ipolar_adapter_exit(void)
{
    if (g_ip.devh != NULL) {
        ipolar_adapter_close();
    }
    if (g_ip.ctx != NULL) {
        uvc_exit(g_ip.ctx);
        g_ip.ctx = NULL;
    }
    if (g_ip.frames_initialized) {
        int rc = ipolar_frame_store_destroy(&g_ip.frames);
        if (rc < 0) return rc; /* preserve state while consumers still lease */
        g_ip.frames_initialized = 0;
    }
    return 0;
}

/* Reconnect path: bounded close + reopen (identity resets via generation). */
int ipolar_adapter_reconnect(uint16_t vid, uint16_t pid)
{
    ipolar_adapter_close();
    return ipolar_adapter_open(vid, pid);
}

/* Start bounded Y16 streaming (640x960 default; 1280x960 supported).
 * Idempotent: a second call while streaming is active is a no-op. */
int ipolar_adapter_stream_y16(void)
{
    if (g_ip.devh == NULL) return -ENODEV;
    if (g_ip.streaming) return 0; /* idempotent */
    if (!g_ip.frames_initialized) return -EINVAL;
    /* Y16 = 16-bit greyscale (UVC_FRAME_FORMAT_GRAY16 in libuvc 0.0.8).
     * The measured iPolar descriptor interval is about 1.8 fps at 640x960;
     * requesting 30 fps cannot match its discrete frame-interval descriptor.
     * libuvc 0.0.8 defines fps=0 as "accept first rate available" for exactly
     * this case, so let the device advertise its supported cadence. */
    uvc_error_t rc = uvc_get_stream_ctrl_format_size(
        g_ip.devh, &g_ip.ctrl, UVC_FRAME_FORMAT_GRAY16, 640, 960, 0);
    if (rc < 0) {
        return rc; /* fail-closed: format not available */
    }
    rc = uvc_start_streaming(g_ip.devh, &g_ip.ctrl, ipolar_frame_cb, NULL, 0);
    if (rc < 0) {
        if (g_ip.frames_initialized)
            ipolar_frame_store_invalidate(&g_ip.frames);
        return rc; /* fail-closed: stream not started */
    }
    g_ip.streaming = 1;
    return 0;
}

/* Exposure/gain controls for obtaining solvable stars (TA #159). */
int ipolar_adapter_set_exposure(uint32_t time_100us)
{
    if (g_ip.devh == NULL) {
        return -1;
    }
    return uvc_set_exposure_abs(g_ip.devh, time_100us);
}

int ipolar_adapter_set_gain(uint16_t gain)
{
    if (g_ip.devh == NULL) {
        return -1;
    }
    return uvc_set_gain(g_ip.devh, gain);
}

/* Lease/release API: callers must release a view; reconnect invalidates its
 * session generation, but the leased bytes remain immutable until release. */
int ipolar_adapter_acquire_latest(struct ipolar_frame_view *view)
{
    if (!g_ip.frames_initialized) return -1;
    return ipolar_frame_store_acquire(&g_ip.frames, view);
}

int ipolar_adapter_release_frame(struct ipolar_frame_view *view)
{
    return ipolar_frame_view_release(view);
}

int ipolar_adapter_frame_is_current(const struct ipolar_frame_view *view)
{
    return ipolar_frame_view_is_current(view);
}
