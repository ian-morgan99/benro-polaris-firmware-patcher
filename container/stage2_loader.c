/*
 * stage2_ondisk_loader.c -- Benro Polaris pgphoto "Stage 2" full-core swap,
 *                           ON-DISK trampoline loader (ZERO runtime .text mprotect).
 *
 * Distributable (generic; no Benro/reconstructed source). Built into
 * libpolaris_stage2.so and LD_PRELOAD'd (or DT_NEEDED) into the ON-DISK-PATCHED
 * pgphoto produced by stage2_ondisk_patch.py.
 *
 * WHY THIS EXISTS -----------------------------------------------------------
 * The earlier loaders rewrote pgphoto's `.text` at RUNTIME (mprotect the code
 * page RW/RWX, patch an 8-byte absolute jump, restore).  Three variants (span
 * RWX, per-unique-page RWX, W^X two-step) each crashed or were REFUSED by the
 * device's Hi3559V200 kernel (mprotect ENOMEM on the dense high-cluster pages;
 * /proc/self/mem segfaulted), and NONE of those failures reproduce under
 * qemu-user.  Runtime `.text` self-modification is fundamentally hostile on this
 * kernel.
 *
 * The on-disk design moves ALL `.text` editing to PATCH TIME (in the file).  At
 * runtime this loader NEVER touches `.text` and NEVER calls mprotect.  Each
 * boundary entry was rewritten in the file to an absolute INDIRECT jump through a
 * per-entry pointer SLOT:
 *     entry+0: ldr r12,[pc,#0]   ; r12 = &slot_i   (the .word at entry+8)
 *     entry+4: ldr pc,[r12]      ; pc = *slot_i    (target, filled below)
 *     entry+8: .word &slot_i
 *
 * SESSION 18 -- SLOTS IN A LOADER-MMAP'd PAGE (not an extended `.bss`) ---------
 * The 64 slots used to live in the patched pgphoto's EXTENDED `.bss` (the patcher
 * bumped the RW PT_LOAD p_memsz + `.bss` sh_size).  On the Hi3559V200 kernel that
 * extended-.bss region was NOT reliably mapped writable: the loader's very first
 * slot write nondeterministically faulted (device crash handler caught SIGSEGV
 * si_addr=0x0037ceb0, the old FIRST slot -- one run's writes succeeded, another's
 * did not).  So the slots now live at a FIXED base (STAGE2_SLOT_BASE, chosen in
 * the wide free gap between pgphoto's image+heap and the shared libs), and THIS
 * loader creates the page itself: as its first action it mmaps a fresh anonymous
 * PROT_READ|PROT_WRITE page MAP_FIXED at STAGE2_SLOT_BASE (after confirming via
 * /proc/self/maps that nothing already occupies it -- if something does it refuses
 * rather than clobbering).  The slot writes then land in a guaranteed-fresh RW
 * anon page.  Still NO mprotect, NO .text write, NO /proc/self/mem -- and no
 * dependence on the kernel's handling of an extended `.bss`.
 *
 * SESSION 17 -- STARTUP-RACE HARDENING & CRASH PINPOINTING -------------------
 * On device the mechanism WORKS but was nondeterministic: some runs reached
 * `[stage2] slots filled 64/64` and drove the new core; others died with a
 * Segmentation fault (exit 139) BEFORE that line.  Leading cause: pgphoto is
 * multi-threaded and re-execs itself; a thread (spCamera IPC / httpd) can call a
 * redirected gp_* while its slot is still 0 (unfilled) -> `ldr pc,[r12]` with
 * *slot==0 -> jump to null -> SIGSEGV.  It is timing/ASLR-dependent (some runs
 * crash, some don't).  This revision:
 *
 *   (1) SLOTS-SAFE-INIT FIRST.  The VERY FIRST action of the constructor (before
 *       dlopen, before symbol resolution, before the CAMLIBS log) writes the
 *       address of `stage2_abort_stub` into ALL 64 slots, with a store barrier so
 *       other threads see it immediately.  THEN dlopen/resolve overwrite each slot
 *       with its real target.  Any boundary call in the pre-fill window now lands
 *       in `stage2_abort_stub` -- which logs `[stage2] FATAL early call to <slot>
 *       before fill` and exits CLEANLY (97) -- never a null jump / segfault.  The
 *       slots are plain writable data in the executable's own .bss, so this early
 *       write needs no mprotect.  If the two-pass re-exec runs the loader twice,
 *       each pass slots-safe-inits first; the operation is idempotent.
 *
 *   (2) CRASH-PINPOINT HANDLER.  A sigaction(SIGSEGV/SIGILL/SIGBUS, SA_SIGINFO)
 *       handler is installed at the very top of the constructor.  On any fault it
 *       logs si_addr, the PC (arm_pc), whether the fault/PC is inside the slot
 *       region or equals a slot's target, and the last checkpoint reached; then it
 *       restores the default handler and re-raises, so the exit code stays visible.
 *
 *   (3) FINE CHECKPOINTS on unbuffered stderr so a crash never hides the last
 *       point reached: `init: stubbed 64 slots`, `dlopen core ok`, `dlopen port
 *       ok`, `resolved N/64`, `slots filled 64/64`.
 */
#define _GNU_SOURCE
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <dlfcn.h>
#include <unistd.h>
#include <stdlib.h>
#include <signal.h>
#include <ucontext.h>
#include <errno.h>
#include <sys/mman.h>

#include "stage2_policy.h"

/* Generated slot table: {symbol name, absolute slot vaddr in extended .bss},
 * plus STAGE2_SLOT_BASE (the fixed slot-region base for THIS binary). */
#include "stage2_ondisk_table.h"

#ifndef STAGE2_CORE_SONAME
#define STAGE2_CORE_SONAME "libgphoto2.so.6"
#endif
#ifndef STAGE2_PORT_SONAME
#define STAGE2_PORT_SONAME "libgphoto2_port.so.12"
#endif
/* SESSION 19 -- absolute default paths so the loader resolves the core/port with
 * ZERO environment (no LD_LIBRARY_PATH, no LD_PRELOAD -- the single-file
 * patchelf'd path).  dlopen order: env override -> absolute default -> bare
 * soname (rpath / LD_LIBRARY_PATH).  On device the absolute default is the real
 * install path; the wrapper's LD_LIBRARY_PATH still works via the soname fallback. */
#ifndef STAGE2_CORE_PATH
#define STAGE2_CORE_PATH "/app/lib/stage2/libgphoto2.so.6"
#endif
#ifndef STAGE2_PORT_PATH
#define STAGE2_PORT_PATH "/app/lib/stage2/libgphoto2_port.so.12"
#endif
#ifndef STAGE2_CAMLIBS_DIR
#define STAGE2_CAMLIBS_DIR "/app/lib/stage2/libgphoto2/2.5.34"
#endif
#ifndef STAGE2_IOLIBS_DIR
#define STAGE2_IOLIBS_DIR  "/app/lib/stage2/libgphoto2_port/0.12.2"
#endif

/* Slot region [BASE, BASE + N*4).  BASE is compiled in from the generated table
 * (Session 18: device & qemu harness both 0x30000000 -- the loader mmaps a fresh
 * RW anon page here; it is no longer the executable's .bss). */
#define STAGE2_SLOT_LO ((uintptr_t)STAGE2_SLOT_BASE)
#define STAGE2_SLOT_HI ((uintptr_t)STAGE2_SLOT_BASE + STAGE2_SLOTS_LEN * 4u)
#define STAGE2_SLOT_PAGE 4096u   /* one page holds the 64*4 = 256 B slot region */

/* ---------------------------------------------------------------------------
 * Last-checkpoint breadcrumb + async-signal-safe stderr writers.  The crash
 * handler and the abort stub run in contexts where fprintf/snprintf are not
 * guaranteed safe, so they use only write(2) and these tiny helpers.
 * ------------------------------------------------------------------------- */
static volatile const char *g_last_ckpt = "(constructor entry)";

static void s_write(const char *s)
{
    size_t n = 0;
    while (s[n]) n++;
    ssize_t rc = write(2, s, n);
    (void)rc;
}

static void s_write_hex(uintptr_t v)
{
    char buf[11];
    buf[0] = '0'; buf[1] = 'x';
    for (int i = 0; i < 8; i++) {
        unsigned nyb = (v >> ((7 - i) * 4)) & 0xf;
        buf[2 + i] = (char)(nyb < 10 ? '0' + nyb : 'a' + nyb - 10);
    }
    ssize_t rc = write(2, buf, 10);
    (void)rc;
}

static void s_write_dec(int v)
{
    char buf[12];
    int i = 12;
    unsigned u = (v < 0) ? (unsigned)(-v) : (unsigned)v;
    if (u == 0) buf[--i] = '0';
    while (u) { buf[--i] = (char)('0' + (u % 10)); u /= 10; }
    if (v < 0) buf[--i] = '-';
    ssize_t rc = write(2, buf + i, (size_t)(12 - i));
    (void)rc;
}

/* Look up a slot's symbol name by its slot vaddr (for the fail-closed message). */
static const char *slot_name(uintptr_t slot)
{
    for (size_t i = 0; i < STAGE2_SLOTS_LEN; i++)
        if (STAGE2_SLOTS[i].slot == slot) return STAGE2_SLOTS[i].name;
    return "(unknown-slot)";
}

/* ---------------------------------------------------------------------------
 * Fail-closed landing pad.  A boundary entry whose slot still holds the stub
 * (never resolved, or called during the pre-fill window) jumps HERE via
 * `ldr pc,[r12]` with r12 == &slot (the trampoline leaves &slot in r12 and does
 * not touch it before branching to the target).  We recover &slot from r12,
 * name the symbol, log loudly, and _exit(97) -- a clean, greppable message
 * instead of a jump to address 0 / a segfault.  (In a correct run no slot points
 * here once fill completes.)
 * ------------------------------------------------------------------------- */
