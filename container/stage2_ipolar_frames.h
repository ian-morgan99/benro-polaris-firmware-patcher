#ifndef STAGE2_IPOLAR_FRAMES_H
#define STAGE2_IPOLAR_FRAMES_H

#include <stddef.h>
#include <stdint.h>
#include <pthread.h>

#define IPOLAR_FRAME_SLOT_COUNT 3

struct ipolar_frame_store {
    pthread_mutex_t mutex;
    uint8_t *buffers[IPOLAR_FRAME_SLOT_COUNT];
    size_t capacity;
    size_t sizes[IPOLAR_FRAME_SLOT_COUNT];
    uint32_t widths[IPOLAR_FRAME_SLOT_COUNT];
    uint32_t heights[IPOLAR_FRAME_SLOT_COUNT];
    uint32_t references[IPOLAR_FRAME_SLOT_COUNT];
    uint64_t generations[IPOLAR_FRAME_SLOT_COUNT];
    uint64_t session_generation;
    uint64_t next_generation;
    int published_slot;
    int initialized;
};

struct ipolar_frame_view {
    const uint8_t *data;
    size_t size;
    uint32_t width;
    uint32_t height;
    uint64_t generation;
    uint64_t session_generation;
    unsigned slot;
    struct ipolar_frame_store *store;
};

int ipolar_frame_store_init(struct ipolar_frame_store *store, size_t capacity);
int ipolar_frame_store_publish(struct ipolar_frame_store *store,
                               const uint8_t *data, size_t data_bytes,
                               uint32_t width, uint32_t height,
                               uint32_t source_stride);
int ipolar_frame_store_acquire(struct ipolar_frame_store *store,
                               struct ipolar_frame_view *view);
int ipolar_frame_view_release(struct ipolar_frame_view *view);
int ipolar_frame_view_is_current(const struct ipolar_frame_view *view);
void ipolar_frame_store_invalidate(struct ipolar_frame_store *store);
int ipolar_frame_store_destroy(struct ipolar_frame_store *store);

#endif
