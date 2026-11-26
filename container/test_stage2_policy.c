#include "stage2_policy.h"

#include <assert.h>
#include <stddef.h>

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

/* Counts how long the caller had to wait, so a test can assert that an idle gate
 * admits immediately instead of burning its budget first. */
static unsigned counted_polls;

static void count_poll(void)
{
    counted_polls++;
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

/* The K-1 II / K-3 III field failure (v115-v117): one native operation takes the
 * gate and its release never arrives, so every later request is refused forever.
 * Three independent defects made that permanent, and each has its own test here.
 */

/* Defect 1 -- the gate was not reentrant. A native handler that already holds the
 * claim and then reaches a second waitCameraIdle (deal_camera_control_handler ->
 * setCameraConfigWithCommand -> wait) was refused by its OWN claim. In the field
 * log this is unmistakable: owner_site equals the refusing site, 24 times over. */
static void test_reentrancy(void)
{
	struct stage2_camera_gate g = { 0 };
	uintptr_t cam = 1;
	unsigned busy = 0;

	assert(stage2_camera_claim(&g, &cam, &busy, 7, 0x100540,
	                           STAGE2_CAMERA_SET, 1, unexpected_poll) == 0);
	assert(busy == 1 && atomic_load(&g.owner_tid) == 7);

	/* The nested wait by the same thread must be admitted, not refused. */
	assert(stage2_camera_claim(&g, &cam, &busy, 7, 0x100540,
	                           STAGE2_CAMERA_CONFIG, 1, unexpected_poll) == 0);
	assert(atomic_load(&g.owner_depth) == 2);
	assert(busy == 1 && atomic_load(&g.owner_tid) == 7);

	/* A different thread is still locked out while the outer claim is live. */
	counted_polls = 0;
	assert(stage2_camera_claim(&g, &cam, &busy, 8, 0x100540,
	                           STAGE2_CAMERA_CONFIG, 1, count_poll) == -1);
	assert(counted_polls == 1);

	/* The inner release must not free the gate: the outer claim is still live. */
	stage2_camera_release(&g, &busy, 7);
	assert(busy == 1 && atomic_load(&g.owner_tid) == 7);
	assert(atomic_load(&g.owner_depth) == 1);

	/* Only the outermost release frees it. */
	stage2_camera_release(&g, &busy, 7);
	assert(!busy && !atomic_load(&g.owner_tid));
	assert(!atomic_load(&g.owner_depth));

	/* A release from a thread that never owned it cannot free a nested claim
	 * either, and must not corrupt the depth. */
	assert(stage2_camera_claim(&g, &cam, &busy, 7, 0x100540,
	                           STAGE2_CAMERA_SET, 1, unexpected_poll) == 0);
	assert(stage2_camera_claim(&g, &cam, &busy, 7, 0x100540,
	                           STAGE2_CAMERA_CONFIG, 1, unexpected_poll) == 0);
	stage2_camera_release(&g, &busy, 99);
	assert(busy == 1 && atomic_load(&g.owner_depth) == 2);
	stage2_camera_release(&g, &busy, 7);
	stage2_camera_release(&g, &busy, 7);
	assert(!busy && !atomic_load(&g.owner_depth));
}

/* Defect 2 -- gp_camera_init bumped the generation but left the owner in place.
 * A fresh session therefore inherited a claim belonging to a dead one, which is
 * exactly why every refusal in the field log reads generation=1: the gate was
 * armed once and never re-armed. */
static void test_reset_clears_a_leaked_claim(void)
{
	struct stage2_camera_gate g = { 0 };
	uintptr_t cam = 1;
	unsigned busy = 0;

	assert(stage2_camera_claim(&g, &cam, &busy, 3, 0x102cd4,
	                           STAGE2_CAMERA_CONTROL, 1, unexpected_poll) == 0);
	/* Simulate the leak: the owning operation returns without releasing. */
	assert(stage2_camera_claim(&g, &cam, &busy, 4, 0x100540,
	                           STAGE2_CAMERA_CONFIG, 1, count_poll) == -1);

	/* A session reinitialise must hand the next request a clean gate. */
	stage2_camera_gate_reset(&g, &busy);
	assert(!busy && !atomic_load(&g.owner_tid) && !atomic_load(&g.owner_site));
	assert(!atomic_load(&g.owner_depth) && !atomic_load(&g.waiting_controls));
	assert(stage2_camera_claim(&g, &cam, &busy, 4, 0x100540,
	                           STAGE2_CAMERA_CONFIG, 1, unexpected_poll) == 0);
	stage2_camera_release(&g, &busy, 4);
	assert(!busy);
}

/* Defect 3 -- nothing bounded a claim. If the release never arrives and no
 * reinitialise happens, the refusal is permanent: the field log shows one owner
 * holding for the whole 71-refusal window. A lease bounds it. The clock is
 * injected so this is deterministic rather than timing-dependent. */
static unsigned fake_now_ms;

static unsigned fake_clock(void)
{
    return fake_now_ms;
}

static void test_lease_expires_a_leaked_claim(void)
{
	struct stage2_camera_gate g = { 0 };
	uintptr_t cam = 1;
	unsigned busy = 0;
	unsigned saved = stage2_camera_lease_ms;

	stage2_camera_set_clock(fake_clock);
	stage2_camera_lease_ms = 1000;
	fake_now_ms = 50000;

	assert(stage2_camera_claim(&g, &cam, &busy, 5, 0x101b0c,
	                           STAGE2_CAMERA_CONTROL, 1, unexpected_poll) == 0);
	assert(atomic_load(&g.lease_started_ms) == 50000);

	/* Inside the lease a second thread waits its budget and is refused, exactly
	 * as before: a genuinely busy camera must not be stolen from. */
	counted_polls = 0;
	assert(stage2_camera_claim(&g, &cam, &busy, 6, 0x100540,
	                           STAGE2_CAMERA_CONFIG, 3, count_poll) == -1);
	assert(counted_polls == 3 && atomic_load(&g.leases_stolen) == 0);
	assert(atomic_load(&g.owner_tid) == 5);

	/* Past the lease the leaked claim is taken over on the first poll, not after
	 * burning the whole budget, and the takeover is recorded for telemetry. */
	fake_now_ms = 51001;
	counted_polls = 0;
	assert(stage2_camera_claim(&g, &cam, &busy, 6, 0x100540,
	                           STAGE2_CAMERA_CONFIG, 500, count_poll) == 0);
	assert(counted_polls == 0 && atomic_load(&g.owner_tid) == 6);
	assert(atomic_load(&g.leases_stolen) == 1);
	assert(atomic_load(&g.owner_depth) == 1);

	/* The stale owner can no longer free the new claim, and cannot corrupt it. */
	stage2_camera_release(&g, &busy, 5);
	assert(busy == 1 && atomic_load(&g.owner_tid) == 6);
	stage2_camera_release(&g, &busy, 6);
	assert(!busy && !atomic_load(&g.owner_depth));

	/* A lease of zero disables takeover entirely: the wedge returns to the old
	 * permanent behaviour, which is the documented escape hatch. */
	stage2_camera_lease_ms = 0;
	fake_now_ms = 60000;
	assert(stage2_camera_claim(&g, &cam, &busy, 7, 0x101b0c,
	                           STAGE2_CAMERA_CONTROL, 1, unexpected_poll) == 0);
	fake_now_ms = 999999;
	counted_polls = 0;
	assert(stage2_camera_claim(&g, &cam, &busy, 8, 0x100540,
	                           STAGE2_CAMERA_CONFIG, 2, count_poll) == -1);
	assert(counted_polls == 2 && atomic_load(&g.owner_tid) == 7);
	stage2_camera_release(&g, &busy, 7);

	stage2_camera_lease_ms = saved;
	stage2_camera_set_clock(NULL);
}

/* A claim must be admitted with no polling at all when the gate is already free.
 * Every refused control request used to burn its whole budget first, which is
 * what turned "settings do not stick" into a visible multi-second stall. */
static void test_idle_admission_is_immediate(void)
{
	struct stage2_camera_gate g = { 0 };
	uintptr_t cam = 1;
	unsigned busy = 0;

	counted_polls = 0;
	assert(stage2_camera_claim(&g, &cam, &busy, 9, 0x100540,
	                           STAGE2_CAMERA_SET, 500, count_poll) == 0);
	assert(counted_polls == 0);
	stage2_camera_release(&g, &busy, 9);
}

/* The shipped lease is 120000 ms and the shipped control budget is 500 polls.
 * test_lease_expires_a_leaked_claim() overrides the lease to 1000 ms, so nothing
 * previously exercised the two shipped values together. That gap let me conclude
 * from field logs alone that takeover was unreachable -- every one of 212 logged
 * refusals reads stolen=0 -- and it is wrong: the lease is evaluated on entry, so
 * a waiter arriving after expiry recovers on its first poll without polling at
 * all. The refusals show no waiter arrived inside the window, not that takeover
 * is broken. Pinned here because the distinction decides where the remaining
 * wedge lives: this gate self-heals, the camlib output_pending latch does not.
 */
static void test_production_lease_recovers_a_leaked_claim(void)
{
	struct stage2_camera_gate g = { 0 };
	uintptr_t cam = 1;
	unsigned busy = 0;

	assert(stage2_camera_lease_ms == 120000);
	stage2_camera_set_clock(fake_clock);
	fake_now_ms = 100000;

	/* Owner takes the gate and its release never arrives. */
	assert(stage2_camera_claim(&g, &cam, &busy, 5, 0x101b0c,
	                           STAGE2_CAMERA_CONTROL, 1, unexpected_poll) == 0);

	/* The observed median hold is ~3 s. A waiter with the shipped budget is
	 * refused and burns all 500 polls -- correct, the lease is still live and a
	 * genuinely busy camera must not be stolen from. */
	fake_now_ms = 103000;
	counted_polls = 0;
	assert(stage2_camera_claim(&g, &cam, &busy, 6, 0x100540,
	                           STAGE2_CAMERA_CONFIG, 500, count_poll) == -1);
	assert(counted_polls == 500 && atomic_load(&g.leases_stolen) == 0);
	assert(atomic_load(&g.owner_tid) == 5);

	/* Past the shipped lease the leaked claim is taken over on entry, with no
	 * polling, so recovery costs the caller nothing. */
	fake_now_ms = 221001;
	counted_polls = 0;
	assert(stage2_camera_claim(&g, &cam, &busy, 7, 0x100540,
	                           STAGE2_CAMERA_CONFIG, 500, count_poll) == 0);
	assert(counted_polls == 0 && atomic_load(&g.leases_stolen) == 1);
	assert(atomic_load(&g.owner_tid) == 7 && atomic_load(&g.owner_depth) == 1);

	/* The dead owner cannot corrupt the new claim. */
	stage2_camera_release(&g, &busy, 5);
	assert(busy == 1 && atomic_load(&g.owner_tid) == 7);
	stage2_camera_release(&g, &busy, 7);
	assert(!busy && !atomic_load(&g.owner_depth));

	stage2_camera_set_clock(NULL);
}

int
main(void)
{
	test_admission();
	test_reentrancy();
	test_reset_clears_a_leaked_claim();
	test_lease_expires_a_leaked_claim();
	test_production_lease_recovers_a_leaked_claim();
	test_idle_admission_is_immediate();
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
