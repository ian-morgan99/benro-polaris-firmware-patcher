# Patcher compatibility gates — audit after libgphoto2 consolidation

This document catalogues every environment-variable / parameter "gate" the
patcher exposes to control the rebuilt libgphoto2, and verifies that each
gate is **fail-closed** (i.e. when a gate would block behaviour that
`stage2_policy.c` allows, the gate is opt-in only; never opt-out).

This audit was produced as part of the upstream-consolidation follow-up
(plan section 16, "preserve-gates") to confirm that no gate is a foot-gun
that silently disables a guard we just put in.

## 1. The gates

| Gate | Default | Used by | Effect when enabled |
|---|---|---|---|
| `ALLOW_DIRTY_SOURCE` | `0` | `build_ptp2.sh` | Permits build with uncommitted local-source changes (otherwise `exit 1`). |
| `FIX_R5M2_TYPO` | `1` | `build_ptp2.sh`, `build_fullstack.sh` | Patches upstream `library.c` so `"Canon:EOS 5Rm2"` becomes `"Canon:EOS R5m2"`. |
| `COLD_START_TIMEOUT_MS` | *(unset)* | `build_ptp2.sh` | Overrides `#define USB_CANON_START_TIMEOUT 1500` in ptp2. |
| `REMOVE_KEEP_DEVICE_ON` | `0` (ptp2-only: `1`) | `build_ptp2.sh` | Neutralises every `camera_keep_device_on(camera)` call. |
| `REMOVE_EXIT_REMOTEMODE` | `0` (ptp2-only: `1`) | `build_ptp2.sh` | Strips the `SetRemoteMode` toggle added in 2.5.34's `camera_exit`. |
| `SELFTEST` | `0` | `patch.sh` | After flash, qemu-emulates `dlopen` of the stage-2 bundle (needs `qemu-arm-static` on host). |
| `SWAP_USB1` | `1` (full mode: `1` unconditionally) | `patch.sh` | Stage libusb-1.0.so.0 so the fresh `usb1.so` (built against system glibc) can find it. |

`TRAMP_ADDR` and `LIBGPHOTO2_VERSION` are positional/required, not "gates".

## 2. Audit — each gate is fail-closed

### 2.1 `ALLOW_DIRTY_SOURCE` (default 0)

When the user mounts a local libgphoto2 checkout, the build hashes the
dirty diff and refuses to build unless this gate is explicitly set to `1`.
This is **fail-closed**: an unflagged build with uncommitted changes
fails fast with a clear error.

```text
[build] ERROR: local source is dirty (hash <sha>); explicit opt-in required
```

*Verified* against `build_ptp2.sh` lines 53-58: gate is read, and the only
way past it is an explicit `ALLOW_DIRTY_SOURCE=1` in the environment.

### 2.2 `FIX_R5M2_TYPO` (default 1)

Corrects the upstream `camlibs/ptp2/library.c` typo so that ptp2's model
table returns `"Canon:EOS R5m2"` for the R5 Mark II. This is **load-bearing**
because `stage2_policy.c` only accepts two exact model strings — the
*fixed* `"Canon:EOS R5m2"` **and** the upstream-typo `"Canon:EOS 5Rm2"`
(belt-and-braces, so an un-fixed build still works for the R5 Mark II).

*Fail-closed check*: if `FIX_R5M2_TYPO=0` were set, the upstream typo
would remain. `stage2_policy.c` lines 12-13 still accepts the typo
string, so behaviour is preserved. Setting the gate to `0` therefore does
not introduce a Canon-detection regression — the second comparison
branch keeps the R5 Mark II accessible.

### 2.3 `COLD_START_TIMEOUT_MS` (default unset)

When set, increases the ptp2 driver's first-OpenSession timeout. The
default is *unset* (stock 1500 ms). The patcher explicitly documents in
`patch.sh` line 147 that this gate is **intentionally left at 1.5 s** —
a longer value exceeds the Polaris app's ~5 s watchdog and crash-loops.

