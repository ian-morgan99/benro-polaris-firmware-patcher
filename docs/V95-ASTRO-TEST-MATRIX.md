# v95 Astro candidate — test matrix and release notes

Status: **NOT BUILDABLE YET.** The libgphoto2 pin is still `43dccb81b` (driver
`origin/main`). The corrected driver is `ian-morgan99/libgphoto2` PR #144, which is
**OPEN** with all three review threads unresolved. Do not build v95 until the pin
below is a real merged SHA.

Candidate identity to be assigned when the pin lands: `astro-v95-<slug>-YYYYMMDD`,
display `6.0.0.54.95`.

## 1. What v95 carries over v94

v94 pins driver `origin/main` @ `43dccb81b92b6b25f44957a4684f534393562028`. That
commit **does not contain** `pentax_model_answers_undeclared_generic_props`, the #233
capability row. PR #144 targets `feature/polaris-capture-events` @ `43df01ea9`,
deliberately not `main`.

Consequence for reading v94 results: **v94 showing no EV / white-balance widget is
expected, not a regression.** Do not carry #233's earlier PASS forward onto v94's
matrix, and do not treat v94 row 7 ("EV does nothing") as a new defect.

## 2. Verification-mechanism change in PR #144 — verified against the diff

PR #144 was reviewed by reading `git diff 43df01ea9...origin/fix/k1ii-shutter-gate-235`
in `/home/ian/Documents/VSCodeProjects/LibGphoto2/libgphoto2`, not from the PR body or
the driver agent's `MANIFEST.txt`. The manifest does not mention this change at all.

| Property | Verification at base `43df01ea9` | Verification in PR #144 | Mechanism changed? |
|---|---|---|---|
| Shutter (`0xd00f`) | conditions offsets 272/276 (`bulb_timer_seconds`) | `_pentax_verify_property_value` on `PTP_DPC_PENTAX_ShutterSpeed`, `PTP_DTC_UINT64`, uncached | **YES — new property read** |
| Drive mode (`0xd013`) | `_pentax_verify_rational_in_conditions` (conditions field) | `_pentax_verify_property_value` on `PTP_DPC_PENTAX_DriveMode`, `PTP_DTC_UINT32`, with conditions fallback | **YES — moved onto the uncached read** |
| White balance (`0x5005`) | `_pentax_verify_u16_property`, which already called `ptp_getdevicepropvalue` | same wrapper, now delegating to `_pentax_verify_property_value` | **NO — same mechanism, refactored** |
| Aperture, EV | `_pentax_verify_rational_in_conditions` | unchanged | NO |

Two corrections to the handover's framing of this:

1. **White balance did not move onto the uncached read in PR #144 — it was already
   there.** At base, `_pentax_verify_u16_property` already loops on
   `ptp_getdevicepropvalue(params, property, &actual, PTP_DTC_UINT16)`. PR #144
   extracted a shared `_pentax_verify_property_value` and made the u16 wrapper call it.
   The PR head comment states this explicitly: *"White balance already verified this way
   and is confirmed to answer GetDevicePropValue for 0x5005, so its return codes are
   unchanged."* So #233's WB verification mechanism is **not** new in v95.
2. **Drive mode is the property that actually changed mechanism**, and PR #144 states
   only its **read** path was proven on a body (`GetDevicePropValue` on `0xd013`
   returned `00000000`). A drive-mode **write** was never exercised. That change rests
   on read-only evidence plus unit/contract tests.

EV stays on the conditions verifier and is unchanged by PR #144.

## 3. Test matrix

Legend: `PASS` needs an instrumented transcript attached to this repo. Operator
observation alone is not a PASS.

### 3a. Carried forward from v94 (must not regress)

| # | Area | Body | Result on v94 | v95 requirement |
|---|---|---|---|---|
| 1 | B capture wheel, untimed | K-3 III | PASS ("works perfectly") | re-confirm |
| 2 | B capture wheel, Manual | K-3 III | FAIL — does nothing | #242 parity |
| 3 | Live View stability | K-3 III | FAIL — pgphoto SIGSEGV, camera off USB | #176 / #147 |
| 4 | Live View start latency + garbled frame | K-1 II | FAIL — ~30 s, garbled on iPad | #253 / #147 |
| 5 | Parameter set latency, values revert | K-1 II | FAIL — minutes, then reverts | #253 |
| 6 | Shutter release delay | K-1 II | PARTIAL — fires 5–20 s late | #253 / #174 |

### 3b. New in v95 — the driver fix being qualified

| # | Area | Body | Why it is here | Owner |
|---|---|---|---|---|
| 7 | Shutter write refused in Bulb | K-1 II | PR #144 gate: non-bulb value without `CAN_CHANGE_TV` must return `-6` before the wire | libgphoto2 #143 |
| 8 | No-op shutter must not false-pass | K-1 II | `SET 00:30` in B returned `GP_OK` at base; must now be `-1` | libgphoto2 #143 |
| 9 | Shutter write in Manual | K-1 II | `SET 1/50` → `GP_OK`, conditions and widget converge | libgphoto2 #143 |
| **10** | **Drive mode WRITE + read-back** | **K-1 II** | **PR #144 moved drive mode onto the uncached `GetDevicePropValue` verifier. Only its READ path was proven on a body; a drive-mode write was never exercised.** | **#27 consistency** |
| **11** | **White balance WRITE + read-back on the pinned SHA** | **K-1 II** | **#233's WB PASS was recorded against driver `43df01ea9`, not against the v95 pinned SHA. The shared verifier `_pentax_verify_property_value` is new code that WB now runs through, and its return codes must be re-confirmed on hardware.** | **#233** |
| **12** | **EV write + read-back on the pinned SHA** | **K-1 II** | **EV stays on `_pentax_verify_rational_in_conditions`, but #233's EV PASS was recorded on `43df01ea9`. v94 never exposed an EV widget at all, so EV has never been exercised on a v9x Astro build. Re-verify; do not carry the earlier PASS.** | **#233** |
| 13 | `exposure_mode` code table display | K-1 II | Conditions output now prints `exposure-mode=Bulb`; confirm the additive parse did not break `pentax-bulb-qualification-probe.c` | libgphoto2 #143 |

