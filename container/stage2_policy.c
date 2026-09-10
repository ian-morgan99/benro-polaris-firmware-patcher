#include "stage2_policy.h"

#include <string.h>

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
	if (!model)
		return 0;

	/* Any Pentax/Ricoh body in the research camlib. The keep-live-view widget
	 * (pentaxpclvkeep, config.c:13648) only exists for vendor-mode Pentax
	 * models, so gating on the "Pentax:" model prefix is both safe and
	 * conservative. */
	return strncmp(model, "Pentax:", 7) == 0;
}
