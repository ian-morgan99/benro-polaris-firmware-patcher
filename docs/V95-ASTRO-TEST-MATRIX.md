# v95 Astro candidate — test matrix and release notes

Status: **PINNED, NOT YET BUILT.** libgphoto2 PR #144 is merged into
`feature/polaris-capture-events` as squash commit
`855f718e515d288adbc7e0ffe8b22b729570e7d8`, verified by content (both
`pentax_model_answers_undeclared_generic_props` for #233 and
`pentax_shutter_write_permitted` for #235 present, reachable from the branch). The pin
is set in all four build-input sites. **v95 has not been built** — no container runtime
in this sandbox; the operator runs `build-astro-candidate.sh` on a docker host. It is
not flashed, installed, or qualified.

Candidate identity: `astro-v95-k1ii-shutter-gate-20261104`, display `6.0.0.54.95`. The
`.95` `version_commit_binding` line and the `FWPKT-PROVENANCE-CONTRACT` v95 row are added
in a separate post-build "release: record" commit (mirroring v94's `3d924c6`), because both
reference a patcher commit that only exists once this branch is merged and built. The binding
line is written by `verify_display_fwver_monotonic.py --record`, not hand-edited.

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

#### 3b-results. On-device run against the pinned SHA (2026-11-04)

Run on a bench K-1 II (`usb:001,013`, fw 1.02, serial 7371227) driven by an x86
build of PR #144 head `75b03f0a3`, whose `camlibs/ptp2/config.c` and
`camlibs/ptp2/library.c` are **byte-identical** to the pinned release SHA
`855f718e5`. This verifies the *driver binary*, not the v95 firmware packet.
Evidence: `PrivateResearch` commit `0f9284221`
(`polaris-evidence/k1ii-controls-20261104/v95-ondevice-*`).

| Row | Result | Evidence |
|---|---|---|
| 11 WB write | **PASS** | `whitebalance=Daylight` → `0`, read back `direct=Daylight` at t=3s via the uncached verifier. Restored. |
| 12 EV write | **PASS** | `exposurecompensation=+0.3` → `0`, conditions `exposure-comp=3/10` at t=3s. Restored. Closes the "do not carry the earlier PASS" instruction — now re-verified on the pinned SHA. |
| 9 shutter in Manual | **PARTIAL** | `pentaxdirectshutter=1/50` → `GP_OK` (gate correctly *permits* a non-bulb value with `CAN_CHANGE_TV`), but read-back stays `5/10` — the body does not apply it. Distinct from the #235 false-pass (that was a refusal reported as success). Logged, not assumed away; needs a separate look at DirectShutter accept-but-ignore in Manual. |
| 7 shutter refused in Bulb | **NOT RUN** | Needs the physical dial on **B**; camera is in Manual and the dial is not changeable over PTP. Gate refusal path (`CAN_CHANGE_TV` absent) still unverified on hardware. |
| 8 no-op shutter false-pass | **NOT RUN** | Same dial dependency as row 7. |
| 10 drive-mode write | **NOT RUN** | No drive-mode harness exists in the evidence directory; only aperture/EV/WB/shutter tests are present. Still unit + source-contract only. |

Also verified while there: **aperture** `pentaxdirectaperture=f/4` → `0`,
`write_took_effect=YES`. Harness bug found: `wb_write_test.c` defaults its target
to `"1/50"` (a shutter string written into the `whitebalance` widget), so a
no-argument run returns `-2 Bad parameters` and looks like a WB failure; with a
valid value WB passes. Harness gotchas: the model string must be
`"Pentax K-1 Mark II (PTP mode)"` (the generic `"USB PTP Class Camera"` from
`--auto-detect` is not registered by this build), and rapid successive PTP inits
race the prior teardown → `init fail`; space runs by ~3s.

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
>
> **Update 2026-11-04:** EV (row 12) and white balance (row 11) are now re-verified on a
> bench K-1 II against the pinned SHA — see §3b-results and `PrivateResearch` commit
> `0f9284221`. Drive-mode write (row 10) still has no harness and remains unit +
> source-contract only. The Bulb rows (7, 8) still need the physical dial on B.

## 6. Do not

- Do not build v95 while `LIB_BASELINE` is `43dccb81b` and claim it carries the fix.
- Do not edit the v94 provenance row or `release-change-summary-v94-astro.json`.
- Do not mark rows 10–12 PASS from operator observation; each needs a transcript.
  Rows 11 and 12 now have one (`0f9284221`); row 10 does not.
