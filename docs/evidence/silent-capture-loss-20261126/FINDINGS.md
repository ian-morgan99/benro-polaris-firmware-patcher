# A capture reported success and told the client it was done; no file exists anywhere on the device

2026-11-26, K-1 II rig (v118, `o-v18a`), first capture after a reboot. This is a **silent data-loss / false
success** path, and it is distinct from the wedge investigated earlier today.

## The sequence

```text
[20:43:35:556] will captureImage status:1  sPath:/app/sd/normal/SP_0050.jpg
[pentax] capture=1 boundary=camlib-enter transfer=0 recovery=1 output_pending=0
[pentax] capture=1 boundary=preconditions-return ptp=0x2001 size=576
[pentax] capture=1 boundary=initiate-enter focus=2 companions=1
[pentax] capture=1 boundary=initiate-return ptp=0x200c
[pentax-recovery] capture=1 path=initiate reason=initiate-not-confirmed ptp=0x200c gp=-8 output_pending=0
                   action=do-not-replay-initiate; resolve-ambiguous-output-before-next-request
[20:43:41:960] captureImage ret 0            <-- success
```

**I first wrote that `PTP 0x200c` is DeviceBusy. That is wrong.** `ptp.h:1241` defines
`PTP_RC_StoreFull = 0x200C`; DeviceBusy is `0x2019`. So the camera reported **storage full**, not busy — which
is also why the GP code is `-8` and not `-110`: `translate_ptp_result` maps StoreFull to
`GP_ERROR_FIXED_LIMIT_EXCEEDED` (-8) and DeviceBusy to `GP_ERROR_CAMERA_BUSY` (-110). That distinction turns out
to be the whole reason this failure is silent rather than reported; see the root cause below.

Our camlib did the right thing: it refused to replay, kept `output_pending=0`, and returned an error (`gp=-8`)
via `goto out` — `library.c` ends the capture path with `return ret`, so the error is propagated by us.

**polestar_app then logged `captureImage ret 0`.**

## What the client was told

Every 264 frame sent for SP_0050, complete:

```text
val[state:1;focus:-1000;leve:1;b:0;path:/app/sd/normal/SP_0050.jpg;c:-1]
val[state:1;/app/sd/normal/SP_0050.jpg]
val[state:2;/app/sd/normal/SP_0050.jpg]
val[state:5; ]
```

No error frame. A client watching this believes the capture completed.

## The missing state:4 is the tell

Comparing with the last successful capture (SP_0049, same rig, 20:04):

```text
GOOD: state:1 -> state:4;K1II8836.JPG -> ret 0 -> state:2 -> state:3 -> state:5 -> state:1 -> state:1;ret:0
BAD:  state:1 ->                (no state:4) -> ret 0 -> state:2 -> state:5
```

`state:4` carries the camera's own filename and is the only frame proving an exposure actually produced an
object. It is emitted by **all 37** successful captures and by **none** of this one.

**This reproduced twice.** The authoritative count comes from `capture-outcomes.py` run over fresh rig logs:
**37 PASS and 2 FAIL**, naming SP_0050 and SP_0051. Do not derive this by comparing global line counts — see
"Why a global counter is the wrong method" below. The second occurrence, SP_0051 at 20:50:51, was produced by
my own frame-dump probe:

```text
val[state:1;focus:-1000;leve:1;b:0;path:/app/sd/normal/SP_0051.jpg;c:-1]
val[state:1;/app/sd/normal/SP_0051.jpg]
initiate-return ptp=0x200c
captureImage ret 0        p:   ;          <- empty path, same signature
val[state:2;/app/sd/normal/SP_0051.jpg]
val[state:5; ]
$ ls /app/sd/normal/SP_0051.jpg           -> MISSING
```

Identical signature to SP_0050: StoreFull (`0x200c`), `ret 0`, empty path, no `state:4`, no file. Both were triggered by
me, which is how I know they are real losses rather than log artifacts — I asked for two captures and got zero
files and two successes.

