/* #158 QHY5L-II (16c0:29a0) adapter skeleton — vendor-protocol path.
 * NOT a complete libgphoto2 camlib; adapter interface only (per adapter contract).
 * SDK command mapping (from Temp/sdk_WinMix_20.06.26.zip qhyccd.h / qhyccdcamdef.h):
 *   DEVICETYPE_QHY5LII_M (3002) / QHY5LII_C (3003)
 *   SINGLE_MODE (0), LIVE_MODE (1)
 *   IS_CAMARA_INIT (1), OPEN (2), CLOSE (3)
 *   GET_SINGLEPICTURE (7), GET_LIVEPICTURE (8)
 * Path: libusb (bulk alt 1 / isochronous alt 3) -> adapter -> OpenPolaris (#151).
 */
#ifndef STAGE2_QHY5LII_ADAPTER_H
#define STAGE2_QHY5LII_ADAPTER_H
#define QHY5LII_VID 0x16c0
#define QHY5LII_PID 0x29a0
/* Adapter interface (item 4) — to be wired to libusb backend + libgphoto2. */
#endif
