/* #158 StarShoot hardware discriminator — host-side harness.
 * Bounds the expected device handshake against the attached
 * 16c0:29a0 camera using the adapter's proposed transfer encoding
 * (stage2_starshoot_adapter.c ss_transfer_opcode): a 4-byte opcode word
 * over a class OUT control request (bRequest 0x41, value = opcode).
 *
 * Steps (all fail-closed, bounded timeouts):
 *   1. enumerate + open 16c0:29a0, claim iface 0, select alt 1 (bulk)
 *   2. IS_CAMARA_INIT handshake (opcode 1), only with explicit --probe-init
 * No guessed commands or bulk reads are issued: without a validated stream
 * command, arbitrary payload bytes cannot be classified as a camera frame.
 * Exit codes: 0 = proposed init request transferred, 2 = open/claim only,
 *             3 = device not found, 4 = open failed.
 */
#include <libusb-1.0/libusb.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SS_VID 0x16c0
#define SS_PID 0x29a0
#define EP_CMD_OUT 0x01
#define EP_BULK_IN 0x81

static int probe_control(libusb_device_handle *dev, uint8_t reqtype,
                         uint8_t brequest, uint16_t value, const char *label)
{
    uint8_t buf[4] = { (uint8_t)(value & 0xff), (uint8_t)((value >> 8) & 0xff), 0, 0 };
    int rc = libusb_control_transfer(dev, reqtype, brequest, value, 0,
                                     buf, sizeof(buf), 2000);
    printf("  probe %-46s rc=%d (%s)\n", label, rc,
           rc == (int)sizeof(buf) ? "accepted (4-byte command sent)"
           : rc >= 0 ? "short command transfer" : libusb_error_name(rc));
    return rc;
}

int main(int argc, char **argv)
{
    int probe_init = argc == 2 && strcmp(argv[1], "--probe-init") == 0;
    if (argc > 1 && !probe_init) {
        fprintf(stderr, "usage: %s [--probe-init]\n", argv[0]);
        return 4;
    }
    libusb_context *ctx = NULL;
    if (libusb_init(&ctx) != LIBUSB_SUCCESS) {
        printf("DISCRIMINATOR: FAIL — libusb_init\n");
        return 4;
    }
    libusb_set_debug(ctx, LIBUSB_LOG_LEVEL_INFO);

    struct libusb_device **list = NULL;
    ssize_t count = libusb_get_device_list(ctx, &list);
    if (count < 0) {
        printf("DISCRIMINATOR: FAIL — enumeration\n");
        return 4;
    }
    struct libusb_device *found = NULL;
    for (ssize_t i = 0; i < count; i++) {
        struct libusb_device_descriptor d;
        if (libusb_get_device_descriptor(list[i], &d) != LIBUSB_SUCCESS) continue;
        if (d.idVendor == SS_VID && d.idProduct == SS_PID) { found = list[i]; break; }
    }
    libusb_free_device_list(list, 1);
    if (found == NULL) {
        printf("DISCRIMINATOR: FAIL — 16c0:29a0 not enumerated\n");
        return 3;
    }

    libusb_device_handle *dev = NULL;
    if (libusb_open(found, &dev) != LIBUSB_SUCCESS) {
        printf("DISCRIMINATOR: FAIL — open (permissions? try udev rule / root)\n");
        return 4;
    }
    int claimed = libusb_claim_interface(dev, 0);
    if (claimed != LIBUSB_SUCCESS) {
        printf("DISCRIMINATOR: FAIL — claim iface 0 rc=%d (%s)\n",
               claimed, libusb_error_name(claimed));
        return 4;
    }
    int alt = libusb_set_interface_alt_setting(dev, 0, 1);
    printf("open+claim OK; alt 1 (bulk) rc=%d (%s)\n", alt, libusb_error_name(alt));
    int result = 2;
    if (probe_init && alt == LIBUSB_SUCCESS) {
        /* This request remains a hypothesis, not a validated protocol. */
        int rc = probe_control(dev, LIBUSB_ENDPOINT_OUT | LIBUSB_REQUEST_TYPE_CLASS,
                               0x41, 1, "proposed IS_CAMARA_INIT class OUT");
        if (rc == 4) result = 0;
    }
    printf("DISCRIMINATOR: %s\n", result == 0
           ? "PROVISIONAL — four request bytes transferred; camera acceptance unproven"
           : "PARTIAL — device opened; no validated frame protocol");

    libusb_release_interface(dev, 0);
    libusb_close(dev);
    libusb_exit(ctx);
    return (alt != LIBUSB_SUCCESS && result == 2) ? 4 : result;
}
