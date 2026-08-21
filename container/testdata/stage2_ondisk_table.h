/* Compile-only fixture. Production builds generate this file from pgphoto. */
#define STAGE2_SLOT_BASE 0x30000000u
static const struct { const char *name; uintptr_t slot; } STAGE2_SLOTS[64] = {
	[0] = {"gp_camera_new", STAGE2_SLOT_BASE},
	[16] = {"gp_camera_init", STAGE2_SLOT_BASE + 16u * 4u},
};
#define STAGE2_SLOTS_LEN (sizeof (STAGE2_SLOTS) / sizeof (STAGE2_SLOTS[0]))
