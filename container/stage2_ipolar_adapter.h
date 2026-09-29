/* #159 iPolar adapter interface — userspace libuvc path.
 * No upstream uvc-devices.c; adapter defines VID/PID and stream modes.
 * TA direction (#159): bounded Y16 frames -> common camera-source interface
 * -> plate solve (source-agnostic). This layer: frame acquisition, identity/
 * generation, reconnect, exposure/gain controls.
 */
#ifndef STAGE2_IPOLAR_ADAPTER_H
#define STAGE2_IPOLAR_ADAPTER_H

#include <stdint.h>
#include "stage2_ipolar_frames.h"

#define IPOLAR_VID 0x1233
#define IPOLAR_PID 0x1455

int  ipolar_adapter_init(void);
int  ipolar_adapter_exit(void);
int  ipolar_adapter_open(uint16_t vid, uint16_t pid);
void ipolar_adapter_close(void);
int  ipolar_adapter_reconnect(uint16_t vid, uint16_t pid);
int  ipolar_adapter_stream_y16(void);
int  ipolar_adapter_set_exposure(uint32_t time_100us);
int  ipolar_adapter_set_gain(uint16_t gain);
int  ipolar_adapter_acquire_latest(struct ipolar_frame_view *view);
int  ipolar_adapter_release_frame(struct ipolar_frame_view *view);
int  ipolar_adapter_frame_is_current(const struct ipolar_frame_view *view);

#endif /* STAGE2_IPOLAR_ADAPTER_H */
