#include "stage2_policy.h"

#include <string.h>
#include <strings.h>   /* strncasecmp */

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
    if (op == STAGE2_CAMERA_SET)
        atomic_fetch_add(&gate->waiting_setters, 1);
    if (op != STAGE2_CAMERA_PREVIEW)
        atomic_fetch_add(&gate->waiting_controls, 1);
    for (int polls = 0; ; polls++) {
        unsigned free_tid = 0;
        if (atomic_load(&gate->generation) != generation ||
            __atomic_load_n(camera_word, __ATOMIC_ACQUIRE) != camera)
            break;
        if (has_priority(gate, op) &&
            atomic_compare_exchange_strong(&gate->owner_tid, &free_tid, tid)) {
            if (!__atomic_load_n(busy_word, __ATOMIC_ACQUIRE) &&
                atomic_load(&gate->generation) == generation &&
                __atomic_load_n(camera_word, __ATOMIC_ACQUIRE) == camera &&
                has_priority(gate, op)) {
                atomic_store(&gate->owner_site, site);
                atomic_store(&gate->owner_kind, op);
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
    if (tid && atomic_load(&gate->owner_tid) == tid) {
        __atomic_store_n(busy_word, 0, __ATOMIC_RELEASE);
        atomic_store(&gate->owner_site, 0);
        atomic_store(&gate->owner_tid, 0);
    }
}
