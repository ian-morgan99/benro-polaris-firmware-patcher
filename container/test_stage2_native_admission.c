/* Exercise the production adapters with the native camera and status words
 * backed by the fixture. Linux supplies real distinct thread IDs. */
#include <assert.h>
#include <pthread.h>
#include <stdint.h>
static uintptr_t camera_word = 1;
static unsigned busy_word;
static int fake_config(int, char *, int);
#define STAGE2_NATIVE_CAMERA_WORD ((uintptr_t)&camera_word)
#define STAGE2_NATIVE_BUSY_WORD ((uintptr_t)&busy_word)
#define STAGE2_CONFIG_COMMAND ((uintptr_t)fake_config)
#define STAGE2_CONFIG_WAIT_RETURN 0x100540u
#define STAGE2_PREVIEW_WAIT_RETURN 0x102ba0u
#define STAGE2_NO_CONSTRUCTOR 1
#include "stage2_loader.c"

static int dispatches;

static void *competing_preview(void *unused)
{
    (void)unused;
    assert(native_claim_from(STAGE2_PREVIEW_WAIT_RETURN, 500) == -1);
    native_set_camera_status(0);
    assert(busy_word == 1);
    return NULL;
}

static int fake_config(int key, char *value, int command)
{
    assert(key == 3 && !strcmp(value, "3") && command == 31);
    if (native_claim_from(STAGE2_CONFIG_WAIT_RETURN, 1) < 0)
        return -2110;
    assert(atomic_load(&native_gate.owner_kind) == STAGE2_CAMERA_SET);
    native_set_camera_status(1);
    dispatches++;
    pthread_t thread;
    assert(!pthread_create(&thread, NULL, competing_preview, NULL));
    assert(!pthread_join(thread, NULL));
    native_set_camera_status(0);
    return -7;
}

int main(void)
{
    assert(native_set_camera_config(3, "3") == -7);
    assert(!busy_word && !native_setting && dispatches == 1);
    camera_word = 0;
    assert(native_set_camera_config(3, "3") == -2110);
    assert(!busy_word && !native_setting && dispatches == 1);
    camera_word = 1;
    assert(native_claim_from(STAGE2_CONFIG_WAIT_RETURN, 1) == 0);
    assert(atomic_load(&native_gate.owner_kind) == STAGE2_CAMERA_CONFIG);
    native_set_camera_status(0);
    return 0;
}
