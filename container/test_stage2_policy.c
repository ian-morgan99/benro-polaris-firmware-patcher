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

        /* Pentax keep-live-view gate (issues #36/#55): case-insensitive brand
         * substring -- colon form, SPACE form (the MTP-mode runtime string that
         * the old prefix check missed), any capitalisation. */
        assert(stage2_model_uses_pentax_keep_lv("Pentax:K-3 Mark III"));
        assert(stage2_model_uses_pentax_keep_lv("Pentax:K-1 Mark II (PTP mode)"));
        /* The actual field-test bug: MTP-mode bodies report a SPACE separator. */
        assert(stage2_model_uses_pentax_keep_lv("Pentax K-3 Mark III (MTP mode)"));
        assert(stage2_model_uses_pentax_keep_lv("Pentax K-1 Mark II (PTP mode)"));
        /* Case-insensitive: any capitalisation of the brand. */
        assert(stage2_model_uses_pentax_keep_lv("pentax:k-01"));
        assert(stage2_model_uses_pentax_keep_lv("PENTAX K-3 MARK III"));
        assert(stage2_model_uses_pentax_keep_lv("Ricoh:GR III"));
        assert(stage2_model_uses_pentax_keep_lv("ricoh gr iii"));
        /* Samsung GX10 / GX-10 (rebranded Pentax K10D): model token ONLY. */
        assert(stage2_model_uses_pentax_keep_lv("Samsung:GX10"));
        assert(stage2_model_uses_pentax_keep_lv("samsung gx-10"));
        assert(stage2_model_uses_pentax_keep_lv("SAMSUNG GX10"));
        /* ...but never any other model. */
        assert(!stage2_model_uses_pentax_keep_lv("Samsung:GX-1S"));
        assert(!stage2_model_uses_pentax_keep_lv("Canon:EOS R5m2"));
        assert(!stage2_model_uses_pentax_keep_lv("Nikon:D850"));
        assert(!stage2_model_uses_pentax_keep_lv(""));
        assert(!stage2_model_uses_pentax_keep_lv(0));
        return 0;
}
