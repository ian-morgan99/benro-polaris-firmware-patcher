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
 *
 * TA review note (issue #158, 2026-09-28): this layer is classified as
 * skeleton/interface work. A successful build proves API/ABI integration only,
 * not camera I/O. Before calling the backend "wired": bounded open/claim/
 * cleanup and transfer error paths (implemented below) plus a hardware
 * discriminator that proves the expected device handshake and one frame from
 * the attached 16c0:29a0 camera (still owed — needs the device on the bench).
 */
#include "stage2_starshoot_adapter.h"

#include <libusb-1.0/libusb.h>  /* libusb — vendor-protocol backend */
#include <stddef.h>

/* Bounded adapter state: one context, one handle, one claimed interface.
 * All paths are fail-closed: on error the handle is released and the context
 * is only freed after a successful open (no leak on failed open). */
struct starshoot_adapter {
    libusb_context *ctx;
    libusb_device_handle *dev;
    int claimed_iface;      /* -1 = not claimed */
};

static struct starshoot_adapter g_ss = { .claimed_iface = -1 };

int starshoot_adapter_init(void)
{
    if (g_ss.ctx != NULL) {
        return 0; /* idempotent */
    }
    int rc = libusb_init(&g_ss.ctx);
    if (rc != LIBUSB_SUCCESS) {
        if (g_ss.ctx != NULL)
            libusb_exit(g_ss.ctx);
        g_ss.ctx = NULL; /* fail-closed: no partial state */
        return rc;
    }
    g_ss.claimed_iface = -1;
    return 0;
}

int starshoot_adapter_open(uint16_t vid, uint16_t pid)
{
    if (g_ss.ctx == NULL)
        return LIBUSB_ERROR_OTHER;
    if (g_ss.dev != NULL)
        return LIBUSB_ERROR_BUSY; /* bounded single handle */
    if (vid != STARSHOOT_VID || pid != STARSHOOT_PID)
        return LIBUSB_ERROR_INVALID_PARAM;

    struct libusb_device **list = NULL;
    ssize_t count = libusb_get_device_list(g_ss.ctx, &list);
    if (count < 0 || list == NULL) {
        if (list != NULL)
            libusb_free_device_list(list, 1);
        return (count < 0) ? (int)count : LIBUSB_ERROR_OTHER;
    }
    int result = LIBUSB_ERROR_NO_DEVICE;
    for (ssize_t i = 0; i < count && g_ss.dev == NULL; i++) {
        struct libusb_device_descriptor desc;
        if (libusb_get_device_descriptor(list[i], &desc) != LIBUSB_SUCCESS) {
            continue;
        }
        if (desc.idVendor == vid && desc.idProduct == pid) {
            int rc = libusb_open(list[i], &g_ss.dev);
            if (rc != LIBUSB_SUCCESS) {
                g_ss.dev = NULL; /* fail-closed */
                result = rc;
                break;
            }

            /* Commands require the measured bulk alternate setting. Fail
             * closed if either ownership or interface selection fails. */
            rc = libusb_claim_interface(g_ss.dev, 0);
            if (rc != LIBUSB_SUCCESS) {
                result = rc;
                libusb_close(g_ss.dev);
                g_ss.dev = NULL;
                break;
            }
            g_ss.claimed_iface = 0;
            rc = libusb_set_interface_alt_setting(g_ss.dev, 0, 1);
            if (rc != LIBUSB_SUCCESS) {
                result = rc;
                (void)libusb_release_interface(g_ss.dev, g_ss.claimed_iface);
                g_ss.claimed_iface = -1;
                libusb_close(g_ss.dev);
                g_ss.dev = NULL;
                break;
            }
            result = LIBUSB_SUCCESS;
        }
    }
    libusb_free_device_list(list, 1);
    return result;
}

int starshoot_adapter_close(void)
{
    int result = LIBUSB_SUCCESS;
    if (g_ss.dev != NULL) {
        /* Bounded cleanup: release the claimed interface, then the handle. */
        if (g_ss.claimed_iface >= 0) {
            result = libusb_release_interface(g_ss.dev, g_ss.claimed_iface);
            g_ss.claimed_iface = -1;
        }
        libusb_close(g_ss.dev);
        g_ss.dev = NULL;
    }
    return result;
}

int starshoot_adapter_exit(void)
{
    int result = starshoot_adapter_close();
    if (g_ss.ctx != NULL) {
        libusb_exit(g_ss.ctx);
        g_ss.ctx = NULL;
    }
    g_ss.claimed_iface = -1;
    return result;
}

/* The former implementation sent a guessed class request (0x41). Static
 * inspection of the archived vendor qhy5dll.dll found no such request; its
 * observed vendor requests are 0x10, 0x11, 0x18, 0x21, 0x22, 0x25, 0x26 and
 * 0x55. Do not send any of those until the exact post-firmware 29a1 sequence
 * is validated against the camera and a frame can be checked. */
int starshoot_adapter_probe_init(void)
{
    return LIBUSB_ERROR_NOT_SUPPORTED;
}
