#include "stage2_starshoot_adapter.h"
#include <libusb-1.0/libusb.h>

#include <stdio.h>

#define CHECK(condition) do { \
    if (!(condition)) { \
        fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
        return 1; \
    } \
} while (0)

static libusb_context test_ctx;
static libusb_device test_device;
static libusb_device_handle test_handle;
static libusb_device *test_list[] = { &test_device, NULL };
static int claim_result;
static int alt_result;
static int claims, releases, closes, exits, frees;

int libusb_init(libusb_context **ctx) { *ctx = &test_ctx; return 0; }
void libusb_exit(libusb_context *ctx) { (void)ctx; ++exits; }
ssize_t libusb_get_device_list(libusb_context *ctx, libusb_device ***list)
{
    (void)ctx; *list = test_list; return 1;
}
void libusb_free_device_list(libusb_device **list, int unref_devices)
{
    (void)list; (void)unref_devices; ++frees;
}
int libusb_get_device_descriptor(libusb_device *dev,
                                 struct libusb_device_descriptor *desc)
{
    (void)dev; desc->idVendor = STARSHOOT_VID; desc->idProduct = STARSHOOT_PID;
    return 0;
}
int libusb_open(libusb_device *dev, libusb_device_handle **devh)
{
    (void)dev; *devh = &test_handle; return 0;
}
int libusb_claim_interface(libusb_device_handle *devh, int iface)
{
    (void)devh; (void)iface; ++claims; return claim_result;
}
int libusb_set_interface_alt_setting(libusb_device_handle *devh,
                                     int iface, int altsetting)
{
    (void)devh; (void)iface;
    if (altsetting != 1) return LIBUSB_ERROR_INVALID_PARAM;
    return alt_result;
}
int libusb_release_interface(libusb_device_handle *devh, int iface)
{
    (void)devh; (void)iface; ++releases; return 0;
}
void libusb_close(libusb_device_handle *devh) { (void)devh; ++closes; }
int main(void)
{
    CHECK(starshoot_adapter_init() == 0);
    CHECK(starshoot_adapter_open(0x1233, 0x1455) == LIBUSB_ERROR_INVALID_PARAM);
    CHECK(starshoot_adapter_open(STARSHOOT_VID, STARSHOOT_PID) == 0);
    CHECK(claims == 1 && frees == 1);
    CHECK(starshoot_adapter_probe_init() == LIBUSB_ERROR_NOT_SUPPORTED);
    CHECK(starshoot_adapter_close() == 0);
    CHECK(releases == 1 && closes == 1);

    claim_result = LIBUSB_ERROR_ACCESS;
    CHECK(starshoot_adapter_open(STARSHOOT_VID, STARSHOOT_PID) == LIBUSB_ERROR_ACCESS);
    CHECK(closes == 2 && releases == 1); /* failed claim closes, never releases */
    claim_result = 0;
    alt_result = LIBUSB_ERROR_NOT_FOUND;
    CHECK(starshoot_adapter_open(STARSHOOT_VID, STARSHOOT_PID) == LIBUSB_ERROR_NOT_FOUND);
    CHECK(closes == 3 && releases == 2); /* failed alt selection releases claim */
    CHECK(starshoot_adapter_exit() == 0);
    CHECK(exits == 1);
    puts("StarShoot adapter bounds identity, USB ownership cleanup, and unqualified-protocol refusal PASS");
    return 0;
}