__attribute__((used, noinline, visibility("hidden")))
void stage2_abort_report(uintptr_t slot)
{
    s_write("[stage2] FATAL early call to ");
    s_write(slot_name(slot));
    s_write(" @slot=");
    s_write_hex(slot);
    s_write(" before fill (slot unresolved / called in pre-fill window). "
            "Aborting cleanly.\n");
    s_write("[stage2]   last checkpoint reached: ");
    s_write((const char *)g_last_ckpt);
    s_write("\n");
    _exit(97);
}

/* Naked entry: preserve r12 (=&slot, set by the in-file trampoline) into r0 and
 * tail-call the C reporter.  Must be naked so the prologue cannot clobber r12
 * before we read it. */
#ifdef STAGE2_NO_CONSTRUCTOR
/* The offline shim unit test builds this ARM-targeted loader natively.  It
 * never enters the abort stub, so provide a portable fail-closed body instead
 * of assembling the production ARM trampoline. */
__attribute__((used, noinline))
static void stage2_abort_stub(void)
{
    stage2_abort_report(0);
}
#else
__attribute__((used, naked, noinline))
static void stage2_abort_stub(void)
{
    __asm__ volatile(
        "mov r0, r12\n\t"
        "b   stage2_abort_report\n\t"
    );
}
#endif

static void slot_store(uintptr_t slot_vaddr, void *val)
{
    *(volatile uintptr_t *)slot_vaddr = (uintptr_t)val;   /* plain RW data store */
}

/* ===========================================================================
 * SHIM #1 -- Benro storageType@+0x1c populator (interop; MIT).
 * ---------------------------------------------------------------------------
 * Root cause of the full-stack `storage:0 -> capture fail` regression:
 * Benro's proprietary `struct _Camera` tail carries an `int storageType` at
 * byte offset +0x1c that Benro's IN-FIRMWARE modified libgphoto2 driver wrote
 * (2 == card present) but NO upstream libgphoto2 build of ANY version writes.
 * With the full 2.5.34 core the field stays calloc-0, so Benro's app
 * `getCameraStorageStatus()` -- which reads `*(int*)((char*)camera + 0x1c)`
 * DIRECTLY (not through any gp_* call, so the read cannot be hooked) -- sees 0,
 * reports `storage:0`, calls `enableCaptureTarget(0,0)`, and Canon/Nikon
 * capture then has no card target and fails.  Single field, whole failure.
 *
 * Fix: wrap `gp_camera_init` (already in the trampolined boundary set).  After a
 * successful init we ask the core's own StorageInfo enumeration whether the
 * camera reports >=1 storage; if so we write storageType=2 into the tail field,
 * exactly what the in-firmware driver used to do.  The `_Camera` struct is
 * padded to 4140 B by the recipe, so +0x1c is safely in-bounds.  Default is
 * gated on get_storageinfo so a genuinely card-less camera is not misreported;
 * STAGE2_STORAGE_FORCE is an escape hatch that writes 2 after any successful
 * init (for the case where 2.5.34's own EOS StorageInfo returns 0 on-device).
 *
 * This ships NO proprietary content: it is one interop offset (0x1c), one
 * constant (2), and the standard public libgphoto2 API gp_camera_get_storageinfo.
 * ------------------------------------------------------------------------- */
#define STAGE2_BENRO_STORAGETYPE_OFF  0x1c   /* byte offset of int storageType */
#define STAGE2_BENRO_STORAGETYPE_CARD 2      /* Benro's "card present" value    */

/* The core handle the loader dlopen'd to fill slots -- the shim resolves the
 * REAL gp_camera_init / gp_camera_get_storageinfo from it (cached). */
static void *g_stage2_core = NULL;
typedef int (*stage2_gp_camera_init_fn)(void *camera, void *context);
typedef int (*stage2_gp_camera_get_storageinfo_fn)(void *camera, void **sifs_out,
                                                   int *count_out, void *context);
typedef int (*stage2_gp_camera_get_abilities_fn)(void *camera, void *abilities);
static stage2_gp_camera_init_fn            g_real_gp_camera_init = NULL;
static stage2_gp_camera_get_storageinfo_fn g_real_gp_camera_get_storageinfo = NULL;
static stage2_gp_camera_get_abilities_fn   g_real_gp_camera_get_abilities = NULL;

/* SHIM #4 (Pentax keep-live-view, issues #36/#55) -- extra core fns.  After a
 * successful gp_camera_init on a Pentax model we push the camlib's
 * `pentaxpclvkeep` toggle ON so camera_capture_preview() skips its per-frame
 * d035 teardown (pentax_restore_live_view) and PC live view stays running
 * across preview requests.  Without it, every failed Polaris preview request
 * tears down + restarts live view and re-enters the NoUpdateImage warmup
 * window -- the churn that starves the Wi-Fi radio (#55). */
typedef int (*stage2_gp_camera_get_single_config_fn)(void *camera, const char *name,
                                                     void **widget_out, void *context);
typedef int (*stage2_gp_widget_set_value_int_fn)(void *widget, const void *value);
static stage2_gp_camera_get_single_config_fn g_real_gp_camera_get_single_config = NULL;
static stage2_gp_widget_set_value_int_fn     g_real_gp_widget_set_value_int    = NULL;
/* Forward-declare the generic widget value getter (defined further down in the
 * SHIM #3 block) so the #121 preview-settle arming below can read the live-view
 * mode widget. The later definition carries the `= NULL` initializer. */
typedef int (*stage2_gp_widget_get_value_fn)(void *widget, void *value);
static stage2_gp_widget_get_value_fn g_real_gp_widget_get_value;
/* Reuses Shim #3's `g_real_gp_camera_set_single_config` (defined further down,
 * in the SHIM #3 block) as the put-handler entry that copies the toggle into
 * params->pentax.keep_live_view.  Forward-declare here so this file compiles
 * top-to-bottom; the later definition carries the `= NULL` initializer. */
typedef int (*stage2_gp_camera_set_single_config_fwd_fn)(void *camera,
                                                        const char *name,
                                                        void *widget,
                                                        void *context);
static stage2_gp_camera_set_single_config_fwd_fn
    g_real_gp_camera_set_single_config;

/* CameraAbilities starts with char model[128] in libgphoto2 2.5.34.  The
 * patcher pins and validates that source version.  Use an over-sized, aligned
 * buffer so this loader does not acquire a compile-time dependency on target
 * libgphoto2 headers while still letting the public getter write its full
 * structure safely. */
static int stage2_camera_uses_r5_shims(void *camera)
{
    union {
        max_align_t alignment;
        unsigned char bytes[4096];
    } abilities;

    if (!g_real_gp_camera_get_abilities && g_stage2_core)
        g_real_gp_camera_get_abilities = (stage2_gp_camera_get_abilities_fn)
            dlsym(g_stage2_core, "gp_camera_get_abilities");
    if (!g_real_gp_camera_get_abilities || !camera)
        return 0;

    memset(&abilities, 0, sizeof(abilities));
    if (g_real_gp_camera_get_abilities(camera, &abilities) != 0)
        return 0;
    abilities.bytes[127] = '\0';
    return stage2_model_uses_r5_shims((const char *)abilities.bytes);
}

/* SHIM #4 model gate: any Pentax/Ricoh body (the keep-live-view widget only
 * exists for vendor-mode Pentax models).  Reuses the abilities read from the
 * same core handle. */
static int stage2_camera_uses_pentax_keep_lv(void *camera)
{
    union {
        max_align_t alignment;
        unsigned char bytes[4096];
    } abilities;

    if (!g_real_gp_camera_get_abilities && g_stage2_core)
        g_real_gp_camera_get_abilities = (stage2_gp_camera_get_abilities_fn)
            dlsym(g_stage2_core, "gp_camera_get_abilities");
    if (!g_real_gp_camera_get_abilities || !camera)
        return 0;

    memset(&abilities, 0, sizeof(abilities));
    if (g_real_gp_camera_get_abilities(camera, &abilities) != 0)
        return 0;
    abilities.bytes[127] = '\0';
    return stage2_model_uses_pentax_keep_lv((const char *)abilities.bytes);
}

/* K-1 Mark II predicate: the body whose PC live view is measurably slow
 * (~1 frame / 7-8 s, docs/evidence/k1ii-live-test-2026-09-15).  Used to pick a
 * model-specific on-demand preview minimum interval so the gate does not return
 * "busy" for most of each inter-frame gap.  Reuses the same abilities read. */
static int stage2_camera_is_k1_mark_ii(void *camera)
{
    union {
        max_align_t alignment;
        unsigned char bytes[4096];
    } abilities;

    if (!g_real_gp_camera_get_abilities && g_stage2_core)
        g_real_gp_camera_get_abilities = (stage2_gp_camera_get_abilities_fn)
            dlsym(g_stage2_core, "gp_camera_get_abilities");
    if (!g_real_gp_camera_get_abilities || !camera)
        return 0;

    memset(&abilities, 0, sizeof(abilities));
    if (g_real_gp_camera_get_abilities(camera, &abilities) != 0)
        return 0;
    abilities.bytes[127] = '\0';
    return stage2_model_is_k1_mark_ii((const char *)abilities.bytes);
}

/* Issue #121: bounded per-session preview-settle window. When the camera is
 * already powered ON at app launch, the PTP session is in "SessionAlreadyOpened"
 * state (a previous process left it open) and PC live view may be active. The
 * app's immediate burst of concurrent preview + config traffic then hits that
 * unsafe transition and crashes (v10 retest: camera ON at start -> crash with no
 * user interaction; OFF->ON works because the camera appears after the runtime is
 * up). We arm a short settle window only when the session was ALREADY open at init
 * (live view active before we enabled keep-lv), so a fresh OFF->ON connection is
 * unaffected. While inside the window, preview fetches return GP_ERROR_CAMERA_BUSY
 * (non-terminal; the app renders it as "camera busy"/pending and retries) instead
 * of generating PTP traffic, giving the session time to settle before the next
 * real frame fetch. Bounded, not an arbitrary sleep: after the window the normal
 * on-demand gate resumes unchanged. */
