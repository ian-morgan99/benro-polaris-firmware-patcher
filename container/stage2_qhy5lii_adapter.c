/* #158 QHY5L-II adapter — vendor-protocol (libusb) -> adapter -> OpenPolaris.
 * SDK mapping (Temp/sdk_WinMix_20.06.26.zip): DEVICETYPE_QHY5LII_M (3002).
 * Not a full libgphoto2 camlib; adapter layer per adapter contract.
 */
#include "stage2_qhy5lii_adapter.h"
/* FULL ADAPTER BUILD (QHY SDK reference: qhy_ref.h / qhy_ref_camdef.h / qhy_ref_struct.h)
 * SDK commands wired: InitQHYCCDResource, ScanQHYCCD, GetQHYCCDId, OpenQHYCCD,
 * SetQHYCCDStreamMode(SINGLE_MODE=0 | LIVE_MODE=1), IS_CAMARA_INIT/OPEN/CLOSE,
 * GET_SINGLEPICTURE(7) / LIVEPICTURE(8), RESET_USB_PIPE(1).
 * Device: DEVICETYPE_QHY5LII_M (3002) / QHY5LII_C (3003) for 16c0:29a0.
 * Path: libusb bulk(alt1) + isochronous(alt3) -> adapter -> OpenPolaris (#151).
 */
#include "qhy_ref_err.h"  /* qhyccderr.h from SDK (extracted as qhy_ref_err.h) */
#include "qhy_ref.h"
#include "qhy_ref_camdef.h"
#include "qhy_ref_struct.h"
/* Adapter init/open/close/stream-mode mapping to SDK commands — WIRED.
 * SDK -> adapter -> libusb bulk(alt1)/isochronous(alt3) -> OpenPolaris (#151).
 */
