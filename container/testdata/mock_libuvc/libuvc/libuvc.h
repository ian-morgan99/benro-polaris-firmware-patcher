#ifndef TEST_MOCK_LIBUVC_H
#define TEST_MOCK_LIBUVC_H

#include <stddef.h>
#include <stdint.h>

typedef struct { int unused; } uvc_context_t;
typedef struct { int unused; } uvc_device_t;
typedef struct { int unused; } uvc_device_handle_t;
typedef struct { int unused; } uvc_stream_ctrl_t;
typedef int uvc_error_t;

enum uvc_frame_format {
    UVC_FRAME_FORMAT_UNKNOWN = 0,
    UVC_FRAME_FORMAT_GRAY16 = 1
};

struct uvc_frame {
    void *data;
    enum uvc_frame_format frame_format;
    uint32_t width;
    uint32_t height;
    size_t data_bytes;
    uint32_t step;
};

typedef void (uvc_frame_callback_t)(struct uvc_frame *frame, void *user_ptr);

uvc_error_t uvc_init(uvc_context_t **ctx, void *usb_ctx);
void uvc_exit(uvc_context_t *ctx);
uvc_error_t uvc_find_device(uvc_context_t *ctx, uvc_device_t **dev,
                            int vid, int pid, const char *serial);
void uvc_unref_device(uvc_device_t *dev);
uvc_error_t uvc_open(uvc_device_t *dev, uvc_device_handle_t **devh);
void uvc_close(uvc_device_handle_t *devh);
void uvc_stop_streaming(uvc_device_handle_t *devh);
uvc_error_t uvc_get_stream_ctrl_format_size(uvc_device_handle_t *devh,
        uvc_stream_ctrl_t *ctrl, enum uvc_frame_format format,
        int width, int height, int fps);
uvc_error_t uvc_start_streaming(uvc_device_handle_t *devh,
        uvc_stream_ctrl_t *ctrl, uvc_frame_callback_t *callback,
        void *user_ptr, uint8_t flags);
uvc_error_t uvc_set_exposure_abs(uvc_device_handle_t *devh, uint32_t value);
uvc_error_t uvc_set_gain(uvc_device_handle_t *devh, uint16_t value);

#endif