/* Issue #125: all Pentax preview/capture timing state is an elapsed-duration /
 * readiness gate, so it must use a MONOTONIC clock, not wall clock.  Polaris can
 * acquire/correct time after boot (NTP); a backwards correction would make
 * `now - last_fetch` negative and satisfy `< min_interval` for far longer than
 * intended (or extend a cooldown), while a forwards correction would expire a
 * safety window immediately.  clock_gettime(CLOCK_MONOTONIC) is immune to both.
 * Wall clock is kept only for human-readable timestamps. */
static long long stage2_monotonic_secs(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0)
        return 0;
    return (long long)ts.tv_sec;
}

static int     g_pentax_session_was_open = 0;
static long long g_pentax_preview_settle_until = 0;
/* Issue #121: settle window length (seconds) after a session that was already
 * open at init. Default 5 s; set STAGE2_PENTAX_PREVIEW_SETTLE_SECS=0 to disable. */
#define STAGE2_PENTAX_PREVIEW_SETTLE_SECS_DEFAULT   5

/* SHIM #4 -- push `pentaxpclvkeep` ON for a Pentax session.  Best-effort: the
 * widget only exists once vendor mode is enabled, so a GP_ERROR_NOT_SUPPORTED
 * (or any non-OK) result is logged and swallowed; it never fails init. */
static void stage2_pentax_enable_keep_live_view(void *camera, void *context)
{
    if (!g_real_gp_camera_get_single_config && g_stage2_core)
        g_real_gp_camera_get_single_config =
            (stage2_gp_camera_get_single_config_fn)
                dlsym(g_stage2_core, "gp_camera_get_single_config");
    if (!g_real_gp_camera_set_single_config && g_stage2_core)
        g_real_gp_camera_set_single_config =
            (stage2_gp_camera_set_single_config_fwd_fn)
                dlsym(g_stage2_core, "gp_camera_set_single_config");
    if (!g_real_gp_widget_set_value_int && g_stage2_core)
        g_real_gp_widget_set_value_int = (stage2_gp_widget_set_value_int_fn)
            dlsym(g_stage2_core, "gp_widget_set_value");
    /* Issue #124: resolve gp_widget_get_value before the #121 settle probe uses
     * it. Without this, the forward-declared pointer is still NULL at camera-init
     * time (the later SHIM #3/#5 dlsym sites have not run yet), and the probe
     * calls a NULL function pointer -> crash -> pgphoto exit -> checkGphotoTask
     * restart loop (844 cycles observed on K-3 III / K-1 II). */
    if (!g_real_gp_widget_get_value && g_stage2_core)
        g_real_gp_widget_get_value = (stage2_gp_widget_get_value_fn)
            dlsym(g_stage2_core, "gp_widget_get_value");
    if (!g_real_gp_camera_get_single_config || !g_real_gp_camera_set_single_config ||
        !g_real_gp_widget_set_value_int) {
        fprintf(stderr, "[stage2] keep-lv: FATAL real get/set_single_config/"
                        "widget_set_value unresolved (core handle %p)\n",
                g_stage2_core);
        return;
    }

    void *widget = NULL;
    int ret = g_real_gp_camera_get_single_config(camera, "pentaxpclvkeep",
                                                 &widget, context);
    if (ret != 0) {                                  /* GP_OK == 0 */
        fprintf(stderr, "[stage2] keep-lv: pentaxpclvkeep widget unavailable "
                        "(ret=%d) -- leaving default per-frame teardown\n", ret);
        return;
    }

    /* Issue #121: if PC live view is ALREADY active (the camera was powered on
     * before this process, so the PTP session was already open), arm a bounded
     * preview-settle window. The app's immediate preview+config burst would
     * otherwise hit the SessionAlreadyOpened / live-view-active transition and
     * crash; returning "camera busy" for a few seconds lets it settle. A fresh
     * OFF->ON connection has d035=0 here, so it is unaffected. */
    {
        void *lvwidget = NULL;
        if (g_real_gp_camera_get_single_config(camera, "pentaxpclvmode",
                                               &lvwidget, context) == 0 &&
            lvwidget) {
            int lvval = 0;
            /* Issue #124: guard the NULL case -- if gp_widget_get_value could not
             * be resolved (helper unavailable), skip the optional settle probe
             * instead of calling a NULL pointer. Camera init must not become
             * fatal just because this best-effort probe cannot run. */
            if (g_real_gp_widget_get_value &&
                g_real_gp_widget_get_value(lvwidget, &lvval) == 0 && lvval == 1) {
                const char *settle_s = getenv("STAGE2_PENTAX_PREVIEW_SETTLE_SECS");
                int settle = STAGE2_PENTAX_PREVIEW_SETTLE_SECS_DEFAULT;
                if (settle_s && atoi(settle_s) >= 0)
                    settle = atoi(settle_s);
                if (settle > 0) {
                    g_pentax_session_was_open = 1;
                    g_pentax_preview_settle_until = stage2_monotonic_secs() + settle;
                    fprintf(stderr, "[stage2] keep-lv: PC live view already active "
                                    "(session was open before this process); arming "
                                    "%ds preview-settle window (issue #121)\n", settle);
                }
            }
        }
    }
    int on = 1;
    if (g_real_gp_widget_set_value_int(widget, &on) != 0) {
        fprintf(stderr, "[stage2] keep-lv: widget value set failed\n");
        return;
    }
    /* Route through the camlib's put handler (_put_Pentax_KeepLiveView), which
     * copies the toggle into params->pentax.keep_live_view -- that is the flag
     * camera_capture_preview() checks to skip its per-frame d035 teardown. */
    ret = g_real_gp_camera_set_single_config(camera, "pentaxpclvkeep", widget,
                                             context);
    if (ret != 0) {
        fprintf(stderr, "[stage2] keep-lv: set_single_config failed (ret=%d) -- "
                        "leaving default per-frame teardown\n", ret);
        return;
    }
    fprintf(stderr, "[stage2] keep-lv: pentaxpclvkeep ON for this session "
                    "(PC-LV stays running across preview requests)\n");
}

/* ===========================================================================
 * SHIM #5 -- Pentax preview backoff (issue #55).  Gated on STAGE2_PENTAX_PREVIEW_BACKOFF
 * (default ON; set =0 to A/B against the legacy unbounded loop).
 *
 * The camlib's per-frame retry is bounded (30 attempts / 1.5 s), but pgphoto's
 * OUTER preview-request loop is not: when PC-LV never yields a frame it calls
 * gp_camera_capture_preview back-to-back for hours, and that sustained PTP
 * traffic starves the Wi-Fi radio (#55).  This wrapper counts consecutive
 * GP_ERROR_TIMEOUT (-10) results (the exhausted-0xa008 terminal branch) and,
 * after STAGE2_PENTAX_PREVIEW_BACKOFF_MAX consecutive failures (default 3),
 * opens a cooldown window (STAGE2_PENTAX_PREVIEW_BACKOFF_SECS, default 30 s).
 * While inside the window the call returns GP_ERROR_CAMERA_BUSY immediately --
 * NON-BLOCKING by design (TA review of 446fbfd): no sleep is held inside the
 * intercepted camera call, so stop/cancel/restart never wait out a cooldown and
 * the session worker is not pinned.  Any non-timeout result resets the counter.
 *
 * On-demand gate (design principle: capture preview panes only when specifically
 * needed): at most one REAL frame fetch per STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_SECS
 * (default 2 s); calls inside the window return GP_ERROR_CAMERA_BUSY (-110, a
 * non-terminal "camera busy" state) instead of generating PTP traffic.  This is
 * what makes preview OFF/low-traffic actually leave processing headroom for the
 * unit itself, and it sets up future on-demand uses (e.g. platesolving: grab a
 * frame when needed, then release). */
typedef int (*stage2_gp_camera_capture_preview_fn)(void *camera, void *file,
                                                  void *context);
static stage2_gp_camera_capture_preview_fn g_real_gp_camera_capture_preview = NULL;
static int  g_pentax_preview_timeouts = 0;
static long long g_pentax_preview_backoff_until = 0;
/* Issue #127: capability-disable for a permanent NOT_SUPPORTED preview result.
 * Once the body/mode reports preview unsupported, stop generating PTP traffic
 * (return the error directly) instead of retrying forever across cooldowns. */
static int g_pentax_preview_disabled = 0;
/* Issue #127 (TA follow-up): transport/session failure state, kept SEPARATE from
 * the transient preview backoff.  A NO_DEVICE / USB / I/O error means the current
 * session generation is unhealthy and needs a lifecycle rebind -- it must NOT be
 * folded into the transient "camera busy" cooldown, which would relabel the
 * terminal transport failure as GP_ERROR_CAMERA_BUSY and delay the rebind path.
 * While set, preview calls return the original terminal class (not CAMERA_BUSY)
 * without generating PTP traffic; a fresh/revalidated session generation (init)
 * clears it so real preview traffic can resume. */
static int  g_pentax_preview_session_unhealthy = 0;
static int  g_pentax_preview_last_terminal = 0;   /* the I/O / no-device code to surface */

/* On-demand gate (design principle: capture preview panes only when specifically
 * needed, not as a side effect of periodic polling).  Live Clog analysis showed
 * ~4-5 frame fetches per app poll while PC-LV is active (~13k blocks / boot),
 * which starves the unit's own processing + radios.  This minimum-interval gate
 * caps real camera traffic at one frame per N seconds; calls inside the window
 * return GP_ERROR_CAMERA_BUSY (-110, "camera busy" -- a non-terminal state the
 * app already renders as pending) instead of hitting PTP.  Set =0 to disable. */
static long long g_pentax_preview_last_fetch = 0;