## The file does not exist

```text
$ find /app /tmp /var -name "SP_0050*"      -> (nothing)
$ ls /app/sd/normal/ | tail -1              -> SP_0049.jpg  (20:04, from the previous boot)
$ ls /app/sd/normal/SP_0050.jpg             -> No such file or directory
```

So: shutter never fired, no object on the camera, nothing downloaded, and both the app's return code and the
client-visible protocol say success.

## Where it is *not* our bug

Checked and ruled out:

- **Our camlib** returns the error correctly (`return ret` at the end of the capture path; `ret != GP_OK`
  branches preserve the candidate rather than clearing state).
- **Our stage2 shim** contains a false-success guard for exactly this class — issue #183, empty returned path
  — and passes `ret` through unchanged otherwise. It is on by default (`STAGE2_CAPTURE_EMPTY_PATH_CHECK`
  unset means enabled) and the code is present in the deployed binary:
  ```text
  $ strings /app/lib/stage2/libpolaris_stage2.so | grep -c "capture-outcome=empty-path"   -> 1
  ```

**The wrapper was in fact installed and in the call path — settled read-only, after I first called this
unobservable.** `stage2_capture_slot_target()` installs it silently:

```c
if (name && strcmp(name, "gp_camera_capture") == 0) {
    if (stage2_capture_trace_enabled() || stage2_capture_guard_enabled() ||
        stage2_capture_empty_path_check_enabled()) {
        g_real_gp_camera_capture = (stage2_gp_camera_capture_fn)resolved;
        return (void *)&stage2_guarded_gp_camera_capture;
    }
}
```

Unlike every other slot it has **no `fprintf`** — the boot log prints `storage: gp_camera_init slot -> shim`,
`capturetarget: gp_camera_set_config slot -> shim`, `shutter-fallback: ... slot -> shim (issue #187)` and
`preview-backoff: gp_camera_capture_preview slot -> shim`, and nothing for `gp_camera_capture`. So the install
cannot be confirmed from the boot log, and my first draft inferred it. It can be confirmed from configuration:

```text
$ grep -n STAGE2_CAPTURE_EMPTY_PATH_CHECK /app/bin/pgphoto
30:export STAGE2_CAPTURE_EMPTY_PATH_CHECK=${STAGE2_CAPTURE_EMPTY_PATH_CHECK:-1}
# ... This check installs the wrapper on its own merit (independent of the opt-in
# STAGE2_CAPTURE_GUARD in-flight guard). Keep it explicit in release images; "0" is
# the documented escape hatch for a diagnostic run.
```

The release launcher sets it to `1`, and the loader's own default is also enabled (`!e || e != "0"`). The
running process environment contains no disabling value. So `stage2_capture_empty_path_check_enabled()` is
true, the condition above holds, and **`stage2_guarded_gp_camera_capture` was in the path for SP_0050**.

That makes the localization firm rather than inferred: the wrapper only rewrites a result when
`ret == 0 && (name empty || folder empty)`. The core returned `-8`, so the wrapper returned `-8` unchanged.

That passthrough is not just read off the source — it is asserted by an existing test, which passes:

```text
$ bash container/test_stage2_capture_empty_path.sh
PASS: issue #183 empty-path capture conversion (7 cases)
```

Case 6 is the relevant one: *"a real error keeps its own class; the conversion never masks it"* — with
`fake_capture_ret = STAGE2_GP_ERROR_TIMEOUT` and an empty path, it asserts the result stays
`STAGE2_GP_ERROR_TIMEOUT` rather than being rewritten to `CAMERA_ERROR`. So a core failure provably survives
the wrapper intact.
**The conversion from `-8` to `captureImage ret 0` therefore happens above our shim.** It can be pinned further,
inside pgphoto's own `capture_image()`. SP_0050's window in `Clog_000039.log`, untruncated:

