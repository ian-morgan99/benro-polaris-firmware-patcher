/* #158 Orion StarShoot All-in-One (16c0:29a0) adapter — vendor-protocol (libusb).
 * NOT a libgphoto2 camlib (2.5.34 has no uvc/ camlib; #151 ownership layer).
 * Protocol: QHY5L-II / INDI-style vendor-protocol (bulk + isochronous endpoints).
 */
#include <stdint.h>
#include <usb.h>  /* libusb — vendor-protocol backend */
void starshoot_adapter_init(void) { libusb_init(NULL); }
void starshoot_adapter_open(uint16_t vid, uint16_t pid) { /* libusb_open(vid,pid) */ }
void starshoot_adapter_stream_bulk_iso(void) { /* bulk (alt 1) + isochronous (alt 3) */ }