/* Issue #121: bounded per-session preview-settle window. When the camera is
 * already powered ON at app launch, the PTP session is in "SessionAlreadyOpened"
 * state (a previous process left it open) and PC live view may be active. The
 * app's immediate burst of concurrent preview + config traffic then hits that
 * unsafe transition and crashes (v10 retest: camera ON at start -> crash with no
 * user interaction; OFF->ON works because the camera appears after the runtime is
 * up). We arm a short settle window only when the session was ALREADY open at init
 * (live view active before we enabled keep-lv), so a fresh OFF->ON connection is
 * unaffected. While inside the window, preview fetches return GP_ERROR_CAMERA_BUSY
 * (non-terminal; the app renders it as "camera busy"/pending and retries) instead
 * of generating PTP traffic, giving the session time to settle before the next
 * real frame fetch. Bounded, not an arbitrary sleep: after the window the normal
 * on-demand gate resumes unchanged.  The state + default are declared above in
 * the SHIM #4 block (before stage2_pentax_enable_keep_live_view arms them). */

#define STAGE2_PENTAX_PREVIEW_BACKOFF_MAX_DEFAULT   3
#define STAGE2_PENTAX_PREVIEW_BACKOFF_SECS_DEFAULT  30
#define STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_SECS_DEFAULT 2
/* K-1 II specific: its PC live view yields ~1 frame / 7-8 s (live probe,
 * docs/evidence/k1ii-live-test-2026-09-15/stream-probe-8080.md).  A gate
 * interval aligned to that cadence stops the app from cycling between a frame
 * and "stalled" for most of each inter-frame gap.  Only used when no explicit
 * STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_SECS override is set. */
#define STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_K1II_SECS 8

/* GP result codes in this libgphoto2 (port-result.h / gphoto2-result.h). */
#define STAGE2_GP_ERROR_TIMEOUT (-10)   /* GP_ERROR_TIMEOUT */
#define STAGE2_GP_ERROR_CAMERA_BUSY (-110) /* GP_ERROR_CAMERA_BUSY */
/* CameraCaptureType from gphoto2-camera.h.  Only still-image capture is
 * subject to the shutter failure budget; movie/sound/preview-like extensions
 * must remain exact pass-through calls. */
#define STAGE2_GP_CAPTURE_IMAGE 0

/* Issue #128: the preview-settle window (armed only when the PTP session was
 * ALREADY open at init -- camera pre-powered, PC live view active) gates
 * PREVIEW traffic only.  CONFIG writes (set_config / set_single_config) are
 * deliberately NOT gated by the settle window: a state-changing write cannot
 * safely be discarded on the assumption that the caller will retry it.
 * Preview remains protected by the inline settle check in
 * stage2_shim_gp_camera_capture_preview below. */

static int stage2_shim_gp_camera_capture_preview(void *camera, void *file,
                                                void *context)
{
    if (!g_real_gp_camera_capture_preview && g_stage2_core)
        g_real_gp_camera_capture_preview =
            (stage2_gp_camera_capture_preview_fn)
                dlsym(g_stage2_core, "gp_camera_capture_preview");
    if (!g_real_gp_camera_capture_preview) {
        fprintf(stderr, "[stage2] preview-backoff: FATAL real "
                        "gp_camera_capture_preview unresolved (core handle %p)\n",
                g_stage2_core);
        return -1;                                   /* GP_ERROR */
    }

    const char *gate = getenv("STAGE2_PENTAX_PREVIEW_BACKOFF");
    if ((gate && strcmp(gate, "0") == 0) ||
        !stage2_camera_uses_pentax_keep_lv(camera))
        return g_real_gp_camera_capture_preview(camera, file, context);

    /* Issue #127: capability-disable.  A permanent GP_ERROR_NOT_SUPPORTED means
     * this body/mode cannot do PC live view; stop generating PTP traffic and
     * surface the error directly instead of retrying forever across cooldowns.
     * (A fresh session / restart re-arms it, since the flag is per-process.) */
    if (g_pentax_preview_disabled) {
        fprintf(stderr, "[stage2] preview: disabled after NOT_SUPPORTED -- "
                        "returning GP_ERROR_NOT_SUPPORTED without PTP traffic (issue #127)\n");
        return -6;                                   /* GP_ERROR_NOT_SUPPORTED */
    }

    /* Issue #127 (TA follow-up): transport/session failure state.  A NO_DEVICE /
     * USB / I/O error marked the current session generation unhealthy.  Until a
     * fresh/revalidated session generation exists (a successful init clears it),
     * keep returning the ORIGINAL terminal class -- never GP_ERROR_CAMERA_BUSY --
     * so the lifecycle/rebind path is not obscured and real preview traffic does
     * not resume against a dead port. */
    if (g_pentax_preview_session_unhealthy) {
        fprintf(stderr, "[stage2] preview: session unhealthy after I/O / no-device "
                        "(last ret=%d) -- returning the terminal class without PTP "
                        "traffic until a fresh/revalidated session generation (issue #127)\n",
                        g_pentax_preview_last_terminal);
        return g_pentax_preview_last_terminal;
    }

    /* Cooldown (NON-BLOCKING, per TA review of 446fbfd): a previous burst
     * exhausted the failure budget.  While inside the cooldown window we return
     * GP_ERROR_CAMERA_BUSY immediately instead of sleeping -- a blocking sleep
     * inside the intercepted call would make stop/cancel/restart wait up to the
     * full cooldown and hold the camera/session worker unnecessarily.  The
     * caller's next poll (or an explicit restart) simply finds the window over;
     * no thread is held, so lifecycle operations stay responsive. */
    if (g_pentax_preview_backoff_until) {
        long long now = stage2_monotonic_secs();
        if (now < g_pentax_preview_backoff_until) {
            int remain_s = (int)(g_pentax_preview_backoff_until - now);
            fprintf(stderr, "[stage2] preview-backoff: in cooldown (%ds left) -- "
                            "returning busy without blocking\n", remain_s);
            return STAGE2_GP_ERROR_CAMERA_BUSY;
        }
    }

    /* Issue #121: bounded preview-settle window. Armed only when the PTP session
     * was ALREADY open at init (camera pre-powered, PC live view active). While
     * inside it, return "camera busy" instead of generating PTP traffic so the
     * app's startup preview+config burst does not hit the SessionAlreadyOpened /
     * live-view-active transition. Non-blocking: the next poll simply finds the
     * window over and proceeds through the normal on-demand gate. */
    if (g_pentax_session_was_open && g_pentax_preview_settle_until) {
        long long now = stage2_monotonic_secs();
        if (now < g_pentax_preview_settle_until) {
            int remain_s = (int)(g_pentax_preview_settle_until - now);
            fprintf(stderr, "[stage2] preview-settle: session was open at init; "
                            "%ds left before the first real frame fetch (issue #121)\n",
                            remain_s);
            return STAGE2_GP_ERROR_CAMERA_BUSY;
        }
        g_pentax_session_was_open = 0;
        g_pentax_preview_settle_until = 0;
    }

    /* On-demand gate: at most one real frame fetch per N seconds.  Calls inside
     * the window return GP_ERROR_CAMERA_BUSY (non-terminal; the app renders it
     * as "camera busy"/pending and retries later) instead of generating PTP
     * traffic, so preview panes are captured only when specifically needed --
     * not on every internal tick/poll.  STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_SECS=0
     * disables the gate (legacy behavior).
     *
     * Model-specific default: the K-1 II's PC live view is measurably slow
     * (~1 frame / 7-8 s, docs/evidence/k1ii-live-test-2026-09-15), so the
     * generic 2 s gate returns "busy" for most of each inter-frame gap and the
     * app cycles between a frame and "stalled".  For a K-1 II with no explicit
     * override, default to an interval aligned to its own cadence (8 s) so the
     * gate stops churning.  Other bodies keep the generic 2 s default. */
    {
        const char *mins = getenv("STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_SECS");
        int min_interval_s;
        if (mins && atoi(mins) >= 0)
            min_interval_s = atoi(mins);
        else if (stage2_camera_is_k1_mark_ii(camera))
            min_interval_s = STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_K1II_SECS;
        else
            min_interval_s = STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_SECS_DEFAULT;
        long long now = stage2_monotonic_secs();
        if ((min_interval_s > 0) && g_pentax_preview_last_fetch &&
            (now - g_pentax_preview_last_fetch < min_interval_s)) {
            return STAGE2_GP_ERROR_CAMERA_BUSY;
        }
        g_pentax_preview_last_fetch = now;
    }

    int ret = g_real_gp_camera_capture_preview(camera, file, context);
    if (ret != 0) {
        /* Issue #127: classify the result BEFORE applying policy.  Collapsing
         * every non-zero result into one transient backoff is unsafe: a permanent
         * NOT_SUPPORTED must disable the operation (no endless retry), an I/O /
         * no-device / USB error signals a dead session that needs lifecycle
         * rebind (not a 30 s "camera busy" window), and only genuine transient
         * failures (timeout / camera-busy) belong in the bounded backoff. */
        int is_not_supported = (ret == -6);            /* GP_ERROR_NOT_SUPPORTED */
        int is_io_or_device  = (ret == -7) ||          /* GP_ERROR_IO */
                               ((ret <= -20) && (ret >= -70)); /* IO_* / USB / lock */

        if (is_not_supported) {
            g_pentax_preview_disabled = 1;
            fprintf(stderr, "[stage2] preview: NOT_SUPPORTED -- disabling PC live "
                            "view for this session/body (no further PTP traffic, issue #127)\n");
            return ret;
        }

        if (is_io_or_device) {
            /* Issue #127 (TA follow-up): a NO_DEVICE / USB / I/O error is a
             * TRANSPORT/SESSION failure, not a transient "camera busy".  Mark the
             * current session generation unhealthy and remember the terminal class
             * so subsequent calls keep surfacing it (never CAMERA_BUSY) until a
             * fresh/revalidated session generation exists.  Do NOT increment or arm
             * the transient preview backoff -- that would relabel the terminal
             * failure as busy and delay the lifecycle rebind path this issue was
             * opened for. */
            g_pentax_preview_session_unhealthy = 1;
            g_pentax_preview_last_terminal = ret;
            fprintf(stderr, "[stage2] preview: I/O / no-device error (ret=%d) -- "
                            "marking session generation unhealthy; will keep returning "
                            "the terminal class (not CAMERA_BUSY) until a fresh/revalidated "
                            "session generation (issue #127)\n", ret);
            return ret;
        }

        /* Issue #127 (TA follow-up): only GENUINELY transient results belong in the
         * bounded backoff.  A timeout (-10) or camera-busy (-110) is a known
         * transient "try again" state; anything else that is not NOT_SUPPORTED and
         * not an I/O / no-device transport failure is an UNKNOWN error class.  The
         * issue's invariant for unknown errors is: SURFACE the original code -- do
         * NOT silently relabel it as GP_ERROR_CAMERA_BUSY, which would hide a real
         * (possibly terminal) failure behind a "camera busy" retry and delay the
         * recovery path.  So: known transient -> bounded backoff; unknown -> surface
         * the original code without arming the BUSY cooldown. */
        int is_known_transient = (ret == STAGE2_GP_ERROR_TIMEOUT) ||
                                 (ret == STAGE2_GP_ERROR_CAMERA_BUSY);

        if (!is_known_transient) {
            fprintf(stderr, "[stage2] preview: unknown error class (ret=%d) -- "
                            "surfacing the original code without relabelling as "
                            "CAMERA_BUSY and without arming the transient backoff "
                            "(issue #127)\n", ret);
            return ret;
        }

        /* Known transient failure (timeout -10, camera-busy -110): bounded backoff.
         * The K-1 II in PTP mode returns transient errors and the outer pgphoto loop
         * hammers gp_camera_capture_preview back-to-back; if only -10 counted, the
         * cooldown never triggered and the sustained PTP traffic starved the Wi-Fi
         * radio (#55).  Any known-transient result contributes to the budget. */
        const char *maxs = getenv("STAGE2_PENTAX_PREVIEW_BACKOFF_MAX");
        const char *secs = getenv("STAGE2_PENTAX_PREVIEW_BACKOFF_SECS");
        int max_failures = STAGE2_PENTAX_PREVIEW_BACKOFF_MAX_DEFAULT;
        int cooldown_s   = STAGE2_PENTAX_PREVIEW_BACKOFF_SECS_DEFAULT;
        if (maxs && atoi(maxs) > 0)
            max_failures = atoi(maxs);
        if (secs && atoi(secs) > 0)
            cooldown_s = atoi(secs);

        g_pentax_preview_timeouts++;
        if (g_pentax_preview_timeouts >= max_failures) {
            g_pentax_preview_backoff_until = stage2_monotonic_secs() + cooldown_s;
            fprintf(stderr, "[stage2] preview-backoff: %d consecutive transient failures "
                            "(last ret=%d) -- backing off %ds (issues #36/#55/#127)\n",
                    g_pentax_preview_timeouts, ret, cooldown_s);
        }
    } else {
        if (g_pentax_preview_timeouts)
            fprintf(stderr, "[stage2] preview-backoff: recovered after %d "
                            "consecutive failures\n", g_pentax_preview_timeouts);
        g_pentax_preview_timeouts = 0;
        g_pentax_preview_backoff_until = 0;
    }
    return ret;
}

