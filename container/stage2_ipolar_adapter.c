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
#include <stdlib.h>
#include <string.h>

/* Bounded frame sink: the latest Y16 frame is copied into a fixed buffer so
 * the streaming callback never outlives its data. Generation counter gives
 * each frame a monotonic identity for the common camera-source interface. */
#define IPOLAR_MAX_FRAME_BYTES (1280 * 960 * 2) /* worst case 1280x960 Y16 */

static struct {
    uvc_context_t *ctx;
    uvc_device_handle_t *devh;
    uvc_stream_ctrl_t ctrl;
    int streaming;          /* 1 = Y16 stream active */
    struct ipolar_frame_sink sink;
} g_ip;

/* libuvc frame callback: bounded copy of the latest Y16 frame. */
static void ipolar_frame_cb(struct uvc_frame *frame, void *user_ptr)
{
    (void)user_ptr;
    if (frame == NULL || frame->data == NULL || g_ip.sink.data == NULL) {
        return; /* fail-closed: drop malformed frame or missing sink buffer */
    }
    uint32_t need = (uint32_t)frame->width * (uint32_t)frame->height * 2u;
    if (need > IPOLAR_MAX_FRAME_BYTES) {
        return; /* bounded: never write past the sink */
    }
    memcpy(g_ip.sink.data, frame->data, need);
    g_ip.sink.width = frame->width;
    g_ip.sink.height = frame->height;
    g_ip.sink.size = need;
    g_ip.sink.generation += 1; /* monotonic identity for the source interface */
    g_ip.sink.have_frame = 1;
}

void ipolar_adapter_init(void)
{
    if (g_ip.ctx != NULL) {
        return; /* idempotent */
    }
    if (uvc_init(&g_ip.ctx, NULL) < 0) {
        g_ip.ctx = NULL; /* fail-closed: no partial state */
        return;
    }
    g_ip.sink.data = malloc(IPOLAR_MAX_FRAME_BYTES);
    if (g_ip.sink.data == NULL) {
        uvc_exit(g_ip.ctx);
        g_ip.ctx = NULL; /* fail-closed: bounded sink is required */
    }
}

void ipolar_adapter_open(uint16_t vid, uint16_t pid)
{
    if (g_ip.ctx == NULL || g_ip.devh != NULL) {
        return; /* not initialized, or already open — bounded single handle */
    }
    uvc_device_t *dev = NULL;
    if (uvc_find_device(g_ip.ctx, &dev, (int)vid, (int)pid, NULL) < 0 || dev == NULL) {
        return; /* fail-closed: device not found */
    }
    if (uvc_open(dev, &g_ip.devh) < 0) {
        g_ip.devh = NULL; /* fail-closed */
    }
    uvc_unref_device(dev); /* uvc_find_device takes a ref; release after open */
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
    g_ip.sink.have_frame = 0; /* bounded: no stale frame after close */
}

/* Release the context + sink buffer (call once at teardown). */
void ipolar_adapter_exit(void)
{
    if (g_ip.devh != NULL) {
        ipolar_adapter_close();
    }
    free(g_ip.sink.data);
    g_ip.sink.data = NULL;
    if (g_ip.ctx != NULL) {
        uvc_exit(g_ip.ctx);
        g_ip.ctx = NULL;
    }
}

/* Reconnect path: bounded close + reopen (identity resets via generation). */
void ipolar_adapter_reconnect(uint16_t vid, uint16_t pid)
{
    ipolar_adapter_close();
    ipolar_adapter_open(vid, pid);
}

/* Start bounded Y16 streaming (640x960 default; 1280x960 supported).
 * Idempotent: a second call while streaming is active is a no-op. */
void ipolar_adapter_stream_y16(void)
{
    if (g_ip.devh == NULL || g_ip.streaming) {
        return; /* fail-closed: no stream without an open device / already on */
    }
    /* Y16 = 16-bit greyscale (UVC_FRAME_FORMAT_GRAY16 in libuvc 0.0.8). */
    uvc_error_t rc = uvc_get_stream_ctrl_format_size(
        g_ip.devh, &g_ip.ctrl, UVC_FRAME_FORMAT_GRAY16, 640, 960, 30);
    if (rc < 0) {
        return; /* fail-closed: format not available */
    }
    rc = uvc_start_streaming(g_ip.devh, &g_ip.ctrl, ipolar_frame_cb, NULL, 0);
    if (rc < 0) {
        g_ip.sink.have_frame = 0;
        return; /* fail-closed: stream not started */
    }
    g_ip.streaming = 1;
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

/* Latest bounded frame for the common camera-source interface. */
const struct ipolar_frame_sink *ipolar_adapter_latest_frame(void)
{
    return g_ip.sink.have_frame ? &g_ip.sink : NULL;
}
