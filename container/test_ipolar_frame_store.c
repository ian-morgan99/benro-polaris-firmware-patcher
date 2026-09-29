#include "stage2_ipolar_frames.h"

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(condition) do { \
    if (!(condition)) { \
        fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
        return 1; \
    } \
} while (0)

static void make_frame(uint8_t frame[10], uint8_t base)
{
    frame[0] = base; frame[1] = base + 1; frame[2] = base + 2; frame[3] = base + 3;
    frame[4] = 0xee; frame[5] = 0xee; /* row padding must not be published */
    frame[6] = base + 4; frame[7] = base + 5; frame[8] = base + 6; frame[9] = base + 7;
}

int main(void)
{
    struct ipolar_frame_store store;
    struct ipolar_frame_view a, b, c, d, short_frame;
    uint8_t src[10];
    CHECK(ipolar_frame_store_init(&store, 16) == 0);
    CHECK(ipolar_frame_store_acquire(&store, &short_frame) == 0);

    make_frame(src, 10);
    CHECK(ipolar_frame_store_publish(&store, src, sizeof(src) - 1, 2, 2, 6) == -EMSGSIZE);
    CHECK(ipolar_frame_store_publish(&store, src, sizeof(src), 2, 2, 3) == -EINVAL);
    CHECK(ipolar_frame_store_publish(&store, src, sizeof(src), 2, 2, 6) == 1);
    CHECK(ipolar_frame_store_acquire(&store, &a) == 1);
    CHECK(a.width == 2 && a.height == 2 && a.size == 8);
    CHECK(a.data[0] == 10 && a.data[3] == 13 && a.data[4] == 14 && a.data[7] == 17);
    CHECK(ipolar_frame_view_is_current(&a) == 1);

    make_frame(src, 20);
    CHECK(ipolar_frame_store_publish(&store, src, sizeof(src), 2, 2, 6) == 1);
    CHECK(ipolar_frame_store_acquire(&store, &b) == 1);
    make_frame(src, 30);
    CHECK(ipolar_frame_store_publish(&store, src, sizeof(src), 2, 2, 6) == 1);
    CHECK(ipolar_frame_store_acquire(&store, &c) == 1);
    make_frame(src, 40);
    CHECK(ipolar_frame_store_publish(&store, src, sizeof(src), 2, 2, 6) == 0);
    CHECK(a.data[0] == 10 && b.data[0] == 20 && c.data[0] == 30);

    CHECK(ipolar_frame_view_release(&b) == 0);
    CHECK(ipolar_frame_store_publish(&store, src, sizeof(src), 2, 2, 6) == 1);
    CHECK(ipolar_frame_store_acquire(&store, &d) == 1);
    CHECK(d.data[0] == 40);
    CHECK(ipolar_frame_store_destroy(&store) == -EBUSY);

    ipolar_frame_store_invalidate(&store);
    CHECK(ipolar_frame_view_is_current(&a) == 0);
    CHECK(ipolar_frame_store_acquire(&store, &short_frame) == 0);
    CHECK(ipolar_frame_view_release(&a) == 0);
    CHECK(ipolar_frame_view_release(&c) == 0);
    CHECK(ipolar_frame_view_release(&d) == 0);
    CHECK(ipolar_frame_store_destroy(&store) == 0);
    puts("iPolar frame store bounds, immutable leases, and reconnect generation PASS");
    return 0;
}