```text
[20:43:35:707] capture_image[3076]:----capture
[20:43:35:737] capture_image[3092]:---- will CAPTURE_IMAGE
[pentax] capture=1 boundary=initiate-return ptp=0x200c
ERROR: Could not capture image.
ERROR: Could not capture.
[20:43:41:856] capture_image[3096]:----ARG_CAPTURE_IMAGE  0
[20:43:41:956] capture_image[3164]:----capture end   -6249 ms
[20:43:41:959] capture_image[3171]:----get file to buffer   -2 ms
[20:43:41:959] capture_image[3176]:----capture out
[20:43:41:960] captureImage[1579]:----captureImage ret 0  p:   ;
```

**pgphoto knows the capture failed.** It prints `ERROR: Could not capture image.` and `ERROR: Could not
capture.` itself, immediately after our camlib returns `0x200c` — and then continues through `capture end`,
`get file to buffer`, `capture out`, and hands back success. The same lines appear for SP_0051.

For contrast, the successful SP_0049 has no ERROR lines at all between `will CAPTURE_IMAGE` and
`ARG_CAPTURE_IMAGE 0`. So those two lines are the discriminator, and the loss is between pgphoto logging its
own failure (around `capture_image` line 3092) and returning to polestar_app (line 3096 onward).

I do not have pgphoto's source, so I cannot name the exact statement that drops the error — but the observable
sequence is unambiguous: **the error is detected and discarded inside pgphoto**, not in our camlib or our shim.

