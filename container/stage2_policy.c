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

/* K-1 Mark II: the body whose PC live view is measurably slow.  Live 8080
 * probe (docs/evidence/k1ii-live-test-2026-09-15/stream-probe-8080.md) shows
 * ~1 frame per 7-8 s, versus the K-3 III's faster cadence.  The generic
 * 2 s on-demand preview gate therefore returns "busy" for most of each
 * inter-frame gap and the app cycles between a frame and "stalled".  A
 * model-specific default (STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_SECS) aligned to
 * the K-1 II's own frame cadence removes that churn.  Matched by the "K-1 Mark
 * II" token so it never catches the original K-1 or the K-3 III. */
int
stage2_model_is_k1_mark_ii(const char *model)
{
	if (!model || !*model)
		return 0;
	return model_contains_ci(model, "k-1 mark ii");
}
