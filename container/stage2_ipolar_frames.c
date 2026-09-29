#include "stage2_ipolar_frames.h"

#include <errno.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>

static pthread_mutex_t *store_mutex(struct ipolar_frame_store *store)
{
    return &store->mutex;
}

static int checked_mul_size(size_t a, size_t b, size_t *out)
{
    if (b != 0 && a > SIZE_MAX / b) return -EOVERFLOW;
    *out = a * b;
    return 0;
}

static int checked_add_size(size_t a, size_t b, size_t *out)
{
    if (a > SIZE_MAX - b) return -EOVERFLOW;
    *out = a + b;
    return 0;
}

int ipolar_frame_store_init(struct ipolar_frame_store *store, size_t capacity)
{
    if (store == NULL || capacity == 0) return -EINVAL;
    memset(store, 0, sizeof(*store));
    store->published_slot = -1;
    store->capacity = capacity;
    store->session_generation = 1;
    if (pthread_mutex_init(store_mutex(store), NULL) != 0) return -ENOMEM;

    for (unsigned i = 0; i < IPOLAR_FRAME_SLOT_COUNT; ++i) {
        store->buffers[i] = malloc(capacity);
        if (store->buffers[i] == NULL) {
            for (unsigned j = 0; j < i; ++j) free(store->buffers[j]);
            pthread_mutex_destroy(store_mutex(store));
            memset(store, 0, sizeof(*store));
            return -ENOMEM;
        }
    }
    store->initialized = 1;
    return 0;
}

int ipolar_frame_store_publish(struct ipolar_frame_store *store,
                               const uint8_t *data, size_t data_bytes,
                               uint32_t width, uint32_t height,
                               uint32_t source_stride)
{
    if (store == NULL || !store->initialized || data == NULL || width == 0 || height == 0)
        return -EINVAL;
    size_t row_bytes = 0;
    if (checked_mul_size((size_t)width, 2u, &row_bytes) < 0) return -EOVERFLOW;
    if ((size_t)source_stride < row_bytes) return -EINVAL;
    size_t source_prefix = 0, source_need = 0;
    if (checked_mul_size((size_t)(height - 1u), source_stride, &source_prefix) < 0 ||
        checked_add_size(source_prefix, row_bytes, &source_need) < 0)
        return -EOVERFLOW;
    if (data_bytes < source_need) return -EMSGSIZE;
    size_t output_size = 0;
    if (checked_mul_size(row_bytes, (size_t)height, &output_size) < 0)
        return -EOVERFLOW;
    if (output_size > store->capacity) return -EOVERFLOW;

    pthread_mutex_t *mutex = store_mutex(store);
    pthread_mutex_lock(mutex);
    if (!store->initialized) {
        pthread_mutex_unlock(mutex);
        return -EINVAL;
    }
    int target = -1;
    for (unsigned i = 0; i < IPOLAR_FRAME_SLOT_COUNT; ++i) {
        if (store->references[i] == 0) {
            target = (int)i;
            break;
        }
    }
    if (target < 0) {
        pthread_mutex_unlock(mutex);
        return 0; /* All buffers are leased; drop this frame rather than mutate a reader's data. */
    }

    uint8_t *dst = store->buffers[target];
    for (uint32_t row = 0; row < height; ++row)
        memcpy(dst + (size_t)row * row_bytes,
               data + (size_t)row * source_stride, row_bytes);

    store->sizes[target] = output_size;
    store->widths[target] = width;
    store->heights[target] = height;
    store->generations[target] = ++store->next_generation;
    store->published_slot = target;
    pthread_mutex_unlock(mutex);
    return 1;
}

int ipolar_frame_store_acquire(struct ipolar_frame_store *store,
                               struct ipolar_frame_view *view)
{
    if (store == NULL || view == NULL || !store->initialized) return -EINVAL;
    memset(view, 0, sizeof(*view));
    pthread_mutex_t *mutex = store_mutex(store);
    pthread_mutex_lock(mutex);
    if (!store->initialized) {
        pthread_mutex_unlock(mutex);
        return -EINVAL;
    }
    const int slot = store->published_slot;
    if (slot < 0) {
        pthread_mutex_unlock(mutex);
        return 0;
    }
    if (store->references[slot] == UINT32_MAX) {
        pthread_mutex_unlock(mutex);
        return -EOVERFLOW;
    }
    ++store->references[slot];
    view->data = store->buffers[slot];
    view->size = store->sizes[slot];
    view->width = store->widths[slot];
    view->height = store->heights[slot];
    view->generation = store->generations[slot];
    view->session_generation = store->session_generation;
    view->slot = (unsigned)slot;
    view->store = store;
    pthread_mutex_unlock(mutex);
    return 1;
}

int ipolar_frame_view_release(struct ipolar_frame_view *view)
{
    if (view == NULL || view->store == NULL) return -EINVAL;
    struct ipolar_frame_store *store = view->store;
    if (!store->initialized || view->slot >= IPOLAR_FRAME_SLOT_COUNT) return -EINVAL;
    pthread_mutex_t *mutex = store_mutex(store);
    pthread_mutex_lock(mutex);
    if (store->references[view->slot] == 0) {
        pthread_mutex_unlock(mutex);
        return -EINVAL;
    }
    --store->references[view->slot];
    pthread_mutex_unlock(mutex);
    memset(view, 0, sizeof(*view));
    return 0;
}

int ipolar_frame_view_is_current(const struct ipolar_frame_view *view)
{
    if (view == NULL || view->store == NULL || !view->store->initialized) return 0;
    struct ipolar_frame_store *store = view->store;
    pthread_mutex_t *mutex = store_mutex(store);
    pthread_mutex_lock(mutex);
    if (!store->initialized) {
        pthread_mutex_unlock(mutex);
        return 0;
    }
    int current = view->session_generation == store->session_generation;
    pthread_mutex_unlock(mutex);
    return current;
}

void ipolar_frame_store_invalidate(struct ipolar_frame_store *store)
{
    if (store == NULL || !store->initialized) return;
    pthread_mutex_t *mutex = store_mutex(store);
    pthread_mutex_lock(mutex);
    if (!store->initialized) {
        pthread_mutex_unlock(mutex);
        return;
    }
    store->published_slot = -1;
    ++store->session_generation;
    pthread_mutex_unlock(mutex);
}

int ipolar_frame_store_destroy(struct ipolar_frame_store *store)
{
    if (store == NULL || !store->initialized) return -EINVAL;
    pthread_mutex_t *mutex = store_mutex(store);
    pthread_mutex_lock(mutex);
    for (unsigned i = 0; i < IPOLAR_FRAME_SLOT_COUNT; ++i) {
        if (store->references[i] != 0) {
            pthread_mutex_unlock(mutex);
            return -EBUSY;
        }
    }
    store->published_slot = -1;
    store->initialized = 0;
    pthread_mutex_unlock(mutex);
    for (unsigned i = 0; i < IPOLAR_FRAME_SLOT_COUNT; ++i) {
        free(store->buffers[i]);
        store->buffers[i] = NULL;
    }
    pthread_mutex_destroy(mutex);
    store->capacity = 0;
    return 0;
}
