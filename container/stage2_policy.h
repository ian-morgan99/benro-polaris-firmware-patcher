#ifndef POLARIS_STAGE2_POLICY_H
#define POLARIS_STAGE2_POLICY_H

int stage2_model_uses_r5_shims(const char *model);
/* Pentax models whose preview path benefits from keeping PC live view running
 * across capture-preview calls (issues #36/#55: per-frame d035 teardown +
 * restart re-enters the NoUpdateImage warmup window on every request). */
int stage2_model_uses_pentax_keep_lv(const char *model);
/* Exact model predicate for the K-1 II preview governor. */
int stage2_model_is_k1_mark_ii(const char *model);

#include <stdint.h>
#include <stdatomic.h>

/* pgphoto admits preview, config, focus and capture through one status word.
 * Keep the owner separately: the native ABI exposes only idle/busy. */
struct stage2_camera_gate {
    atomic_uint owner_tid;
    atomic_uint owner_site;
    atomic_uint waiting_controls;
    atomic_uint waiting_setters;
    atomic_uint owner_kind;
    atomic_uint generation;
};
enum stage2_camera_operation {
    STAGE2_CAMERA_CONTROL,
    STAGE2_CAMERA_PREVIEW,
    STAGE2_CAMERA_CONFIG,
    STAGE2_CAMERA_SET
};

int stage2_camera_claim(struct stage2_camera_gate *gate, uintptr_t *camera_word,
                       unsigned *busy_word, unsigned tid, unsigned site,
                       enum stage2_camera_operation op, int budget, void (*pause_poll)(void));
void stage2_camera_release(struct stage2_camera_gate *gate, unsigned *busy_word,
                          unsigned tid);
#endif