/* Loader-internal wrapper installed in gp_camera_init's slot (see the fill loop).
 * Runs in NORMAL context (not a signal handler), so plain fprintf/getenv/free are
 * fine; stderr stays unbuffered like the rest of the loader. */
static int stage2_shim_gp_camera_init(void *camera, void *context)
{
    /* Resolve + cache the REAL core fns on first use, from the SAME core handle
     * the loader used to fill the other 63 slots. */
    if (!g_real_gp_camera_init && g_stage2_core)
        g_real_gp_camera_init =
            (stage2_gp_camera_init_fn)dlsym(g_stage2_core, "gp_camera_init");
    if (!g_real_gp_camera_get_storageinfo && g_stage2_core)
        g_real_gp_camera_get_storageinfo =
            (stage2_gp_camera_get_storageinfo_fn)
                dlsym(g_stage2_core, "gp_camera_get_storageinfo");

    if (!g_real_gp_camera_init) {
        fprintf(stderr, "[stage2] storage: FATAL real gp_camera_init unresolved "
                        "(core handle %p) -- cannot init\n", g_stage2_core);
        return -1;                                   /* GP_ERROR */
    }

    int ret = g_real_gp_camera_init(camera, context);
    if (ret != 0)                                    /* GP_OK == 0 */
        return ret;                                  /* init failed: pass through */

    /* Issue #127: a fresh session re-arms the preview capability.  A previous
     * session's NOT_SUPPORTED disable must not leak into this one, so clear it
     * (and any stale backoff) on every successful init.  A successful init is also
     * a FRESH/REVALIDATED session generation: clear the transport/session-unhealthy
     * mark (set by an I/O / no-device failure in the previous generation) so real
     * preview traffic can resume against the new session. */
    g_pentax_preview_disabled = 0;
    g_pentax_preview_timeouts = 0;
    g_pentax_preview_backoff_until = 0;
    g_pentax_preview_session_unhealthy = 0;
    g_pentax_preview_last_terminal = 0;

    /* SHIM #4 -- Pentax keep-live-view (issues #36/#55).  After a successful
     * init on a Pentax model, push `pentaxpclvkeep` ON so camera_capture_preview()
     * keeps PC live view running across preview requests instead of tearing it
     * down + restarting per request (which re-enters the NoUpdateImage warmup
     * window and drives the radio-starvation churn).  Vendor mode is already
     * enabled by init, so the widget is available.  Default ON; set
     * STAGE2_PENTAX_KEEP_LV=0 to A/B against the legacy per-frame teardown. */
    {
        const char *klv = getenv("STAGE2_PENTAX_KEEP_LV");
        if ((!klv || strcmp(klv, "0") != 0) && stage2_camera_uses_pentax_keep_lv(camera))
            stage2_pentax_enable_keep_live_view(camera, context);
    }

    /* These tail/config workarounds are supported only by R5 II device traces.
     * Fail closed for Pentax, other cameras, and an unreadable ability record. */
    if (!stage2_camera_uses_r5_shims(camera)) {
        fprintf(stderr, "[stage2] compatibility shims: bypassed for non-R5-II camera\n");
        return ret;
    }

    /* SESSION 20 -- ENV GATE for the storageType write (STAGE2_STORAGE_SHIM).
     * The storage shim writes storageType@+0x1c=2 so Benro's getCameraStorageStatus()
     * returns nonzero -> the app selects enableCaptureTarget(1,1) = Memory-card.
     * On the R5 II that path (device trace) ends at CAPTURE_COMPLETE with an EMPTY
     * event queue: no ObjectAdded / RequestObjectTransfer -> no GP_EVENT_FILE_ADDED
     * -> timeout.  Setting STAGE2_STORAGE_SHIM=0 SKIPS the storage write entirely so
     * storageType stays calloc-0, getCameraStorageStatus()==0, and the app selects
     * enableCaptureTarget(0,0) = Internal-RAM (tethered) target, which streams the
     * image to the host via RequestObjectTransfer instead of waiting on a card-object
     * notification.  Default (unset or != "0") keeps the shim ON (write as today). */
    {
        const char *shim_env = getenv("STAGE2_STORAGE_SHIM");
        if (shim_env && strcmp(shim_env, "0") == 0) {
            fprintf(stderr,
                    "[stage2] storage: shim DISABLED via STAGE2_STORAGE_SHIM=0\n");
            return ret;                              /* leave storageType@+0x1c = 0 */
        }
    }

    int forced = (getenv("STAGE2_STORAGE_FORCE") != NULL);

    if (g_real_gp_camera_get_storageinfo) {
        void *sifs = NULL;
        int   n    = 0;
        int   sret = g_real_gp_camera_get_storageinfo(camera, &sifs, &n, context);
        fprintf(stderr, "[stage2] storage: get_storageinfo ret=%d n=%d\n",
                sret, n);
        if (sret == 0 && n >= 1) {
            *(int *)((char *)camera + STAGE2_BENRO_STORAGETYPE_OFF) =
                STAGE2_BENRO_STORAGETYPE_CARD;
            fprintf(stderr,
                    "[stage2] storage: storageType@+0x1c set to 2 (card)\n");
            free(sifs);
            return ret;
        }
        free(sifs);                                  /* free even on 0/err return */
    } else {
        fprintf(stderr, "[stage2] storage: get_storageinfo unavailable "
                        "(dlsym miss)\n");
    }

    /* Default (un-forced): a 0/err enumeration means we do NOT write, so a truly
     * card-less camera is never misreported as having a card.  The FORCE path is
     * the escape hatch if 2.5.34's own EOS StorageInfo returns 0 on-device. */
    if (forced) {
        *(int *)((char *)camera + STAGE2_BENRO_STORAGETYPE_OFF) =
            STAGE2_BENRO_STORAGETYPE_CARD;
        fprintf(stderr, "[stage2] storage: FORCED storageType=2 "
                        "(STAGE2_STORAGE_FORCE)\n");
    }
    return ret;
}

/* ===========================================================================
 * SHIM #2 -- capturetarget config shim (interop; MIT).  Gated on
 * STAGE2_TETHER_CAPTURE (default OFF).
 * ---------------------------------------------------------------------------
 * DECOUPLE app-display from camera-mode.  With Shim #1 ON the app sees a card
 * (storageType@+0x1c=2 -> no cosmetic "no memory card" warning), which also
 * makes the app request the Memory-card capturetarget.  But on the R5 II the
 * Memory-card target dead-ends at CAPTURE_COMPLETE with an empty event queue
 * (no ObjectTransfer -> no file).  The reliable path is the Internal-RAM
 * (tethered) capturetarget, which streams the image to the host.
 *
 * So when the app pushes a capturetarget config down through gp_camera_set_config
 * we intercept it: if the widget being set is (or contains) `capturetarget` and
 * its value is anything other than "Internal RAM" (e.g. the app selected
 * "Memory card"), we rewrite it to "Internal RAM" before handing the config to
 * the real core.  Net: app shows a card (Shim #1) AND capture streams to host
 * (Shim #2) -- the two are independent.
 *
 * Every OTHER set_config (ISO, shutterspeed, aperture, ...) passes through
 * unchanged.  When STAGE2_TETHER_CAPTURE is unset or "0" the shim is a pure
 * pass-through (real gp_camera_set_config, no inspection).
 *
 * Ships NO proprietary content: the public libgphoto2 widget API plus one
 * capturetarget string constant.
 * ------------------------------------------------------------------------- */