(A method note: my first pass attributed these ERROR lines to SP_0051 because `awk "/20:43:35/,/20:43:42/"`
never matched an end pattern and so ran to EOF, sweeping in the next capture. Re-done with a bounded `sed` range
and `head`, which puts them inside SP_0050's own window.)

## Root cause: pgphoto propagates only an allowlist of error codes, and `-8` is not on it

Found in the local Ghidra reconstruction at
`~/Documents/VSCodeProjects/PrivateResearch/pgphoto-re/decompiled/gpManager.decompiled.c`, `capture_generic()`
(address `0x000fa938`). **Provenance caveat first:** this is Ghidra output from `pgphoto.stock`, not Benro
source — no Benro `.c` exists; statement text is a reconstruction of ARM machine code and should be read as
reference for behaviour, never as the upstream file.

```c
result = gp_camera_capture(...);
if (result != 0) {
    cli_error_print("Could not capture image.");        /* the first ERROR line */
LAB_000fae68:
    if (result != 0) {
        cli_error_print("Could not capture.");          /* the second ERROR line */
        if (result == -6)   return -6;
        if (result == -3)   return -3;
        if (result == -0x70) return -0x70;               /* -112 GP_ERROR_CANCEL */
        if (result == -0x73) return -0x73;               /* -115 GP_ERROR_NO_SPACE */
        if (result == -0x35) return -0x35;
        if (result == -0x3c) return -0x3c;
        if (result == -0x6e) return -0x6e;               /* -110 GP_ERROR_CAMERA_BUSY */
        if (result == -0x72) return -0x72;               /* -114 GP_ERROR_OS_FAILURE */
    }
    goto LAB_000faf04;                                  /* <-- no return: treated as success */
}
```

**This is the bug, and it explains why `-110` is reported while `-8` is not.** The list contains `-0x6e` =
`-110` (`GP_ERROR_CAMERA_BUSY`, i.e. DeviceBusy `0x2019`) but **not `-8`** (`GP_ERROR_FIXED_LIMIT_EXCEEDED`,
i.e. StoreFull `0x200c`). A busy camera therefore returns an error to polestar_app; a camera whose card is full
prints two ERROR lines, falls through to `LAB_000faf04`, and continues into the download path as if the
exposure had happened.

That also resolves the `-110` vs `-8` question that otherwise looks inconsistent: both are "camera refused to
capture", but only one of them is on pgphoto's list.

The fix is small and local: propagate unmapped failures instead of falling through — either add
`GP_ERROR_FIXED_LIMIT_EXCEEDED`, or better, invert the logic so any non-zero `result` returns rather than only
the enumerated ones. The latter cannot regress into silence for codes nobody thought to enumerate.

### Confirmed empirically, without relying on the decompile

The deployed binary is our patched variant — md5 `79d4454f…`, matching none of the four pgphoto builds in
`PrivateResearch/pgphoto-re/evidence/manifest.md` (`a766aaf9` stock, `295806a8` o-v18m, `4684782f` v94,
`a83ac7bb` k1ii-k3iii) — so the decompiled `capture_generic` is explanatory, not authoritative for this exact
binary. The prediction it makes can be tested directly on the logs instead, and it holds:

| GP code | name | on pgphoto's list? | camlib returned it | reached polestar_app |
|---|---|---|---|---|
| `-110` | `GP_ERROR_CAMERA_BUSY` | yes (`-0x6e`) | many | **14** as `captureImage ret -110` |
| `-112` | `GP_ERROR_CANCEL` | yes (`-0x70`) | — | **3** as `captureImage ret -112` |
| `-8` | `GP_ERROR_FIXED_LIMIT_EXCEEDED` | **no** | **2** | **0** |

Across all logs on the rig the camlib returned `gp=-8` exactly **twice**, and `captureImage ret -8` appears
**zero** times — while codes that *are* on the list propagate freely. Those two `gp=-8` returns are precisely
SP_0050 and SP_0051, the two phantom successes. Codes on the list surface as errors; the one code not on the
list became success both times it occurred.

That is a 2-for-2 match with the predicted asymmetry, derived purely from logs. It also means this class of bug
is not limited to StoreFull: **any** GP error outside that eight-entry list is silently converted to a successful
capture, and nobody has enumerated which ones exist in practice.

## Mitigation shipped (commit 3bf5b93a)

pgphoto cannot be patched, but the wrapper we already own sits at the exact call boundary where the code is
dropped. `stage2_guarded_gp_camera_capture()` now remaps `-8` to `GP_ERROR_NO_SPACE` (**-115**), which *is* on
pgphoto's allowlist and is the semantically correct code for a full card. Default-on, with
`STAGE2_CAPTURE_STOREFULL_REMAP=0` as the documented escape hatch, matching the #183 pattern. The trace line
still logs the raw `-8`, so a reader can tell what the core did rather than only what pgphoto was handed.

`stage2_capture_slot_target()` now installs the wrapper for this mode too — that silent-install gap is what made
the #183 guard's deployment unverifiable earlier.

### What is verified, and what is inferred

**Verified on the rig:** a negative return from pgphoto becomes a `val[state:-N;…]` frame in the client-facing
log. Across all logs: `state:-110` ×15, `state:-112` ×3, and `state:-8` **zero times** — the same asymmetry as
the return codes. The client-facing `Mlog_000039.log` likewise carries negative states (`state:-1005`,
`state:-5`), so error states do reach the client.

**Inferred, not observed:** that `-115` specifically produces `val[state:-115;…]`. pgphoto's allowlist includes
-115 (it returns it), and the app's `state:-N` emission looked generic across the two codes actually seen — but
-115 never occurred on this rig, so that final step is an inference from the pattern. It should be confirmed on
the first real full-card event, or by a device test that fills the camera's card.

### Still unexplained

61 `will captureImage` attempts against 56 completion lines — **5 attempts produced no completion line at all**.
That is a separate gap from the phantom-success bug (those 2 are inside the 39 `ret 0`) and I have not
determined whether they are truncated log tails, in-flight captures at rotation time, or a third failure mode.
Not claiming an explanation.

The #183 guard is active but structurally cannot catch this: it validates the *success* path for an empty
path, whereas here the core reported a failure that the caller discarded. A guard for this class has to live
where the return value is consumed — check it before emitting `state:2`/`state:5`, and emit an error frame
instead.

**The conversion point is not visible in this capture**: `STAGE2_CAPTURE_TRACE=0` on the deployed rig, so no
`[stage2-trace] capture-return seq=N ret=-8` line exists to show what the shim handed back. Enabling that
trace and reproducing would pin whether the loss is in pgphoto's error mapping or in polestar_app's handling
of it. I am not claiming which, because I have not observed it.

## Why this matters more than the wedge

A wedge is loud: every later capture returns `-1005` and the operator knows something is wrong. This path is
silent — one capture vanishes, the app says it succeeded, the client says it finished, and the user has no
photo and no error. For astrophotography sequences that means a missing frame in a stack with nothing to
indicate it.

## Relationship to #181 — the stated trigger is too narrow

#181 ("First capture after a session re-establishment can be accepted then silently lost (no shutter, no
files)") matches the symptom. SP_0050 fits its trigger: first capture after a reboot, with
`[camera-usb] supervisor ready; identity=none` preceding it.

