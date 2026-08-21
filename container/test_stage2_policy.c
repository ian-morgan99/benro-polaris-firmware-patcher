#include "stage2_policy.h"

#include <assert.h>

int
main(void)
{
	assert(stage2_model_uses_r5_shims("Canon:EOS R5m2"));
	assert(stage2_model_uses_r5_shims("Canon:EOS 5Rm2"));
	assert(!stage2_model_uses_r5_shims("Pentax:K-3 Mark III"));
	assert(!stage2_model_uses_r5_shims("Pentax:K-1 Mark II"));
	assert(!stage2_model_uses_r5_shims("Canon:EOS R5"));
	assert(!stage2_model_uses_r5_shims(""));
	assert(!stage2_model_uses_r5_shims(0));
	return 0;
}
