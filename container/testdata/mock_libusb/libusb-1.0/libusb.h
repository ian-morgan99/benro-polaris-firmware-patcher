#ifndef TEST_MOCK_LIBUSB_H
#define TEST_MOCK_LIBUSB_H

#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>

#define LIBUSB_SUCCESS 0
#define LIBUSB_ERROR_IO -1
#define LIBUSB_ERROR_INVALID_PARAM -2
#define LIBUSB_ERROR_ACCESS -3
#define LIBUSB_ERROR_NO_DEVICE -4
#define LIBUSB_ERROR_NOT_FOUND -5
#define LIBUSB_ERROR_BUSY -6
#define LIBUSB_ERROR_OTHER -99
#define LIBUSB_ERROR_NOT_SUPPORTED -12
#define LIBUSB_ENDPOINT_OUT 0x00
#define LIBUSB_REQUEST_TYPE_CLASS (0x01u << 5)

typedef struct libusb_context { int unused; } libusb_context;
typedef struct libusb_device { int unused; } libusb_device;
typedef struct libusb_device_handle { int unused; } libusb_device_handle;
struct libusb_device_descriptor { uint16_t idVendor, idProduct; };

int libusb_init(libusb_context **ctx);
void libusb_exit(libusb_context *ctx);
ssize_t libusb_get_device_list(libusb_context *ctx, libusb_device ***list);
void libusb_free_device_list(libusb_device **list, int unref_devices);
int libusb_get_device_descriptor(libusb_device *dev,
                                 struct libusb_device_descriptor *desc);
int libusb_open(libusb_device *dev, libusb_device_handle **devh);
int libusb_claim_interface(libusb_device_handle *devh, int iface);
int libusb_set_interface_alt_setting(libusb_device_handle *devh,
                                     int iface, int altsetting);
int libusb_release_interface(libusb_device_handle *devh, int iface);
void libusb_close(libusb_device_handle *devh);
int libusb_control_transfer(libusb_device_handle *devh, uint8_t request_type,
        uint8_t request, uint16_t value, uint16_t index,
        unsigned char *data, uint16_t length, unsigned int timeout);

#endif
