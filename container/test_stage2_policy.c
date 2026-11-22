#include "stage2_policy.h"

#include <assert.h>

static struct stage2_camera_gate gate;
static uintptr_t camera = 1;
static unsigned busy;
static unsigned polls;
static unsigned release_at;
static int replace_camera;
static int change_generation;
static int config_polls;

static void config_poll(void)
{
    config_polls++;
}

static void unexpected_poll(void)
{
	assert(0 && "preview must never wait, and an idle camera must admit immediately");
}

static void poll_with_preview(void)
{
	polls++;
	assert(atomic_load(&gate.waiting_controls) == 1);
	/* A different thread's cleanup cannot release the active operation. */
	stage2_camera_release(&gate, &busy, 99);
	assert(busy == 1);
    if (polls == release_at) {
		stage2_camera_release(&gate, &busy, 1);
        assert(!busy);
        /* A periodic metadata GET also uses deal_camera_control_handler.
         * It must not take the released slot ahead of the waiting SET. */
        assert(stage2_camera_claim(&gate, &camera, &busy, 4, 44,
                                   STAGE2_CAMERA_CONFIG, 1, config_poll) == -1);
        assert(config_polls == 1);
    }
	/* Even if the owner just released, a pending control takes priority. */
	assert(stage2_camera_claim(&gate, &camera, &busy, 3, 33, 1, 500,
	                           unexpected_poll) == -1);
	if (replace_camera)
		camera++;
	if (change_generation)
		atomic_fetch_add(&gate.generation, 1);
}

static void test_admission(void)
{
	const int budget = 500;
	/* A release in the final permitted sleep still admits the control. */
	release_at = budget;
	assert(stage2_camera_claim(&gate, &camera, &busy, 1, 11, 1, budget, unexpected_poll) == 0);
	assert(stage2_camera_claim(&gate, &camera, &busy, 2, 22, STAGE2_CAMERA_SET, budget, poll_with_preview) == 0);
	assert(polls == release_at && atomic_load(&gate.owner_tid) == 2 && busy == 1);
	assert(atomic_load(&gate.owner_site) == 22 && !atomic_load(&gate.waiting_controls));
	assert(atomic_load(&gate.owner_kind) == STAGE2_CAMERA_SET && !atomic_load(&gate.waiting_setters));
	assert(stage2_camera_claim(&gate, &camera, &busy, 1, 11, 1, budget, unexpected_poll) == -1);
	stage2_camera_release(&gate, &busy, 2);
	assert(!busy && !atomic_load(&gate.owner_tid));

	/* Three independent refusals: a real busy owner, a replaced camera and
	 * a reinit which reuses the same camera pointer. No deferred requests. */
	for (int i = 0; i < 3; i++) {
		release_at = 0;
		polls = 0;
		replace_camera = i == 1;
		change_generation = i == 2;
		assert(stage2_camera_claim(&gate, &camera, &busy, 1, 11, 1, budget, unexpected_poll) == 0);
		assert(stage2_camera_claim(&gate, &camera, &busy, 2, 22, 0, budget, poll_with_preview) == -1);
		assert(polls == (i == 0 ? (unsigned)budget : 1u));
		assert(atomic_load(&gate.owner_tid) == 1 && !atomic_load(&gate.waiting_controls));
		stage2_camera_release(&gate, &busy, 1);
		assert(!busy && !atomic_load(&gate.owner_tid));
	}
	camera = 0;
	assert(stage2_camera_claim(&gate, &camera, &busy, 2, 22, 0, budget, unexpected_poll) == -1);
	assert(!busy && !atomic_load(&gate.waiting_controls));
}

int
main(void)
{
	test_admission();
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
