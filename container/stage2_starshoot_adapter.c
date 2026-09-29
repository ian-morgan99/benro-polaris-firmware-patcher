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

/* Vendor-protocol command opcodes (SDK opcode table, qhyccdcamdef.h). */
enum ss_opcode {
    SS_OP_RESET_USB_PIPE     = 1,
    SS_OP_IS_CAMARA_INIT     = 1, /* SDK: IS_CAMARA_INIT(1) */
    SS_OP_IS_CAMARA_OPEN     = 2,
    SS_OP_IS_CAMARA_CLOSE    = 3,
    SS_OP_GET_IMAGE_TIMEOUT  = 6,
    SS_OP_GET_SINGLEPICTURE  = 7,
    SS_OP_GET_LIVEPICTURE    = 8
};

/* Bounded command transfer: one bulk control write of the opcode word.
 * Returns 0 on success, negative libusb error code otherwise (fail-closed). */
static int ss_transfer_opcode(struct starshoot_adapter *a, uint16_t opcode)
{
    if (!a->dev) {
        return LIBUSB_ERROR_NOT_FOUND; /* fail-closed: no open handle */
    }
    uint8_t buf[4];
    buf[0] = (uint8_t)(opcode & 0xff);
    buf[1] = (uint8_t)((opcode >> 8) & 0xff);
    buf[2] = 0; /* payload length (low) */
    buf[3] = 0; /* payload length (high) */
    int rc = libusb_control_transfer(a->dev,
                                     LIBUSB_ENDPOINT_OUT | LIBUSB_REQUEST_TYPE_CLASS,
                                     0x41, /* vendor request (SDK-style) */
                                     opcode, 0, buf, (uint16_t)sizeof(buf), 2000);
    if (rc < 0)
        return rc;
    /* libusb returns the number of payload bytes transferred. A zero-byte
     * status is not proof that this four-byte command reached the camera. */
    return (rc == (int)sizeof(buf)) ? 0 : LIBUSB_ERROR_IO;
}

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

/* Provisional protocol probe. A full 4-byte transfer only proves that the
 * host sent the proposed request; device acceptance and image capture remain
 * unproven until a response and validated frame are implemented. */
int starshoot_adapter_probe_init(void)
{
    return ss_transfer_opcode(&g_ss, SS_OP_IS_CAMARA_INIT);
}