#define STAGE2_CAPTURETARGET_NAME  "capturetarget"
#define STAGE2_CAPTURETARGET_RAM   "Internal RAM"

typedef int (*stage2_gp_camera_set_config_fn)(void *camera, void *widget,
                                              void *context);
typedef int (*stage2_gp_widget_get_child_by_name_fn)(void *widget,
                                                     const char *name,
                                                     void **child);
typedef int (*stage2_gp_widget_get_name_fn)(void *widget, const char **name);
typedef int (*stage2_gp_widget_get_value_fn)(void *widget, void *value);
typedef int (*stage2_gp_widget_set_value_fn)(void *widget, const void *value);

static stage2_gp_camera_set_config_fn        g_real_gp_camera_set_config       = NULL;
static stage2_gp_widget_get_child_by_name_fn g_real_gp_widget_get_child_by_name = NULL;
static stage2_gp_widget_get_name_fn          g_real_gp_widget_get_name         = NULL;
static stage2_gp_widget_get_value_fn         g_real_gp_widget_get_value        = NULL;
static stage2_gp_widget_set_value_fn         g_real_gp_widget_set_value        = NULL;

/* SHIM #3 -- gp_camera_set_single_config wrapper (shares Shim #2's widget helpers
 * and capturetarget constants).  Benro's app sets INDIVIDUAL configs via
 * gp_camera_set_single_config (confirmed: gpManager_update.c calls
 * gp_camera_set_single_config(camera,name,child,context) as the PRIMARY path,
 * falling back to gp_camera_set_config).  Shim #2 only wrapped the
 * gp_camera_set_config tree-walk, so on device the app's capturetarget=Memory-card
 * single-config write slipped past unshimmed -> capture stayed in card mode ->
 * timeout.  This wraps the single-config entry too.  Here the widget passed IS the
 * leaf being set and its name arrives as the `name` ARGUMENT, so no tree walk /
 * get_child_by_name is needed. */
typedef int (*stage2_gp_camera_set_single_config_fn)(void *camera,
                                                     const char *name,
                                                     void *widget, void *context);
static stage2_gp_camera_set_single_config_fn
    g_real_gp_camera_set_single_config = NULL;

/* Loader-internal wrapper installed in gp_camera_set_config's slot (see the fill
 * loop).  Normal (non-signal) context, so fprintf/getenv/dlsym are fine. */
static int stage2_shim_gp_camera_set_config(void *camera, void *widget,
                                            void *context)
{
    /* The real core set_config is needed on EVERY call (it is the pass-through
     * target), so resolve + cache it first. */
    if (!g_real_gp_camera_set_config && g_stage2_core)
        g_real_gp_camera_set_config = (stage2_gp_camera_set_config_fn)
            dlsym(g_stage2_core, "gp_camera_set_config");
    if (!g_real_gp_camera_set_config) {
        fprintf(stderr, "[stage2] capturetarget: FATAL real gp_camera_set_config "
                        "unresolved (core handle %p)\n", g_stage2_core);
        return -1;                                   /* GP_ERROR */
    }

    /* Issue #128 diagnostic: CONFIG writes are deliberately NOT gated by the
     * preview-settle window. A state-changing write cannot safely be discarded
     * on the assumption that the caller will retry it. Preview traffic remains
     * protected by the existing settle gate; config setters pass through. */

    /* Gate: default OFF (unset or "0").  When OFF, pure pass-through. */
    {
        const char *tether = getenv("STAGE2_TETHER_CAPTURE");
        if (!tether || strcmp(tether, "0") == 0)
            return g_real_gp_camera_set_config(camera, widget, context);
    }
    if (!stage2_camera_uses_r5_shims(camera))
        return g_real_gp_camera_set_config(camera, widget, context);

    /* Tether ON: resolve the widget helpers we need (lazy, cached). */
    if (!g_real_gp_widget_get_child_by_name && g_stage2_core)
        g_real_gp_widget_get_child_by_name =
            (stage2_gp_widget_get_child_by_name_fn)
                dlsym(g_stage2_core, "gp_widget_get_child_by_name");
    if (!g_real_gp_widget_get_name && g_stage2_core)
        g_real_gp_widget_get_name = (stage2_gp_widget_get_name_fn)
            dlsym(g_stage2_core, "gp_widget_get_name");
    if (!g_real_gp_widget_get_value && g_stage2_core)
        g_real_gp_widget_get_value = (stage2_gp_widget_get_value_fn)
            dlsym(g_stage2_core, "gp_widget_get_value");
    if (!g_real_gp_widget_set_value && g_stage2_core)
        g_real_gp_widget_set_value = (stage2_gp_widget_set_value_fn)
            dlsym(g_stage2_core, "gp_widget_set_value");

    /* Locate a capturetarget widget: check BOTH the passed widget's own name and
     * a child named "capturetarget" (the app may set the leaf directly or push a
     * config-tree whose child is capturetarget). */
    void *ct = NULL;
    if (g_real_gp_widget_get_name) {
        const char *wname = NULL;
        if (g_real_gp_widget_get_name(widget, &wname) == 0 && wname &&
            strcmp(wname, STAGE2_CAPTURETARGET_NAME) == 0)
            ct = widget;
    }
    if (!ct && g_real_gp_widget_get_child_by_name) {
        void *child = NULL;
        if (g_real_gp_widget_get_child_by_name(widget,
                STAGE2_CAPTURETARGET_NAME, &child) == 0 && child)
            ct = child;
    }

    /* If found and not already Internal RAM, force it. */
    if (ct && g_real_gp_widget_get_value && g_real_gp_widget_set_value) {
        const char *cur = NULL;
        if (g_real_gp_widget_get_value(ct, &cur) == 0 && cur &&
            strcmp(cur, STAGE2_CAPTURETARGET_RAM) != 0) {
            fprintf(stderr, "POLARIS_TRACE: capturetarget shim: forced Internal "
                            "RAM (was %s)\n", cur);
            g_real_gp_widget_set_value(ct, STAGE2_CAPTURETARGET_RAM);
        }
    }

    /* Hand the (possibly rewritten) config to the real core and return its
     * result -- unchanged for ISO/shutter/etc. */
    return g_real_gp_camera_set_config(camera, widget, context);
}

/* Loader-internal wrapper installed in gp_camera_set_single_config's slot (see the
 * fill loop).  Normal (non-signal) context, so fprintf/getenv/dlsym are fine.
 * This is the entry Benro's app actually uses to push individual configs (incl.
 * capturetarget), so it -- not the tree-walk gp_camera_set_config -- is what has
 * to force Internal RAM on device.  Same STAGE2_TETHER_CAPTURE gate as Shim #2. */
static int stage2_shim_gp_camera_set_single_config(void *camera, const char *name,
                                                   void *widget, void *context)
{
    /* The real core single-config is the pass-through target on EVERY call, so
     * resolve + cache it first. */
    if (!g_real_gp_camera_set_single_config && g_stage2_core)
        g_real_gp_camera_set_single_config =
            (stage2_gp_camera_set_single_config_fn)
                dlsym(g_stage2_core, "gp_camera_set_single_config");
    if (!g_real_gp_camera_set_single_config) {
        fprintf(stderr, "[stage2] capturetarget(single): FATAL real "
                        "gp_camera_set_single_config unresolved (core handle %p)\n",
                g_stage2_core);
        return -1;                                   /* GP_ERROR */
    }

    /* Issue #128 diagnostic: CONFIG writes are deliberately NOT gated by the
     * preview-settle window. A state-changing write cannot safely be discarded
     * on the assumption that the caller will retry it. Preview traffic remains
     * protected by the existing settle gate; config setters pass through. */

    /* Gate: default OFF (unset or "0").  When OFF, pure pass-through. */
    {
        const char *tether = getenv("STAGE2_TETHER_CAPTURE");
        if (!tether || strcmp(tether, "0") == 0)
            return g_real_gp_camera_set_single_config(camera, name, widget,
                                                      context);
    }
    if (!stage2_camera_uses_r5_shims(camera))
        return g_real_gp_camera_set_single_config(camera, name, widget, context);

    /* Tether ON: only capturetarget is rewritten; every other name (iso,
     * shutterspeed, aperture, ...) passes straight through.  The name is given
     * directly, and `widget` is the leaf being set -- no tree to walk. */
    if (name && strcmp(name, STAGE2_CAPTURETARGET_NAME) == 0) {
        if (!g_real_gp_widget_get_value && g_stage2_core)
            g_real_gp_widget_get_value = (stage2_gp_widget_get_value_fn)
                dlsym(g_stage2_core, "gp_widget_get_value");
        if (!g_real_gp_widget_set_value && g_stage2_core)
            g_real_gp_widget_set_value = (stage2_gp_widget_set_value_fn)
                dlsym(g_stage2_core, "gp_widget_set_value");

        if (g_real_gp_widget_get_value && g_real_gp_widget_set_value) {
            const char *cur = NULL;
            if (g_real_gp_widget_get_value(widget, &cur) == 0 && cur &&
                strcmp(cur, STAGE2_CAPTURETARGET_RAM) != 0) {
                fprintf(stderr, "POLARIS_TRACE: capturetarget(single) shim: forced "
                                "Internal RAM (was %s)\n", cur);
                g_real_gp_widget_set_value(widget, STAGE2_CAPTURETARGET_RAM);
            }
        }
    }

    /* Hand the (possibly rewritten) config to the real core and return its
     * result -- unchanged for ISO/shutter/etc. */
    return g_real_gp_camera_set_single_config(camera, name, widget, context);
}

