/* #158 Orion StarShoot All-in-One (16c0:29a0) adapter interface — vendor-protocol.
 * NOT a complete libgphoto2 camlib; adapter interface only (per adapter contract).
 * SDK command mapping (from Temp/sdk_WinMix_20.06.26.zip qhyccd.h / qhyccdcamdef.h):
 *   DEVICETYPE_QHY5LII_M (3002) / QHY5LII_C (3003)
 *   SINGLE_MODE (0), LIVE_MODE (1)
 *   IS_CAMARA_INIT (1), OPEN (2), CLOSE (3)
 *   GET_SINGLEPICTURE (7), GET_LIVEPICTURE (8)
 * Path: libusb (bulk alt 1 / isochronous alt 3) -> adapter -> OpenPolaris (#151).
 */
#ifndef STAGE2_STARSHOOT_ADAPTER_H
#define STAGE2_STARSHOOT_ADAPTER_H

#include <stdint.h>

#define STARSHOOT_VID 0x16c0
#define STARSHOOT_PID 0x29a0

/* QHY SDK device types for the 16c0:29a0 vendor-protocol family. */
#define QHY_DEV_QHY5LII_M 3002
#define QHY_DEV_QHY5LII_C 3003

/* Stream modes (SetQHYCCDStreamMode). */
#define QHY_STREAM_SINGLE_MODE 0
#define QHY_STREAM_LIVE_MODE   1

/* Adapter interface (item 4 of the contract) — wired to libusb backend.
 * Bounded lifecycle: init -> open(vid,pid) [claim iface 0, alt 1] ->
 * stream_bulk_iso() -> close() [release iface, close handle]. Fail-closed. */
void starshoot_adapter_init(void);
void starshoot_adapter_open(uint16_t vid, uint16_t pid);
void starshoot_adapter_close(void);
void starshoot_adapter_stream_bulk_iso(void);

#endif /* STAGE2_STARSHOOT_ADAPTER_H */
