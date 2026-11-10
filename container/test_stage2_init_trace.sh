#!/bin/sh
# Behavioural test for the issue #297 one-shot init trace (STAGE2_TRACE_INIT_ENTRY).
#
# Why this exists: container/test_stage2_loader_compile.sh proves the loader *builds* for ARM,
# and nothing else can. The shim is static (the .so exports 12 symbols and gp_camera_init is not
# among them), so it cannot be called from outside; stage2_crash_handler reads ARM-only
# mcontext_t fields so the file will not compile on x86; and there is no qemu-arm in PATH here
# (only qemu-arm-static, which needs an ARM dynamic loader we do not have). So the trace logic
# had no coverage at all.
#
# Rather than hand-copy the helper -- which would silently keep passing if production changed --
# this extracts the real definition from container/stage2_loader.c with awk and compiles that.
# If the helper is renamed, its gating changes, or its per-site flag array is collapsed back to a
# single flag, extraction fails or an assertion fires.
#
# Each case runs in a fresh child process on purpose: g_init_entry_traced is process-global by
# design (one line per site per process), so cases sharing a process would legitimately see
# silence after the first one. An earlier revision of this test made that mistake and reported
# three false failures while the code under test was correct.
set -eu

dir="$(cd "$(dirname "$0")" && pwd)"
src="$dir/stage2_loader.c"
cc="${CC:-gcc}"

command -v "$cc" >/dev/null 2>&1 || { echo "SKIP: no C compiler" >&2; exit 77; }
[ -f "$src" ] || { echo "SKIP: $src not found" >&2; exit 77; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT HUP INT TERM

# --- extract the helper verbatim from production source -----------------------
awk '/^#define STAGE2_INIT_TRACE_SITES/,/^}$/' "$src" > "$work/helper.inc"

if ! grep -q 'stage2_trace_init_entry' "$work/helper.inc"; then
    echo "FAIL: could not extract stage2_trace_init_entry from $src" >&2
    echo "      the helper was renamed or its shape changed; update this test deliberately." >&2
    exit 1
fi

# Non-vacuity guard: the extraction must contain the per-site array, not a lone flag.
if ! grep -q 'g_init_entry_traced\[STAGE2_INIT_TRACE_SITES\]' "$work/helper.inc"; then
    echo "FAIL: extracted helper has no per-site flag array" >&2
    echo "      a single shared flag lets the first trace suppress the rest, which defeats" >&2
    echo "      the never-entered / refused / reached-core distinction this probe exists for." >&2
    exit 1
fi

cat > "$work/t.c" <<'CEOF'
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>

#include "helper.inc"

static void child_run(int calls, int skip_core)
{
    int i;
    for (i = 0; i < calls; i++) {
        stage2_trace_init_entry(STAGE2_TR_ENTER, "ENTER gp_camera_init", 0);
        /* skip_core models the capture guard returning before the core call. */
        if (!skip_core) {
            stage2_trace_init_entry(STAGE2_TR_CORE, "gp_camera_init -> real core", 0);
            stage2_trace_init_entry(STAGE2_TR_RESULT, "gp_camera_init returned %d", -110);
        }
    }
}

static int run_child(int calls, int skip_core, const char *envval, char *buf, size_t cap)
{
    pid_t p; FILE *f; long sz;
    buf[0] = '\0';
    p = fork();
    if (p < 0) { perror("fork"); return -1; }
    if (p == 0) {
        if (envval) setenv("STAGE2_TRACE_INIT_ENTRY", envval, 1);
        else        unsetenv("STAGE2_TRACE_INIT_ENTRY");
        if (freopen("stderr.capture", "w", stderr) == NULL) _exit(9);
        child_run(calls, skip_core);
        fflush(stderr);
        _exit(0);
    }
    waitpid(p, NULL, 0);
    f = fopen("stderr.capture", "r");
    if (!f) { perror("open capture"); return -1; }
    sz = (long)fread(buf, 1, cap - 1, f);
    if (sz < 0) sz = 0;
    buf[sz] = '\0';
    fclose(f);
    return 0;
}

static int count_lines(const char *out, const char *needle)
{
    int n = 0; const char *p = out;
    while ((p = strstr(p, needle)) != NULL) { n++; p += strlen(needle); }
    return n;
}

static int fails = 0;
static void expect(const char *what, int got, int want)
{
    if (got == want) printf("  ok   %-48s got %d\n", what, got);
    else { printf("  FAIL %-48s got %d want %d\n", what, got, want); fails++; }
}

int main(void)
{
    static char buf[65536];

    printf("case 1: env unset -> silent even after 50 calls\n");
    if (run_child(50, 0, NULL, buf, sizeof buf) == 0) {
        expect("ENTER lines", count_lines(buf, "ENTER gp_camera_init"), 0);
        expect("core lines",  count_lines(buf, "real core"), 0);
        expect("result lines", count_lines(buf, "returned"), 0);
    }

    printf("case 2: env=1 -> one line per site, not one per call\n");
    if (run_child(50, 0, "1", buf, sizeof buf) == 0) {
        expect("ENTER lines (50 calls)", count_lines(buf, "ENTER gp_camera_init"), 1);
        expect("core lines (50 calls)",  count_lines(buf, "real core"), 1);
        expect("result lines (50 calls)", count_lines(buf, "returned"), 1);
        expect("return code rendered",   count_lines(buf, "returned -110"), 1);
    }

    printf("case 3: env=0 -> treated as unset\n");
    if (run_child(50, 0, "0", buf, sizeof buf) == 0) {
        expect("ENTER lines", count_lines(buf, "ENTER gp_camera_init"), 0);
        expect("total trace lines", count_lines(buf, "[stage2] init:"), 0);
    }

    printf("case 4: capture-guard path -- ENTER fires, core/result stay silent\n");
    if (run_child(50, 1, "1", buf, sizeof buf) == 0) {
        expect("ENTER present", count_lines(buf, "ENTER gp_camera_init"), 1);
        expect("core absent (guard refused)",   count_lines(buf, "real core"), 0);
        expect("result absent (never called)",  count_lines(buf, "returned"), 0);
    }

    printf("\n%s\n", fails ? "FAILED" : "ALL PASS");
    return fails ? 1 : 0;
}
CEOF

"$cc" -std=gnu11 -Wall -Wextra -I"$work" -o "$work/t" "$work/t.c"
cd "$work" && ./t
