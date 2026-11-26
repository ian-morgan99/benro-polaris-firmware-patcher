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
    /* Nested waits by the owning thread share one claim (see below), so the
     * gate must know how many are outstanding before it may be freed. */
    atomic_uint owner_depth;
    /* Monotonic milliseconds at which the current claim was acquired, and a
     * count of claims taken over after their lease expired. */
    atomic_uint lease_started_ms;
    atomic_uint leases_stolen;
};
enum stage2_camera_operation {
    STAGE2_CAMERA_CONTROL,
    STAGE2_CAMERA_PREVIEW,
    STAGE2_CAMERA_CONFIG,
    STAGE2_CAMERA_SET
};

/* How long a single claim may be held before another request is allowed to take
 * it over. A native operation that never releases -- the v115..v117 field fault
 * -- otherwise wedges the camera permanently. The value must exceed the longest
 * legitimate single native operation, because stealing mid-operation would let a
 * second request reach a camera that is genuinely busy. Two minutes satisfies
 * both: no native call legitimately runs that long, and a wedged head recovers
 * by itself instead of needing a reboot. */
extern unsigned stage2_camera_lease_ms;

/* Monotonic milliseconds. Injectable so the lease can be tested without sleeping,
 * which keeps the harness deterministic on slow and fast machines alike. */
unsigned stage2_camera_now_ms(void);
void stage2_camera_set_clock(unsigned (*clock)(void));

int stage2_camera_claim(struct stage2_camera_gate *gate, uintptr_t *camera_word,
                       unsigned *busy_word, unsigned tid, unsigned site,
                       enum stage2_camera_operation op, int budget, void (*pause_poll)(void));
void stage2_camera_release(struct stage2_camera_gate *gate, unsigned *busy_word,
                          unsigned tid);
/* Hand the next request a clean gate. Called on every session reinitialise: a
 * claim taken by a dead session must not survive into the new one. */
void stage2_camera_gate_reset(struct stage2_camera_gate *gate, unsigned *busy_word);
#endif
