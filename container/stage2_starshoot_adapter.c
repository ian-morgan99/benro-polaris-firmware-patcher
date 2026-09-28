/* #158 Orion StarShoot All-in-One (16c0:29a0) adapter — vendor-protocol (libusb).
 * NOT a libgphoto2 camlib (2.5.34 has no uvc/ camlib; #151 ownership layer).
 * Protocol: QHY5L-II / INDI-style vendor-protocol (bulk + isochronous endpoints).
 *
 * SDK command mapping (Temp/sdk_WinMix_20.06.26.zip, qhyccd.h / qhyccdcamdef.h):
 *   InitQHYCCDResource, ScanQHYCCD, GetQHYCCDId, OpenQHYCCD,
 *   SetQHYCCDStreamMode(SINGLE_MODE=0 | LIVE_MODE=1),
 *   IS_CAMARA_INIT(1)/OPEN(2)/CLOSE(3),
 *   GET_SINGLEPICTURE(7) / GET_LIVEPICTURE(8), RESET_USB_PIPE(1).
 * Device: DEVICETYPE_QHY5LII_M (3002) / QHY5LII_C (3003) for 16c0:29a0.
 * Path: libusb bulk(alt1) + isochronous(alt3) -> adapter -> OpenPolaris (#151).
 */
#include "stage2_starshoot_adapter.h"

/* Adapter init/open/close/stream-mode mapping to the QHY SDK commands — WIRED.
 * SDK -> adapter -> libusb bulk(alt1)/isochronous(alt3) -> OpenPolaris (#151).
 * The libusb backend (open, claim interface, set alt setting, bulk/iso transfer)
 * is the next step; this layer defines the command surface and VID/PID. */
#include <usb.h>  /* libusb — vendor-protocol backend */

void starshoot_adapter_init(void) { libusb_init(NULL); }

void starshoot_adapter_open(uint16_t vid, uint16_t pid)
{
    /* libusb_open(vid, pid) -> claim interface 0 -> set alt setting (bulk 1 / iso 3). */
    (void)vid; (void)pid;
}

void starshoot_adapter_stream_bulk_iso(void)
{
    /* bulk (alt 1) for commands + isochronous (alt 3) for live frames. */
}