*Fail-closed check*: leaving the gate unset is the safe default. Setting
it to e.g. `8000` would cause a runtime crash loop on the device. The
gate is **opt-in only** (no default value overrides the stock 1500 ms),
so an unspec'd run is always safe. The doc comment in `patch.sh`
prevents the next maintainer from re-introducing a higher default.

### 2.4 `REMOVE_KEEP_DEVICE_ON` (default 0; ptp2-only mode forces 1)

Strips `camera_keep_device_on(camera)` calls. This gate is **only enabled
in `MODE=ptp2only`**. The full-stack path keeps the upstream call,
relying on the `pgphoto` reliability base (`resetUsb` + list-files) to
dampen the cold-start storm the heartbeat would otherwise cause.

*Fail-closed check*: the gate defaults to `0`. Only the explicit
`MODE=ptp2only` build path sets it to `1`. A full-stack build never
touches this gate, so a fresh-core user cannot accidentally disable the
heartbeat and trip the viewfinder-settle interaction.

### 2.5 `REMOVE_EXIT_REMOTEMODE` (default 0; ptp2-only mode forces 1)

Strips the `SetRemoteMode` toggle added in 2.5.34's `camera_exit` to
avoid an extra re-enumeration. Same fail-closed story as 2.4: only
`MODE=ptp2only` enables it.

### 2.6 `SELFTEST` (default 0)

When set, after a successful flash the patcher qemu-emulates the
stage-2 bundle's `dlopen` to confirm all symbols resolve. Pure
post-build verification — no runtime behaviour change. Default off,
opt-in only. *Fail-closed* trivially.

### 2.7 `SWAP_USB1` (default 1)

Stages `libusb-1.0.so.0` from a glibc-compat baseline so the freshly
rebuilt `usb1.so` can `dlsym` it. Lines 94-100 of `patch.sh`
auto-disable it if the on-device library is missing. In `MODE=full`
the gate is forced to `1` (line 43) because the fresh port **must** be
able to find libusb.

*Fail-closed check*: if the on-device libusb is missing, the gate
auto-disables and the full-stack build falls back gracefully (the fresh
port will not load — this is a known limitation, not a silent regression,
and `build_ptp2.sh` will emit a `SWAP_USB1=0` notice).

## 3. Pentax markers — orthogonal to these gates

The Pentax / non-Pentax split is enforced **inside the rebuilt ptp2** by
the model-name string `*Pentax*` match in `container/patch.sh` and
**inside `stage2_policy.c`** by an explicit allow-list. Neither of
those is a "gate" in the env-var sense — they are *invariants*. See
`docs/pentax-patcher-gate-bug.md` for the recent SIGPIPE-pipefail bug
that briefly made the Pentax marker look unguarded, and `stage2_policy.c`
for the final model-gated check.

## 4. Summary

| Gate | Default | Fail-closed? | Notes |
|---|---|---|---|
| `ALLOW_DIRTY_SOURCE` | 0 | ✅ | Explicit opt-in for dirty local source. |
| `FIX_R5M2_TYPO` | 1 | ✅ | Default-ON; `stage2_policy.c` accepts both spellings. |
| `COLD_START_TIMEOUT_MS` | unset | ✅ | Opt-in only; longer value is dangerous and documented as such. |
| `REMOVE_KEEP_DEVICE_ON` | 0 | ✅ | Only flipped by `MODE=ptp2only`. |
| `REMOVE_EXIT_REMOTEMODE` | 0 | ✅ | Only flipped by `MODE=ptp2only`. |
| `SELFTEST` | 0 | ✅ | Trivially opt-in post-build verification. |
| `SWAP_USB1` | 1 | ✅ | Auto-disables when on-device libusb is missing. |

All seven gates are fail-closed. The consolidation work did not
introduce or remove any of them. The two model-ability gates in
`stage2_policy.c` (`R5m2` and `5Rm2`) remain the authoritative
controls over what the bundle will run.