**SP_0051 does not.** It occurred seven minutes later in the *same* session — grepping 20:43:40 to 20:50:45 for
`supervisor ready`, `gp_camera_init`, `keep-lv` or usb events returns nothing. So no re-establishment happened
between the two, and the trigger is not "first capture after a session restart" but **any capture whose
InitiateCapture is refused with `PTP_RC_StoreFull` (`0x200c`)**. That makes it more common than #181's title
implies: two occurrences in one boot, minutes apart, from ordinary repeated capture attempts.

What these occurrences add beyond #181 is the mechanism evidence — the camlib *explicitly reports*
`initiate-not-confirmed ptp=0x200c gp=-8`, so the loss happens above the camlib and above our shim — and a
detection signature that already works offline.

## Detection already exists -- and already caught this

My first draft of this file proposed pairing `captureImage ret 0` against `state:4` as a new detector. That was
wrong: **`scripts/capture-outcomes.py` already implements exactly this** and classified the event correctly on
the first run, with no changes:

```text
classified PASS        : 37
classified FAIL        : 1
  rig_all.txt 20:43:41:956 FAIL    logged=-6249ms file=SP_0050.jpg states=[2, 5]
naive sign-based count : 38 -> over-reports by 2.71x
```

It reports SP_0050 as **FAIL** despite `ret 0`, precisely because `states=[2, 5]` contains no `4`. Its
docstring already warns against trusting the sign at all (issue #218: `capture end -23398 ms` is a *success*),
and notes that a naive sign-based analysis once produced "34 capture timeouts" and several failure modes that
did not exist. The counter pair in this file is therefore a cross-check on the tool, not a replacement for it
-- and the tool agrees with it.

### Why a global counter is the wrong method

I earlier wrote "38 `ret 0` vs 37 `state:4`, exactly one mismatch" and then "39 vs 37, two". **That arithmetic
is unsound and I am withdrawing it.** `state:4` is not emitted once per capture. In the overnight corpus
(`docs/evidence/k1ii-overnight-20261126/sanitized`) 33 captures produced:

```text
empty-payload state:4 lines   : 33     (val[state:4;])
named state:4 lines           : 66     (e.g. K1II8794.JPG appears twice)
distinct filenames            : 33
ret 0 lines                   : 33
```

So roughly three `state:4` lines per capture, of which some carry no filename at all. Comparing that total
against a count of `ret 0` lines compares unlike things; the overnight corpus reads 99 vs 33 and would look
like a huge mismatch when there is none.

The valid method is **per-capture classification** — pair each outcome with the frames of *that* capture and
ask whether a named `state:4` occurred for it. `capture-outcomes.py` already does exactly that, which is why
its output above (`PASS 37 / FAIL 2`, naming SP_0050 and SP_0051) is the number to use. My counter pair agreed
with it by luck on the rig corpus, where the ratio happened to be near one; it would have produced a false
alarm on the overnight corpus.

The real gap is narrower than I first wrote: this classification exists as an **offline script** and nothing
runs it at runtime. The supervisor still reports `supervisor ready` throughout (#182), so a phantom success is
only discoverable after the fact by someone who thinks to run the analyzer over the logs.
