/* clock_gettime and CLOCK_MONOTONIC are POSIX, and the harness compiles this
 * file with -std=c11, which hides them unless the feature macro is set before
 * any system header is reached. */
#define _POSIX_C_SOURCE 200809L

#include "stage2_policy.h"

#include <string.h>
#include <strings.h>   /* strncasecmp */
#include <time.h>

/* Default lease. See the header: it must outlast any legitimate native
 * operation while still bounding a permanent wedge. */
unsigned stage2_camera_lease_ms = 120000;

static unsigned default_clock_ms(void)
{
    struct timespec ts;

    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0)
        return 0;
    return (unsigned)((long long)ts.tv_sec * 1000LL + ts.tv_nsec / 1000000LL);
}

static unsigned (*clock_ms)(void) = default_clock_ms;

/* A lease can only be judged against a working clock. If the monotonic clock is
 * unavailable we cannot tell an expired claim from a live one, so the lease is
 * disabled rather than guessed at: stealing a claim on a bad clock would let two
 * requests drive the camera at once, which is worse than the wedge it fixes.
 * Probed once, lazily, so a device that never uses the lease never pays for it. */
static int clock_probe_done;
static int clock_usable;

unsigned
stage2_camera_now_ms(void)
{
    return clock_ms();
}

static int
lease_clock_ready(void)
{
    if (!clock_probe_done) {
        struct timespec ts;

        clock_probe_done = 1;
        clock_usable = clock_gettime(CLOCK_MONOTONIC, &ts) == 0;
    }
    return clock_usable;
}

void
stage2_camera_set_clock(unsigned (*clock)(void))
{
    if (clock) {
        /* An injected clock is usable by definition; this is how the lease is
         * exercised without sleeping. */
        clock_ms = clock;
        clock_probe_done = 1;
        clock_usable = 1;
    } else {
        clock_ms = default_clock_ms;
        clock_probe_done = 0;   /* re-probe the real clock on next use */
    }
}

/* Case-insensitive substring test -- equivalent to upper-casing both sides and
 * using strstr, without the buffer copy. NUL-terminated inputs. */
static int
model_contains_ci(const char *hay, const char *needle)
{
	size_t hlen = strlen(hay);
	size_t nlen = strlen(needle);

	if (nlen == 0 || hlen < nlen)
		return 0;
	for (size_t i = 0; i + nlen <= hlen; i++) {
		if (strncasecmp(hay + i, needle, nlen) == 0)
			return 1;
	}
	return 0;
}

int
stage2_model_uses_r5_shims(const char *model)
{
	if (!model)
		return 0;

	/* Accept the upstream 2.5.34 typo as well as this patcher's corrected name. */
	return !strcmp(model, "Canon:EOS R5m2") ||
	       !strcmp(model, "Canon:EOS 5Rm2");
}

int
stage2_model_uses_pentax_keep_lv(const char *model)
{
	if (!model || !*model)
		return 0;

	/* Case-insensitive brand match (upper-case both sides, look for the token):
	 * any Pentax or Ricoh body in the research camlib, whatever separator or
	 * capitalisation the runtime abilities string uses. The keep-live-view widget
	 * (pentaxpclvkeep) only exists for vendor-mode Pentax models, so brand gating
	 * is safe and conservative.
	 *
	 * FIELD-TEST FIX (2026-09-10): the old exact-prefix check ("Pentax:") silently
	 * failed on MTP-mode bodies whose runtime string uses a SPACE separator
	 * ("Pentax K-3 Mark III (MTP mode)"), so Shims #4/#5 never activated there.
	 * A case-insensitive substring match covers every form + capitalisation.
	 *
	 * Plus the Samsung GX10 / GX-10 (a rebranded Pentax K10D): matched by model
	 * token ONLY -- gx10 or gx-10, never any other model. */
	if (model_contains_ci(model, "pentax") ||
	    model_contains_ci(model, "ricoh"))
		return 1;

	return model_contains_ci(model, "gx10") ||
	       model_contains_ci(model, "gx-10");
}

/* Keep the K-1 II pacing policy off the original K-1 and the K-3 III. */
int
stage2_model_is_k1_mark_ii(const char *model)
{
	if (!model || !*model)
		return 0;
	return model_contains_ci(model, "k-1 mark ii");
}

static int has_priority(struct stage2_camera_gate *gate, enum stage2_camera_operation op)
{
    if (op == STAGE2_CAMERA_PREVIEW)
        return !atomic_load(&gate->waiting_controls);
    if (op == STAGE2_CAMERA_CONFIG)
        return !atomic_load(&gate->waiting_setters);
    return 1;
}

/* All nine native wait callers on the audited image follow successful admission
 * with setCameraStatus(1) and release with setCameraStatus(0). The claim must
 * already belong to this thread when wait returns. A second thread may run
 * between that return and the legacy status write. */
int
stage2_camera_claim(struct stage2_camera_gate *gate, uintptr_t *camera_word,
                    unsigned *busy_word, unsigned tid, unsigned site,
                    enum stage2_camera_operation op, int budget, void (*pause_poll)(void))
{
    unsigned generation = atomic_load(&gate->generation);
    uintptr_t camera = __atomic_load_n(camera_word, __ATOMIC_ACQUIRE);
    int result = -1;

    if (!camera || !tid || budget <= 0)
        return -1;

