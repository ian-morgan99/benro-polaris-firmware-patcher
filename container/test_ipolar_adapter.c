#include "stage2_ipolar_adapter.h"
#include <libuvc/libuvc.h>

#include <stdio.h>
#include <stdlib.h>

#define CHECK(condition) do { \
    if (!(condition)) { \
        fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
        return 1; \
    } \
} while (0)

static uvc_context_t test_ctx;
static uvc_device_t test_device;
static uvc_device_handle_t test_handle;
static int selected_fps = -1;
static int stream_starts;
static int stream_stops;
static int exposure_value;
static int gain_value;
static uint8_t *frame_data;
static int find_error;
static int open_error;
static int stream_error;

uvc_error_t uvc_init(uvc_context_t **ctx, void *usb_ctx)
{
    (void)usb_ctx;
    *ctx = &test_ctx;
    return 0;
}

void uvc_exit(uvc_context_t *ctx) { (void)ctx; }

uvc_error_t uvc_find_device(uvc_context_t *ctx, uvc_device_t **dev,
                            int vid, int pid, const char *serial)
{
    (void)ctx; (void)serial;
    if (find_error) return find_error;
    if (vid != IPOLAR_VID || pid != IPOLAR_PID) return -1;
    *dev = &test_device;
    return 0;
}

void uvc_unref_device(uvc_device_t *dev) { (void)dev; }

uvc_error_t uvc_open(uvc_device_t *dev, uvc_device_handle_t **devh)
{
    (void)dev;
    if (open_error) return open_error;
    *devh = &test_handle;
    return 0;
}

void uvc_close(uvc_device_handle_t *devh) { (void)devh; }
void uvc_stop_streaming(uvc_device_handle_t *devh)
{
    (void)devh;
    ++stream_stops;
}

uvc_error_t uvc_get_stream_ctrl_format_size(uvc_device_handle_t *devh,
        uvc_stream_ctrl_t *ctrl, enum uvc_frame_format format,
        int width, int height, int fps)
{
    (void)devh; (void)ctrl;
    if (format != UVC_FRAME_FORMAT_YUYV || width != 1280 || height != 960)
        return -1;
    selected_fps = fps;
    /* libuvc 0.0.8 uses zero to accept a discrete device-advertised rate. */
    return fps == 0 ? 0 : -1;
}

uvc_error_t uvc_start_streaming(uvc_device_handle_t *devh,
        uvc_stream_ctrl_t *ctrl, uvc_frame_callback_t *callback,
        void *user_ptr, uint8_t flags)
{
    (void)devh; (void)ctrl; (void)flags;
    ++stream_starts;
    if (stream_error) return stream_error;
    struct uvc_frame frame = {
        .data = frame_data,
        .frame_format = UVC_FRAME_FORMAT_YUYV,
        .width = 1280,
        .height = 960,
        .data_bytes = 1280u * 960u * 2u,
        .step = 1280u * 2u
    };
    callback(&frame, user_ptr);
    return 0;
}

uvc_error_t uvc_set_exposure_abs(uvc_device_handle_t *devh, uint32_t value)
{
    (void)devh;
    exposure_value = (int)value;
    return 0;
}

uvc_error_t uvc_set_gain(uvc_device_handle_t *devh, uint16_t value)
{
    (void)devh;
    gain_value = (int)value;
    return 0;
}

int main(void)
{
    struct ipolar_frame_view view;
    frame_data = calloc(1280u * 960u, 2u);
    CHECK(frame_data != NULL);
    frame_data[0] = 0x34;
    frame_data[1] = 0x12;

    CHECK(ipolar_adapter_init() == 0);
    CHECK(ipolar_adapter_open(0x1234, IPOLAR_PID) < 0); /* identity gate */
    CHECK(ipolar_adapter_open(IPOLAR_VID, IPOLAR_PID) == 0);
    CHECK(ipolar_adapter_set_exposure(1234) == 0 && exposure_value == 1234);
    CHECK(ipolar_adapter_set_gain(17) == 0 && gain_value == 17);
    CHECK(ipolar_adapter_stream_yuyv() == 0);
    CHECK(ipolar_adapter_stream_yuyv() == 0);
    CHECK(selected_fps == 0);
    CHECK(stream_starts == 1); /* already-active stream is idempotent */
    CHECK(ipolar_adapter_acquire_latest(&view) == 1);
    CHECK(view.width == 1280 && view.height == 960);
    CHECK(view.size == 1280u * 960u * 2u);
    CHECK(view.data[0] == 0x34 && view.data[1] == 0x12);
    CHECK(ipolar_adapter_frame_is_current(&view) == 1);

    CHECK(ipolar_adapter_reconnect(IPOLAR_VID, IPOLAR_PID) == 0);
    CHECK(ipolar_adapter_frame_is_current(&view) == 0);
    CHECK(ipolar_adapter_release_frame(&view) == 0);
    CHECK(ipolar_adapter_stream_yuyv() == 0);
    CHECK(stream_starts == 2);
    ipolar_adapter_close();
    find_error = -7;
    CHECK(ipolar_adapter_open(IPOLAR_VID, IPOLAR_PID) == -7);
    find_error = 0;
    open_error = -8;
    CHECK(ipolar_adapter_open(IPOLAR_VID, IPOLAR_PID) == -8);
    open_error = 0;
    CHECK(ipolar_adapter_open(IPOLAR_VID, IPOLAR_PID) == 0);
    stream_error = -9;
    CHECK(ipolar_adapter_stream_yuyv() == -9);
    stream_error = 0;
    ipolar_adapter_close();
    CHECK(ipolar_adapter_exit() == 0);
    CHECK(stream_stops == 2);
    free(frame_data);
    puts("iPolar adapter negotiates proven YUYV 1280x960, publishes bounded frames, and invalidates on reconnect PASS");
    return 0;
}
