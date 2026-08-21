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