/* ---------------------------------------------------------------------------
 * Session 19: env-less-capable dlopen.  Try, in order:
 *   (1) an env override (STAGE2_CORE_PATH / STAGE2_PORT_PATH) -- for tests;
 *   (2) the compiled-in ABSOLUTE default path -- resolves with NO environment
 *       (the single-file patchelf'd path: no LD_LIBRARY_PATH needed);
 *   (3) the bare soname -- resolves via the exe's rpath or LD_LIBRARY_PATH
 *       (the wrapper path, and the qemu harness path).
 * Absolute-first means the self-driving in-firmware binary needs no env vars at
 * all, while the wrapper's explicit LD_LIBRARY_PATH still works via the fallback.
 * ------------------------------------------------------------------------- */
static void *dlopen_pref(const char *env_name, const char *abs_path,
                         const char *soname, const char *label)
{
    const char *ov = env_name ? getenv(env_name) : NULL;
    if (ov && *ov) {
        void *h = dlopen(ov, RTLD_NOW | RTLD_GLOBAL);
        if (h) { fprintf(stderr, "[stage2] dlopen %s via $%s=%s\n",
                         label, env_name, ov); return h; }
        fprintf(stderr, "[stage2] dlopen %s via $%s=%s failed (%s); trying "
                        "defaults\n", label, env_name, ov, dlerror());
    }
    if (abs_path && *abs_path) {
        void *h = dlopen(abs_path, RTLD_NOW | RTLD_GLOBAL);
        if (h) { fprintf(stderr, "[stage2] dlopen %s via abs %s\n",
                         label, abs_path); return h; }
        /* absolute miss is normal under the qemu harness / wrapper -- fall back */
    }
    void *h = dlopen(soname, RTLD_NOW | RTLD_GLOBAL);
    if (h) fprintf(stderr, "[stage2] dlopen %s via soname %s (rpath/"
                           "LD_LIBRARY_PATH)\n", label, soname);
    return h;
}

/* ---------------------------------------------------------------------------
 * Crash-pinpoint handler.  If ANYTHING still faults (dlopen, a slot write, or a
 * jump to a bad target), log exactly where before dying.
 * ------------------------------------------------------------------------- */
static void stage2_crash_handler(int sig, siginfo_t *si, void *uc)
{
    uintptr_t fault = (uintptr_t)(si ? si->si_addr : 0);
    uintptr_t pc = 0;
#ifndef STAGE2_NO_CONSTRUCTOR
    if (uc) {
        ucontext_t *u = (ucontext_t *)uc;
        pc = (uintptr_t)u->uc_mcontext.arm_pc;   /* ARM EABI */
    }
#else
    (void)uc; /* Native offline shim test: ARM program counter is unavailable. */
#endif

    s_write("\n[stage2] *** CRASH sig=");
    s_write_dec(sig);
    s_write(" (");
    s_write(sig == SIGSEGV ? "SIGSEGV" : sig == SIGBUS ? "SIGBUS" :
            sig == SIGILL ? "SIGILL" : "?");
    s_write(") si_addr=");
    s_write_hex(fault);
    s_write(" pc=");
    s_write_hex(pc);
    s_write("\n");

    /* Classify the fault address vs the slot region. */
    s_write("[stage2]   slot region [");
    s_write_hex(STAGE2_SLOT_LO);
    s_write(",");
    s_write_hex(STAGE2_SLOT_HI);
    s_write(")  ");
    if (fault >= STAGE2_SLOT_LO && fault < STAGE2_SLOT_HI) {
        s_write("si_addr IS inside the slot region -> slot ");
        s_write(slot_name(fault & ~3u));
        s_write("\n");
    } else {
        s_write("si_addr is NOT in the slot region\n");
    }

    /* Is PC a null jump, the abort stub, or one of the slot targets? */
    s_write("[stage2]   pc classify: ");
    if (pc == 0) {
        s_write("NULL jump (an unfilled slot == 0 was called -- exactly the "
                "pre-fix race)\n");
    } else if (pc == (uintptr_t)stage2_abort_stub) {
        s_write("== stage2_abort_stub (fail-closed landing pad)\n");
    } else {
        const char *hit = NULL;
        for (size_t i = 0; i < STAGE2_SLOTS_LEN; i++) {
            uintptr_t tgt = *(volatile uintptr_t *)STAGE2_SLOTS[i].slot;
            if (tgt == pc) { hit = STAGE2_SLOTS[i].name; break; }
        }
        if (hit) {
            s_write("== target of slot ");
            s_write(hit);
            s_write(" (jump to a resolved/bad target)\n");
        } else {
            s_write("not null, not the stub, not a current slot target\n");
        }
    }

    s_write("[stage2]   last checkpoint reached: ");
    s_write((const char *)g_last_ckpt);
    s_write("\n");

    /* Restore default disposition and re-raise so the real exit code (139/…)
     * remains visible to the launcher. */
    signal(sig, SIG_DFL);
    raise(sig);
}

static void install_crash_handler(void)
{
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = stage2_crash_handler;
    sa.sa_flags = SA_SIGINFO;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGSEGV, &sa, NULL);
    sigaction(SIGBUS,  &sa, NULL);
    sigaction(SIGILL,  &sa, NULL);
}

/* ---------------------------------------------------------------------------
 * TEST-ONLY hooks (env-gated; production no-ops unless the env var is set).
 * They let the single-threaded qemu harness exercise the two device-only paths.
 * ------------------------------------------------------------------------- */
static void maybe_test_early_call(void)
{
    /* Simulate "a boundary fn is called before its slot is filled": reproduce the
     * in-file trampoline's second instruction by hand -- `ldr pc,[r12]` with
     * r12 == &slot -- during the pre-fill window.  The slot currently holds
     * &stage2_abort_stub, so this lands in the stub with r12==&slot exactly like
     * the real trampoline, giving a clean named abort (exit 97) instead of a null
     * jump.  This needs no dynamic symbol export (a non-PIE harness/pgphoto does
     * not put gp_* in .dynsym), so it faithfully models the device path. */
    if (!getenv("STAGE2_TEST_EARLY_CALL")) return;
    uintptr_t slot = STAGE2_SLOTS[16].slot;        /* gp_camera_init's slot */
    s_write("[stage2] TEST: a thread calls gp_camera_init via its trampoline "
            "BEFORE fill (expect clean abort stub, NOT segfault)\n");
#ifdef STAGE2_NO_CONSTRUCTOR
    stage2_abort_report(slot);
#else
    __asm__ volatile(
        "mov r12, %0\n\t"
        "ldr pc, [r12]\n\t"                        /* == the trampoline's 2nd insn */
        : : "r"(slot) : "r12", "memory");
#endif
}

static void maybe_test_segv(void)
{
    /* Deliberately fault so the crash handler's output can be inspected.  Use a
     * NULL-pointer DATA write (si_addr==0, pc==the faulting store): qemu-user
     * delivers this to the guest handler cleanly.  (A null EXECUTE / jump-to-0
     * would trip an unrelated qemu-user TB-translation assertion, not our code;
     * on the real device the same handler catches the pc==0 null-jump too.) */
    if (!getenv("STAGE2_TEST_SEGV")) return;
    s_write("[stage2] TEST: forcing a deliberate NULL-pointer write to exercise "
            "the crash handler\n");
    *(volatile int *)0 = 0;
}

/* ---------------------------------------------------------------------------
 * Session 18: create the slot page.  The slots are NOT the executable's .bss any
 * more (the device's kernel did not reliably map the extended-.bss region
 * writable).  This is the constructor's first memory action: confirm nothing
 * already overlaps the fixed slot region, then mmap a fresh anonymous
 * PROT_READ|PROT_WRITE page MAP_FIXED at STAGE2_SLOT_BASE.
 *
 *   - overlap (something already mapped there): log the offending /proc/self/maps
 *     line and _exit(96) -- REFUSE, never MAP_FIXED-clobber a live mapping.  On
 *     the real device this is what confirms STAGE2_SLOT_BASE is actually free: if
 *     a future firmware maps something there, the loader aborts cleanly instead of
 *     corrupting it.
 *   - mmap failure: log errno and _exit(97) -- never proceed without the page.
 *
 * On success the guaranteed-fresh RW page is in place before slots-safe-init
 * writes &abort_stub into every slot.
 * ------------------------------------------------------------------------- */