### 3c. Astro half (never executed on v94)

| # | Area | Result on v94 | v95 requirement |
|---|---|---|---|
| 14 | Astro boot hook present after flash | FAIL — `/app/astro` empty, nothing on `:8090`; flashing replaced `/app` and deleted `/app/network_telnetd.sh` | must survive a flash; see #265 |
| 15 | Astro SD deployment | FAIL — no automatic path | #265 design |
| 16 | Plate solve on a real frame | not attempted | requires 14–15 |

## 4. Blocking prerequisite — the libgphoto2 pin (six locations)

PR #144 must be **merged** into `feature/polaris-capture-events` first. Never pin an
unmerged branch head: if the PR is amended during review, provenance points at a commit
that exists on no branch.

Take the **merge/squash SHA on `feature/polaris-capture-events`**, not the PR head
`75b03f0a3`. Do **not** `git am` the patch series at
`/home/ian/Documents/VSCodeProjects/shutter-gate-patches/full-pr144/` — that produces
`68fd8bcbbd445654ebcb2ca446f44cba9701b9b1`, an orphan on zero branches, and the tree is
identical but the commit is unfetchable.

All six move together:

| Location | Field |
|---|---|
| `scripts/build-astro-candidate.sh:10` | `LIB_BASELINE="<sha>"` |
| `docs/RELEASE-VERSION-STATE.md` | new `version_commit_binding=6.0.0.54.95\|libgphoto2=<sha>\|patcher=<sha>` line |
| `docs/FWPKT-PROVENANCE-CONTRACT.md` | **append a new v95 row; never edit the v94 row** |
| `docs/release-change-summary-v95-astro.json` | `baseline.libgphoto2_commit` |
| `docs/ASTRO-CAMERA-INTEGRATION-HANDOFF.md` | "pinned at `<sha>`" |
| `docs/ASTRO-CANDIDATE-RELEASE.md` | `--libgphoto2-commit <sha>` |

**Wording that becomes false once pinned:** the fix lands on
`feature/polaris-capture-events`, **not** driver `main`. Any place describing the input
as "promoted libgphoto2 main" must name the feature branch explicitly. Affected today:
`docs/release-change-summary-v94-astro.json` (`"Use promoted libgphoto2 main ..."` —
leave it, it is true of v94), `docs/ASTRO-CAMERA-INTEGRATION-HANDOFF.md` ("clean main
checkout"), and `docs/ASTRO-CANDIDATE-RELEASE.md` ("the clean pinned libgphoto2 main
checkout").

**Blocker resolved on this branch.** `scripts/build-astro-candidate.sh` previously read

```sh
[ "$(git -C "$LIBSRC" branch --show-current)" = "main" ] || die "libgphoto2 must be on main"
```

Because the fix lands on `feature/polaris-capture-events`, that gate rejected a valid v95
input even after PR #144 merged. It has been replaced with a reachability check: the pinned
`LIB_BASELINE` must be an ancestor of `origin/main` or `origin/feature/polaris-capture-events`.
Behaviour verified against real SHAs:

| Input | Result |
|---|---|
| `43dccb81b` (v94 pin, driver main) | accepted — no regression on the v94 path |
| `43df01ea9` (#233 base, feature branch) | accepted |
| detached checkout at a reachable SHA | accepted |
| `75b03f0a3` (PR #144 head, unmerged) | **rejected** |
| `68fd8bcbb` (`git am` orphan) | **rejected** |

This is strictly stronger than the branch check it replaced: it rejects exactly the two
unfetchable cases this document warns about, while accepting every legitimate pin.

Note `scripts/build-release-candidate.sh:104` still requires driver `main`. That is the
**standard** (non-Astro) release line, which pins main and does not need the feature branch,
so it is unchanged. Only the Astro candidate path was relaxed.

## 5. Release-summary note to carry into v95

> PR #144 unified Pentax vendor-property verification onto the uncached
> `GetDevicePropValue` read (issue #27's consistency criterion). Drive mode moved from
> its conditions field onto that read; shutter moved from conditions offsets 272/276
> onto it. White balance already used an uncached property read and keeps its existing
> wrapper and return codes. Drive-mode **write** verification is proven only by unit and
> source-contract tests — no body write was exercised. EV and white balance must be
> re-verified on a K-1 II against the pinned SHA before v95 is called qualified; #233's
> earlier PASS was recorded against `43df01ea9`, not this build.

## 6. Do not

- Do not build v95 while `LIB_BASELINE` is `43dccb81b` and claim it carries the fix.
- Do not edit the v94 provenance row or `release-change-summary-v94-astro.json`.
- Do not mark rows 10–12 PASS from operator observation; each needs a transcript.