    /* Reentrancy. A native handler that already holds the claim can reach a
     * second waitCameraIdle on the same thread -- deal_camera_control_handler
     * dispatching into setCameraConfigWithCommand does exactly this. Refusing it
     * is a self-deadlock: the owner is waiting on itself and nothing can ever
     * free the gate. Admit it and count the nesting so only the outermost
     * release frees the claim. This is the fault recorded in the field as
     * "owner_site == refusing site", 24 times in one log window. */
    if (atomic_load(&gate->owner_tid) == tid &&
        __atomic_load_n(busy_word, __ATOMIC_ACQUIRE)) {
        atomic_fetch_add(&gate->owner_depth, 1);
        return 0;
    }

    if (op == STAGE2_CAMERA_SET)
        atomic_fetch_add(&gate->waiting_setters, 1);
    if (op != STAGE2_CAMERA_PREVIEW)
        atomic_fetch_add(&gate->waiting_controls, 1);
    for (int polls = 0; ; polls++) {
        unsigned free_tid = 0;
        if (atomic_load(&gate->generation) != generation ||
            __atomic_load_n(camera_word, __ATOMIC_ACQUIRE) != camera)
            break;

        /* Lease takeover. A claim whose lease has expired belongs to an
         * operation that is never going to release it -- the v115..v117 wedge,
         * where one owner held for an entire 71-refusal window and every later
         * request was refused forever. Take it over rather than wait out the
         * rest of eternity. Only possible when the clock works, because stealing
         * a live claim would let two requests drive the camera at once. */
        if (stage2_camera_lease_ms > 0 && lease_clock_ready()) {
            unsigned owner = atomic_load(&gate->owner_tid);
            unsigned started = atomic_load(&gate->lease_started_ms);
            if (owner && owner != tid && busy_word &&
                __atomic_load_n(busy_word, __ATOMIC_ACQUIRE) &&
                stage2_camera_now_ms() - started >= stage2_camera_lease_ms) {
                unsigned stale = owner;
                if (atomic_compare_exchange_strong(&gate->owner_tid, &stale, tid)) {
                    atomic_store(&gate->owner_site, site);
                    atomic_store(&gate->owner_kind, op);
                    atomic_store(&gate->owner_depth, 1);
                    atomic_store(&gate->lease_started_ms, stage2_camera_now_ms());
                    atomic_fetch_add(&gate->leases_stolen, 1);
                    __atomic_store_n(busy_word, 1, __ATOMIC_RELEASE);
                    result = 0;
                    break;
                }
            }
        }

        if (has_priority(gate, op) &&
            atomic_compare_exchange_strong(&gate->owner_tid, &free_tid, tid)) {
            if (!__atomic_load_n(busy_word, __ATOMIC_ACQUIRE) &&
                atomic_load(&gate->generation) == generation &&
                __atomic_load_n(camera_word, __ATOMIC_ACQUIRE) == camera &&
                has_priority(gate, op)) {
                atomic_store(&gate->owner_site, site);
                atomic_store(&gate->owner_kind, op);
                atomic_store(&gate->owner_depth, 1);
                atomic_store(&gate->lease_started_ms, stage2_camera_now_ms());
                __atomic_store_n(busy_word, 1, __ATOMIC_RELEASE);
                result = 0;
                break;
            }
            atomic_store(&gate->owner_tid, 0);
        }
        /* A preview poll can drop its frame. A control samples once after the
         * last permitted sleep, with no additional sleep or deferred replay. */
        if (op == STAGE2_CAMERA_PREVIEW || polls == budget)
            break;
        pause_poll();
    }
    if (op != STAGE2_CAMERA_PREVIEW)
        atomic_fetch_sub(&gate->waiting_controls, 1);
    if (op == STAGE2_CAMERA_SET)
        atomic_fetch_sub(&gate->waiting_setters, 1);
    return result;
}

void
stage2_camera_release(struct stage2_camera_gate *gate, unsigned *busy_word,
                      unsigned tid)
{
    if (!tid || atomic_load(&gate->owner_tid) != tid)
        return;

    /* Only the owner may release, and a nested claim is freed one level at a
     * time: an inner handler returning must not hand the camera to another
     * request while its caller is still mid-operation. */
    unsigned depth = atomic_load(&gate->owner_depth);
    if (depth > 1) {
        atomic_store(&gate->owner_depth, depth - 1);
        return;
    }
    __atomic_store_n(busy_word, 0, __ATOMIC_RELEASE);
    atomic_store(&gate->owner_site, 0);
    atomic_store(&gate->owner_tid, 0);
    atomic_store(&gate->owner_kind, 0);
    atomic_store(&gate->owner_depth, 0);
    atomic_store(&gate->lease_started_ms, 0);
}

/* A session reinitialise ends every operation that could still hold a claim: the
 * camera it was taken against is gone. gp_camera_init already bumped the
 * generation, but bumping it left owner_tid and busy in place, so the new session
 * inherited a claim from a dead one -- which is why every refusal in the field log
 * reads generation=1. Clear the claim as well as winding the generation. */
void
stage2_camera_gate_reset(struct stage2_camera_gate *gate, unsigned *busy_word)
{
    atomic_fetch_add(&gate->generation, 1);
    __atomic_store_n(busy_word, 0, __ATOMIC_RELEASE);
    atomic_store(&gate->owner_tid, 0);
    atomic_store(&gate->owner_site, 0);
    atomic_store(&gate->owner_kind, 0);
    atomic_store(&gate->owner_depth, 0);
    atomic_store(&gate->lease_started_ms, 0);
    atomic_store(&gate->waiting_controls, 0);
    atomic_store(&gate->waiting_setters, 0);
}