static void map_slot_page(void)
{
    const uintptr_t lo = STAGE2_SLOT_LO;
    const uintptr_t hi = STAGE2_SLOT_LO + STAGE2_SLOT_PAGE;

    /* TEST-ONLY (env-gated; production no-op): pre-occupy the slot page so the
     * overlap pre-check below trips.  Single-threaded qemu cannot otherwise force
     * a collision at a fixed vaddr; this models "something is already mapped
     * there" so the refuse-not-clobber path is exercised by exit code. */
    if (getenv("STAGE2_TEST_MAP_OVERLAP")) {
        mmap((void *)lo, STAGE2_SLOT_PAGE, PROT_READ,
             MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
        s_write("[stage2] TEST: pre-occupied the slot page to exercise the "
                "overlap pre-check (expect clean refusal, exit 96)\n");
    }

    /* Pre-check: refuse if ANYTHING already overlaps [lo,hi). */
    FILE *mf = fopen("/proc/self/maps", "r");
    if (mf) {
        char line[512];
        while (fgets(line, sizeof line, mf)) {
            unsigned long s = 0, e = 0;
            if (sscanf(line, "%lx-%lx", &s, &e) == 2 &&
                (uintptr_t)s < hi && (uintptr_t)e > lo) {
                fprintf(stderr,
                        "[stage2] FATAL slot page [%#lx,%#lx) already mapped -- "
                        "refusing to clobber it. Offending region: %s",
                        (unsigned long)lo, (unsigned long)hi, line);
                fclose(mf);
                _exit(96);
            }
        }
        fclose(mf);
    } else {
        /* Cannot read maps -> cannot prove the region is free.  Do NOT blindly
         * MAP_FIXED (that could clobber).  Abort cleanly. */
        fprintf(stderr, "[stage2] FATAL cannot open /proc/self/maps (%s) -- "
                        "cannot confirm slot page @%#lx is free; aborting\n",
                strerror(errno), (unsigned long)lo);
        _exit(96);
    }

    /* TEST-ONLY (env-gated; production no-op): force the mmap to fail to exercise
     * the mmap-failure abort by exit code.  Drop MAP_ANONYMOUS while keeping fd=-1
     * -> the kernel returns EBADF (reliable under qemu-user, unlike len 0). */
    int flags = MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED;
    if (getenv("STAGE2_TEST_MAP_FAIL")) flags = MAP_PRIVATE | MAP_FIXED;

    void *p = mmap((void *)lo, STAGE2_SLOT_PAGE, PROT_READ | PROT_WRITE,
                   flags, -1, 0);
    if (p == MAP_FAILED || (uintptr_t)p != lo) {
        int en = errno;
        fprintf(stderr,
                "[stage2] FATAL mmap slot page @%#lx failed: errno=%d (%s) -- "
                "never proceeding without a writable slot page; aborting\n",
                (unsigned long)lo, en, strerror(en));
        _exit(97);
    }
    g_last_ckpt = "mmap slot page ok";
    fprintf(stderr, "[stage2] mmap slot page @%#lx ok (fresh RW anon page, "
                    "%u B)\n", (unsigned long)lo, STAGE2_SLOT_PAGE);
}

/* Still capture must preserve the exact dlsym target.  Keep this decision in a
 * small testable helper so a future Stage-2 policy cannot silently reintroduce
 * the extra capture ABI boundary. */
static void *stage2_capture_slot_target(const char *name, void *resolved)
{
    if (name && strcmp(name, "gp_camera_capture") == 0)
        return resolved;
    return resolved;
}

/* STAGE2_NO_CONSTRUCTOR is defined ONLY by the offline unit test that #includes
 * this file to exercise the shims directly; production builds always run the
 * constructor at load. */
#ifndef STAGE2_NO_CONSTRUCTOR
__attribute__((constructor))
#endif
static void stage2_ondisk_init(void)
{
    /* Unbuffered stderr so a crash never hides the last checkpoint. */
    setvbuf(stderr, NULL, _IONBF, 0);

    /* (2) Crash handler FIRST -- so a fault anywhere below is pinpointed. */
    install_crash_handler();

    /* (0) SLOT PAGE FIRST -- create the guaranteed-writable slot page (Session 18)
     * before any slot is touched.  Confirms the region is free, then MAP_FIXED an
     * anonymous RW page; refuses cleanly (never clobbers) on overlap / mmap fail. */
    map_slot_page();

    /* (1) SLOTS-SAFE-INIT -- before dlopen, before resolution, before the
     * CAMLIBS log.  Every slot -> &abort_stub, then a store barrier so other
     * threads (spCamera IPC / httpd, or a re-exec sibling) observe the stub
     * immediately.  These are plain stores into the fresh RW anon page mmap'd
     * above -- no mprotect, no .text write.  A re-exec (execve of self) gives a
     * fresh address space, so each pass's constructor maps its own page and
     * stub-fills cleanly (no inherited slot page to trip the overlap check). */
    for (size_t i = 0; i < STAGE2_SLOTS_LEN; i++)
        slot_store(STAGE2_SLOTS[i].slot, (void *)stage2_abort_stub);
    __sync_synchronize();                       /* publish the stub to all threads */
    g_last_ckpt = "init: stubbed slots";
    fprintf(stderr, "[stage2] init: stubbed %zu slots (fail-closed baseline; "
                    "slot base %#lx)\n",
            STAGE2_SLOTS_LEN, (unsigned long)STAGE2_SLOT_LO);

    /* Point the self-contained core at the Stage-2 camlib/iolib dirs.
     * overwrite=0: a command-line CAMLIBS/IOLIBS override wins. */
    setenv("CAMLIBS", STAGE2_CAMLIBS_DIR, 0);
    setenv("IOLIBS",  STAGE2_IOLIBS_DIR,  0);
    fprintf(stderr, "[stage2] on-disk loader: CAMLIBS=%s IOLIBS=%s\n",
            getenv("CAMLIBS"), getenv("IOLIBS"));

    maybe_test_early_call();   /* env-gated; no-op in production */
    maybe_test_segv();         /* env-gated; no-op in production */

    void *core = dlopen_pref("STAGE2_CORE_PATH", STAGE2_CORE_PATH,
                             STAGE2_CORE_SONAME, "core");
    if (!core) {
        fprintf(stderr, "[stage2] dlopen core FAILED (%s) -- all %zu slots left "
                        "at abort stub (fail-closed)\n", dlerror(),
                STAGE2_SLOTS_LEN);
        return;
    }
    g_last_ckpt = "dlopen core ok";
    fprintf(stderr, "[stage2] dlopen core ok\n");
    g_stage2_core = core;   /* SHIM #1: source handle for the shim's lazy dlsym */

    void *port = dlopen_pref("STAGE2_PORT_PATH", STAGE2_PORT_PATH,
                             STAGE2_PORT_SONAME, "port");
    if (!port) {
        fprintf(stderr, "[stage2] dlopen port FAILED (%s) -- all %zu slots left "
                        "at abort stub (fail-closed)\n", dlerror(),
                STAGE2_SLOTS_LEN);
        return;
    }
    g_last_ckpt = "dlopen port ok";
    fprintf(stderr, "[stage2] dlopen port ok\n");

    /* Resolve each boundary symbol and store it into its slot. */
    unsigned filled = 0, unresolved = 0;
    for (size_t i = 0; i < STAGE2_SLOTS_LEN; i++) {
        const char *name = STAGE2_SLOTS[i].name;
        void *t = dlsym(core, name);
        if (!t) t = dlsym(port, name);
        if (!t) {
            fprintf(stderr, "[stage2] unresolved %s -- slot 0x%08lx left at abort "
                            "stub\n", name, (unsigned long)STAGE2_SLOTS[i].slot);
            unresolved++;
            continue;                                  /* slot stays = abort stub */
        }
        /* SHIM #1: gp_camera_init is the ONE slot redirected to a loader-internal
         * wrapper (stage2_shim_gp_camera_init), which then calls the real core
         * init `t` (via g_stage2_core) and populates Benro's storageType@+0x1c
         * after a successful init.  All other 63 slots go DIRECT to the core/port
         * target.  Match by EXACT boundary symbol name (robust to slot ordering). */
        if (strcmp(name, "gp_camera_init") == 0) {
            slot_store(STAGE2_SLOTS[i].slot, (void *)&stage2_shim_gp_camera_init);
            fprintf(stderr, "[stage2] storage: gp_camera_init slot -> shim "
                            "(real core fn cached for pass-through)\n");
            filled++;
            continue;
        }
        /* SHIM #2: gp_camera_set_config is redirected to the capturetarget
         * wrapper (stage2_shim_gp_camera_set_config).  It forces the camera's
         * capturetarget to Internal RAM (when STAGE2_TETHER_CAPTURE is ON) while
         * every other config passes straight through to the real core fn. */
        if (strcmp(name, "gp_camera_set_config") == 0) {
            slot_store(STAGE2_SLOTS[i].slot,
                       (void *)&stage2_shim_gp_camera_set_config);
            fprintf(stderr, "[stage2] capturetarget: gp_camera_set_config slot -> "
                            "shim (real core fn cached for pass-through)\n");
            filled++;
            continue;
        }
        /* SHIM #3: gp_camera_set_single_config is redirected to the single-config
         * capturetarget wrapper (stage2_shim_gp_camera_set_single_config) -- the
         * entry Benro's app actually uses to set individual configs (the primary
         * path per gpManager_update.c).  Same STAGE2_TETHER_CAPTURE gate + Internal
         * RAM forcing as Shim #2; every other single-config passes straight
         * through.  Belt-and-suspenders with the Shim #2 tree-walk fallback. */
        if (strcmp(name, "gp_camera_set_single_config") == 0) {
            slot_store(STAGE2_SLOTS[i].slot,
                       (void *)&stage2_shim_gp_camera_set_single_config);
            fprintf(stderr, "[stage2] capturetarget: gp_camera_set_single_config "
                            "slot -> shim (real core fn cached for pass-through)\n");
            filled++;
            continue;
        }
        /* SHIM #5: gp_camera_capture_preview is redirected to the Pentax
         * preview-backoff wrapper (stage2_shim_gp_camera_capture_preview).  It
         * counts consecutive GP_ERROR_TIMEOUT results and backs off before the
         * next request, bounding pgphoto's otherwise-unbounded preview loop so
         * a dead PC-LV session cannot starve the Wi-Fi radio (#55).  Pure
         * pass-through for non-Pentax models or STAGE2_PENTAX_PREVIEW_BACKOFF=0. */
        if (strcmp(name, "gp_camera_capture_preview") == 0) {
            slot_store(STAGE2_SLOTS[i].slot,
                       (void *)&stage2_shim_gp_camera_capture_preview);
            fprintf(stderr, "[stage2] preview-backoff: gp_camera_capture_preview "
                            "slot -> shim (real core fn cached for pass-through)\n");
            filled++;
            continue;
        }
        /* Still capture deliberately remains direct-to-core.  The historical
         * Stage-2 wrapper added a second function-call/ABI boundary around
         * gp_camera_capture and the first-shot K-3 III failures at o-v12j/k/n
         * all crashed at that boundary before the core returned.  Capture
         * readiness, candidate ownership and bounded recovery belong to the
         * matched libgphoto2 core; Stage-2 must not interpose another policy. */
        slot_store(STAGE2_SLOTS[i].slot,
                   stage2_capture_slot_target(name, t));
        filled++;
    }
    g_last_ckpt = "resolved slots";
    fprintf(stderr, "[stage2] resolved %u/%zu\n", filled, STAGE2_SLOTS_LEN);

    /* Publish all slot writes before main() (and Benro's first boundary call)
     * can observe them. */
    __sync_synchronize();
    g_last_ckpt = "slots filled";

    fprintf(stderr, "[stage2] slots filled %u/%zu%s\n",
            filled, STAGE2_SLOTS_LEN,
            unresolved ? " [some unresolved: left at abort stub, fail-closed]"
                       : "");
}
