/* #159 iPolar adapter interface — userspace libuvc path.
 * No upstream uvc-devices.c; adapter defines VID/PID and stream modes.
 * TA direction (#159): bounded Y16 frames -> common camera-source interface
 * -> plate solve (source-agnostic). This layer: frame acquisition, identity/
 * generation, reconnect, exposure/gain controls.
 */
#ifndef STAGE2_IPOLAR_ADAPTER_H
#define STAGE2_IPOLAR_ADAPTER_H

#include <stdint.h>

#define IPOLAR_VID 0x1233
#define IPOLAR_PID 0x1455

/* Bounded latest-frame sink (Y16, up to 1280x960). */
struct ipolar_frame_sink {
    uint8_t *data;      /* owned buffer, width*height*2 bytes */
    uint32_t width;
    uint32_t height;
    uint32_t size;      /* bytes in the latest frame */
    uint64_t generation; /* monotonic per-frame identity */
    int have_frame;
};

void ipolar_adapter_init(void);
void ipolar_adapter_exit(void);
void ipolar_adapter_open(uint16_t vid, uint16_t pid);
void ipolar_adapter_close(void);
void ipolar_adapter_reconnect(uint16_t vid, uint16_t pid);
void ipolar_adapter_stream_y16(void);
int  ipolar_adapter_set_exposure(uint32_t time_100us);
int  ipolar_adapter_set_gain(uint16_t gain);
const struct ipolar_frame_sink *ipolar_adapter_latest_frame(void);

#endif /* STAGE2_IPOLAR_ADAPTER_H */
