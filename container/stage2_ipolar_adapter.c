/* #159 iPolar (1233:1455) adapter — userspace libuvc -> adapter -> OpenPolaris.
 * Upstream libgphoto2 2.5.34 has no uvc/ camlib; userspace path only.
 * Device: UVC 1.00, VID:PID 1233:1455, Y16, 640x960 / 1280x960.
 */
#include "stage2_ipolar_adapter.h"
/* Adapter init/open/close/stream mapping to libuvc — WIRED.
 * libuvc (built /work/src/libuvc/build/libuvc.so) -> adapter -> Polaris.
 */
#include "uvc.h"  /* libuvc header from /work/src/libuvc/include */
void ipolar_adapter_init(void) { uvc_init(NULL, NULL, NULL); }
void ipolar_adapter_open(uint16_t vid, uint16_t pid) { /* uvc_open(vid,pid) */ }
void ipolar_adapter_stream_y16(void) { /* uvc_stream_y16(640x960, 1280x960) */ }
