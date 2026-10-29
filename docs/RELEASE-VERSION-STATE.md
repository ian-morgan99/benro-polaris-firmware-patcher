# Polaris display firmware-version release state

Benro Connect must receive the exact five-component version from code 780.
The release builder treats the value below as the last accepted display version
and refuses to build a candidate that is unchanged, lower, from another
version family, or missing the fifth build component.

```text
last_display_fwver=6.0.0.54.90
```

## Consumed-version registry (authoritative)

Every display version ever issued is listed below. `verify_display_fwver_monotonic.py`
reads these lines and refuses to hand out any of them again, **regardless of what
`last_display_fwver` says**. The list is append-only: never delete or edit an
entry, only add one when a candidate is claimed.

```text
consumed_display_fwver=6.0.0.54.67
consumed_display_fwver=6.0.0.54.90
consumed_display_fwver=6.0.0.54.89
consumed_display_fwver=6.0.0.54.88
consumed_display_fwver=6.0.0.54.87
consumed_display_fwver=6.0.0.54.86
consumed_display_fwver=6.0.0.54.85
consumed_display_fwver=6.0.0.54.78
consumed_display_fwver=6.0.0.54.77
consumed_display_fwver=6.0.0.54.76
consumed_display_fwver=6.0.0.54.75
consumed_display_fwver=6.0.0.54.74
consumed_display_fwver=6.0.0.54.73
consumed_display_fwver=6.0.0.54.72
consumed_display_fwver=6.0.0.54.71
consumed_display_fwver=6.0.0.54.70
consumed_display_fwver=6.0.0.54.69
consumed_display_fwver=6.0.0.54.68
consumed_display_fwver=6.0.0.54.66
consumed_display_fwver=6.0.0.54.53
consumed_display_fwver=6.0.0.54.65
consumed_display_fwver=6.0.0.54.64
consumed_display_fwver=6.0.0.54.63
consumed_display_fwver=6.0.0.54.62
consumed_display_fwver=6.0.0.54.61
consumed_display_fwver=6.0.0.54.60
consumed_display_fwver=6.0.0.54.59
consumed_display_fwver=6.0.0.54.58
consumed_display_fwver=6.0.0.54.57
consumed_display_fwver=6.0.0.54.56
consumed_display_fwver=6.0.0.54.54
consumed_display_fwver=6.0.0.54.55
version_commit_binding=6.0.0.54.68|libgphoto2=8e06d39aea9ff22be9a59a5962263bdf41fc76e7|patcher=36d72ae9ffaa0d234c80fbf935102dd58809a67c
version_commit_binding=6.0.0.54.69|libgphoto2=731d7fbd5b5c590490f2783dd549762fc5dc3b9d|patcher=437e0d3fac284ef8b1502d58bd4336e0bbff5ec8
version_commit_binding=6.0.0.54.70|libgphoto2=731d7fbd5b5c590490f2783dd549762fc5dc3b9d|patcher=f2c2e18a7631cead8686b56d2944a7f633e85221
version_commit_binding=6.0.0.54.71|libgphoto2=f95bc575309b7efe1724405aaea970bf0c9704cb|patcher=7d534319db315731cf4f6e1fac2b2feea2a44ebc
version_commit_binding=6.0.0.54.72|libgphoto2=749d38f6d7989579e43cdc5675a27a27956eb34d|patcher=cd892ba28e9de61e720cc4a25edc7f58f313fedd
version_commit_binding=6.0.0.54.73|libgphoto2=27540e12227c7fc94f054f2f86fca7dc7a543ff6|patcher=d5ba81ecffae619a83cd47984e5e64b6db76f856
version_commit_binding=6.0.0.54.74|libgphoto2=8db3785f7afbc5b38ff622690dc5198f785c35ec|patcher=ffb2e504df300767c21a823c86937ed28cd660d8
version_commit_binding=6.0.0.54.75|libgphoto2=e7d0cf1ddf40ce956c4aa62f8e505143555620a6|patcher=798bd11f5c2ff24bc05ffcc819032856685d5d8e
version_commit_binding=6.0.0.54.76|libgphoto2=df9d7274565a5c0ebf310b9e7bfec75c28a8dabc|patcher=27f01f5658f8a6b8c2499bbb19a202b84074aa09
version_commit_binding=6.0.0.54.77|libgphoto2=c7eeaeda90ecdff87a5bbd03a2cfc0e03ffcbcae|patcher=2799e90989e007b38b523fe8630af9e7c3d4afbe
version_commit_binding=6.0.0.54.78|libgphoto2=d4f2df913ae9b6eec6830f79465179554a75d366|patcher=09e72c81a4bd0b6b1af82020f96326992daff323
version_commit_binding=6.0.0.54.85|libgphoto2=3fe1c80e08e9ea66019700e07e1522b2ca9f7a06|patcher=006ab000fb9e884b3559a2455877bf633834dc31
version_commit_binding=6.0.0.54.86|libgphoto2=83240b36a8f128f67eb7e0f68dc10045547b0b47|patcher=02c71dabd7b4ee22dafb458c1955da83ea62ac15
version_commit_binding=6.0.0.54.87|libgphoto2=d03a948180592337337782858c6a72064b0938ab|patcher=7f0a3887cdbac23633dde2e3bf4408e062749ed8
version_commit_binding=6.0.0.54.88|libgphoto2=bd35b36e5062a2676116616006f47618fb025ddc|patcher=84999979f536ca90f6c7e77c5ef79f7bc70c8040
version_commit_binding=6.0.0.54.89|libgphoto2=63a894b0821a510fc40244c5cc4ef84a5220a91c|patcher=613b9d140299add55caee24c0a3ece4e46fa0a42
version_commit_binding=6.0.0.54.90|libgphoto2=63a894b0821a510fc40244c5cc4ef84a5220a91c|patcher=f344e41261a886f8f6107b9467095bc90b3835a1
```

## Version-to-commit binding (one version, one set of commits)

A display version is a claim about a specific build, so uniqueness has to hold in
both directions:

| direction | what it prevents |
|---|---|
| version → commit set | two different builds reporting the same firmware version in Benro Connect |
| commit set → version | an unchanged source tree being rebuilt and re-issued as though it were new |

The consumed registry above gives the first. It cannot express the second, and the
second is what breaks quietly: rebuilding an unchanged tree "to try again" mints a
fresh number for identical commits, and the app then shows two firmwares that
cannot possibly behave differently.

So every version claimed from now on is recorded with the exact commits it was
built from:

Each entry is one line: the key, the version, then the two commits, separated by
`|`.

```text
…=<version>|libgphoto2=<sha>|patcher=<sha>
```

`build-release-candidate.sh` supplies both commits and refuses to claim a version
from a dirty patcher tree, so a binding describes the build instead of
approximately describing it. `verify_display_fwver_monotonic.py` enforces both
directions and fails closed on a malformed entry.

The latest bound candidate is `.90`; its exact source commits are recorded and
its published artifact identity is independently recorded below. `.68` through `.90`
have recorded commit bindings where the release evidence established them.
Earlier versions are deliberately left unbound when their commit sets are not
reliably recorded: an unbound historical version still blocks its number
forever, but is never used to infer what commits it contained. Re-issuing an
old build is therefore refused on its version, not accepted on a guessed commit
set.

| Version | Candidate | Notes |
| --- | --- | --- |
| `.90` | o-v18m-k1ii-pgphoto-readiness-20261029 | **published to PrivateResearch 2026-10-29; install pending.** Exact source commits: libgphoto2 `63a894b0821a510fc40244c5cc4ef84a5220a91c`, patcher `f344e41261a886f8f6107b9467095bc90b3835a1`. Display version `6.0.0.54.90`; build id `6.0.0.54.90-o-v18m-k1ii-pgphoto-readiness-20261029`. ZIP MD5 `4c005b0acf50676fa7e1d32ffbac9cd6`, SHA-256 `829fd30e79a52b2155bd865e1fb584fc82f7785bfad31d4878de7fe31a01ab34`; appfs MD5 `d1e290f5509cee93f7e2d1b9b5666c36`. Pre-release gate GREEN: 16 passed / 0 failed / 1 prerequisite skip (stock firmwareInfo cross-check unavailable in the public checkout). Carries patcher issue #253: bounded pgphoto 8080 readiness window increased from the measured false-failure limit to 90 seconds; no libgphoto2 source change. Hardware qualification and installation evidence remain pending. Artifact: [PrivateResearch firmware packet](https://github.com/ian-morgan99/PrivateResearch/tree/main/firmware-packets/6.0.0.54.90--o-v18m-k1ii-pgphoto-readiness-20261029). |
| `.87` | o-v18j-k1ii-mainline-20261028-r2 | **published to PrivateResearch and installed/runtime-verified on Polaris 2026-10-28; device reports `FwVer:6.0.0.54.87;date:2026.10.28;`, exact on-device provenance matches libgphoto2 `d03a948180592337337782858c6a72064b0938ab` and patcher `7f0a3887cdbac23633dde2e3bf4408e062749ed8`.** Pre-release gate GREEN (16 passed / 0 failed / 1 prerequisite skip); ZIP MD5 `2ec045f6fc9ba860c7ebb2a2c293fbc6`, SHA-256 `8fb41c4cddae0483dac8ca960937e38ecb495d9b8bf8e225c1296c580138a4a9`. K-1 II Polaris canary PASS: 3/3 liveness, populated ISO/shutter/aperture lists, preview close, and one ordinary capture completing with lifecycle `[1,4,0]` and `SP_0479.jpg`. This is partial physical evidence, not full camera qualification: Bulb, persistent live view, focus, setting round-trips, and the complete widget tree remain pending. The first `.87` manifest attempt was rejected before publication; only the `-r2` artifact was tested and published. See `docs/evidence/o-v18j-k1ii-mainline-20261028-r2/SUMMARY.md`. |
| `.69` | o-v17d-darkframe-budget-20261023 | **built 2026-10-23; pre-release gate re-run GREEN against this artifact on 2026-10-24 (12 passed / 0 failed / 0 skipped); INSTALLED + VERIFIED byte-for-byte 2026-10-24 — device reports `FwVer:6.0.0.54.69;date:2026.10.23;`, provenance `build_id 6.0.0.54.69-o-v17d-darkframe-budget-20261023`, all 10 manifest files SHA-256 match the install manifest, `verify_installed_build.py` PASS. Current running build and current rollback target.** Row added 2026-10-24: `.69` was claimed in the consumed registry and commit binding but never given a table row, so its change set was undocumented here. Single behavioural purpose: libgphoto2 `23008c229` (`camlibs/ptp2/pentax-utils.c`) budgets the long-exposure noise-reduction dark frame in the capture wait — a 70 s bulb had given up at 107.4 s against a 101 s budget and a 40 s bulb at 71.6 s against 71 s, discarding a real photograph by arithmetic rather than a camera fault. Allowance is `exposure + (exposure + 30 s)`, scaled only from a *known* exposure so a proxy is never doubled. **Scope limit found later:** the scaling keys on `bulb_timer_seconds`, which the camera reports only in B mode, so a *timed* long exposure still falls through to the un-margined 60 s base — tracked as **#230** (P0, reproduced live on this build 2026-10-24). Manifest differential `.68`→`.69`: **4 of 10 files moved** — `ptp2.so` (the dark-frame fix), `libpolaris_stage2.so`, `FwVer`, and the provenance file. The loader change is patcher `76e0920` (#213: log each preview-backoff cooldown window once instead of once per poll — measured 617 of 621 Clog lines on one session); it adds log bookkeeping only and changes no control flow or return value, so `.69`'s original "only behavioural change is the dark-frame budget" claim stands. `container/build_ptp2.sh` also changed (`b1b7207`, #214 fail-closed sed anchor) — build path, not shipped bytes. `pentax.so`, `libgphoto2.so.6`, `libgphoto2_port.so.12`, `usb1.so`, `polestar_app` and the pgphoto wrapper are unchanged from `.68`. Artifact `out/o-v17d-darkframe-budget-20261023/FwPkt.zip` — sha256 `9dc904553923e3930082cb9055ff1df6f0b5759169ad2b5e75bd071d839eb7dc`, md5 `52a617302021a5dc167360f083bed122`, size 68392605; `install-manifest.json` present (10 mandatory files, `stage2_mandatory=true`, zip digest matches). **Open defect on this build:** #205 confirmed live 2026-10-24 — an app-side `state:1;bulb:40;c:-1;` on a timed dial is routed to `captureBulbImage` and refused with `state:-6` in ~2 s (21 occurrences in the archived logs, 7 of them at 40 000 ms). |
| `.68` | o-v17c-colortemp-formless | **built 2026-10-19, pre-release gate GREEN (10 passed / 0 failed / 0 skipped); published to PrivateResearch (`93d4d04df`); INSTALLED + VERIFIED + PHYSICALLY QUALIFIED PASS 2026-10-19 — device reports `FwVer:6.0.0.54.68;date:2026.10.19;`, provenance `build_id 6.0.0.54.68-o-v17c-colortemp-formless`, all 10 manifest files SHA-256 match (verdict verified), uptime reset 9373→79 confirms a real reboot. Current running build and current rollback target.** Single-purpose candidate: carries libgphoto2 `8e06d39ae` (PR #105, closes #104), which fixes the `0xd018` blocker found while qualifying `.67`. `_pentax_prop_get` no longer rejects every `FormFlag == PTP_DPFF_None` descriptor; a form-less descriptor is admitted only when it is `GetSet` **and** of a scalar datatype, so `Enumeration` with `NumberOfValues == 0` still fails closed and `0xd024`–`0xd026` stay withheld. No range is invented — the descriptor supplies none, so the control renders as the same plain integer widget the generic property path already produces (matches the capability matrix's descriptor-driven intent; IT2 has no color-temperature UI, so there is no source value list to take a range from). Everything else is identical to `.67` (same patcher tree, same stock base, same CI controls). Artifact `out/o-v17c-colortemp-formless/FwPkt.zip` — sha256 `14e5761ce06a5ddc5933bfa237771737ed52bd1ca21b13365eac50db8e2e604d`, md5 `12c7a5fc83295f28ea9a85d829a38b99`, size 68392387; `install-manifest.json` present (10 mandatory files, `stage2_mandatory=true`, zip digest matches). Gate detail: container harness 21, python regression 243, code-780 version patch, FwPkt structural validation, firmwareInfo manifest, install-manifest currency, polestar_app Bulb branch intact, pgphoto timed-Bulb dispatch present. **ACCEPTANCE GATE PASSED 2026-10-19** (`docs/evidence/o-v17c-physical-20261019/SUMMARY.md`): with WB in color-temperature-1, `pentaxcolortemperature` gets (`Readonly: 0`, `Current: 5000`) and sets (`=4000`, rc=0), and the named control and raw `other/d018` agree in both states — on `.67` the same pair returned `Error (-1)` and rc=1. Blast radius proven to be one control: `--list-all-config` with WB=auto vs WB=color-temp-1 differs by exactly the single added `pentaxcolortemperature` line, and none of the other nine properties served by the same function gained a widget. No regressions: the six working Custom Image controls still read and round-trip (`pentaxcisaturation` `0→+2→0`, confirmed from fresh processes); `0xd024`–`0xd026` still `Error (-1)` and absent from the tree; `pentaxpropd02b`/`pentaxpropd02d` still `Readonly: 1` and refuse writes; capture canary PASS twice (`lifecycle=[1,4,0]`, `SP_0355.dng`, and again `SP_0356.dng` after the daemon was stopped and restored); no segfault/OOM since boot. **Stability run 2026-10-19: 3/3 PASS** per the #180 bar (three consecutive captures, each recorded separately) — no first-shot divergence, identical `[1, 4, 0]` lifecycle on all three, `state:0` close each time, daemon pids unchanged (249 / 27532, so no restart), process RSS and fd counts flat, zero kernel faults, camera never dropped off USB; `memfree` fell only by the three DNGs' page cache. Runner `scripts/stability-3shot.sh`, evidence `docs/evidence/o-v17c-stability-20261019/` (`shots.txt`, `health.txt`, `SUMMARY.md`). Scope is one scenario (RAW, short exposure, NR off, Pixel Shift off) — the other five #180 scenarios and any long-duration soak are **not** covered. Separately: protocol code `823` is unanswered by the daemon, and always has been (0 of 475 requests across every archived Mlog, each logged `SP_sendMsg Fail`; neighbouring `824` answered 160 times), so it is a long-standing stock-protocol gap and **not** a `.68` regression. **`.68` is the first build release-qualified as Color Temperature support and supersedes `.67` for that purpose.** Remaining: K-1 II behaviour of the relaxed branch untested (expected unchanged — `GetSet`-scalar-only admission plus model gating — but untested); async-apply behaviour unchanged, so assertions must keep re-reading from a fresh process. See `out/build-ov17c.log`. |
| `.67` | o-v17b-ci-colortemp-20261018 | **built 2026-10-19, pre-release gate GREEN (10 passed / 0 failed / 0 skipped); INSTALLED + VERIFIED 2026-10-19 09:30 local — device reports `FwVer:6.0.0.54.67;date:2026.10.18;`, provenance `build_id 6.0.0.54.67-o-v17b-ci-colortemp-20261018`, all 10 manifest files SHA-256 match (verdict verified). Install path: the zip-only staging was silently ignored by the on-boot watcher (issue #58), so the tree was extracted on-device from the staged zip (`unzip`, all 6 firmwareInfo MD5s matched) and applied via a detached `setsid ... /sbin/reboot` (uptime reset 27872→17 confirms a real reboot; earlier `/sbin/reboot`/`812` attempts never actually rebooted — those were AP-link flaps, not boots). Physical qualification on a K-3 III outstanding.** First candidate exposing the K-3 III white-balance Color Temperature (`0xd018`) and detailed Custom Image parameters (`0xd021`–`0xd029`) as libgphoto2 controls, plus a read-only descriptor passthrough for the CI user filter (`0xd02d`). Model-gated to the K-3 III family (`pentax_model_supports_color_temperature` / `pentax_model_supports_ci_detail`); ranges/signedness come from the camera's own `GetDevicePropDesc` via `_get_INT`/`_put_INT` (no hard-coded table). Carries the two Codex P1 fixes from PR #103: bounded read-back verification after every write (a PTP `0x2001` acknowledges, does not apply — read the raw `GetDevicePropValue` back and fail on mismatch), and empty-descriptor controls fail closed instead of rendering a zero-choice widget (`0xd024`–`0xd026` return empty enums on the recorded K-3 III). libgphoto2 `6c6142625` (merged PR #103), patcher `8a7f2bf5` (`main`). Artifact `out/o-v17b-ci-colortemp-20261018/FwPkt.zip` — sha256 `bed0ef63c4e6554fae257fb2a2a2df4bc4086218087947584a2329efccda9efd`, md5 `537e42dce2c84fd67e542d19878c3a62`, size 68390567; `install-manifest.json` present (10 mandatory files, `stage2_mandatory=true`, zip digest matches). Gate detail: container harness 20, python regression 243, code-780 version patch, FwPkt structural validation, firmwareInfo manifest, install-manifest currency, polestar_app Bulb branch intact, pgphoto timed-Bulb dispatch present. **PHYSICALLY QUALIFIED PARTIAL 2026-10-19** (`docs/evidence/o-v17b-physical-20261019/SUMMARY.md`): capture path PASS (single-shot and two-shot, distinct files, no crash, pgphoto pid stable); Custom Image `0xd021`–`0xd023` and `0xd027`–`0xd029` all write and round-trip through their named widgets (verified by fresh-process value read-back; signed path correct; ranges come from the camera's own descriptor). Corrected oracle: the raw `/main/other/d0XX` nodes do NOT reliably track these CI properties (they lag or encode differently — `d027` disagreed even before any write), so the named widget read from a fresh process is the only reliable oracle; a raw/widget disagreement is not a control failure. Read-only descriptor passthroughs `0xd02b`/`0xd02d` render correctly and refuse writes as designed. `0xd024`-`0xd026` confirmed to enumerate nothing - **there is no 255 sentinel** - so the fail-closed withholding is correct and stays. **The headline control FAILS**: `0xd018` Color Temperature is unreachable through `pentaxcolortemperature` (both get and set return `Error (-1)`) while the raw property reads `5000` and accepts `4000`; root cause is the `FormFlag == PTP_DPFF_None` branch in `_pentax_prop_get` conflating a range-less writable scalar with an empty enumeration - filed as libgphoto2 #104. `.67` is the running build but is **not** release-qualified as Color Temperature support; `.55` remains the last *fully* physically tested rollback target. **Superseded 2026-10-19 by `.68`**, which carries the #104 fix and passes the Color Temperature acceptance gate; the `0xd018` root-cause analysis above stands and is what `.68` fixes. See `out/build-o-v17b.log`. |
| `.53` | o-v15p | withdrawn artifact |
| `.54` | o-v15q | installed; reported `6.0.0.54.54` on code 780 |
| `.55` | o-v15r-supervisor-preload-20261005 | installed 2026-10-05; reports `6.0.0.54.55`. Superseded as the running build by `.59` on 2026-10-06; still the last *physically* tested build, so it remains the rollback target. |
| `.56` | o-v15s-orphan-candidate-recovery-20261005 | **superseded by `.57`, do not flash** — built 2026-10-05 and never installed, so its version is consumed but its content is a strict subset of `.57`. |
| `.57` | o-v15t-admission-deadlock-and-durability-20261006 | **superseded by `.58`, do not flash** — same libgphoto2 (`e6b55ad09`) and never installed, so its content is a strict subset of `.58`. It carried `e65404f5f` (#175 orphan recovery), `e0742ce03` (#176 durable save), `98ee8e67a` (#173 stale-output-obligation release — the self-locking gate behind "Bulb still fails" on `.55`) and `e6b55ad09` (#176 review durability made non-optional). |
| `.58` | o-v15u-first-capture-crash-pinpoint-20261006 | **superseded by `.59`, do not flash** — gate was GREEN but it was never installed (device was still on `.55`). `.59`'s libgphoto2 (`f3a8ffebf`) and patcher (`8949d83`) are both verified descendants of `.58`'s inputs (`e6b55ad09`, `984d5eb`) by `git merge-base --is-ancestor`, so its content is a strict subset of `.59`. |
| `.66` | o-v17a-shutter-fallback-off-20261012 | **installed on the device 2026-10-17 00:41 local; reports `6.0.0.54.66`; all 10 mandatory files verified against `install-manifest.json` (SHA-256 + size, verdict "verified")** — adds a fail-closed `gp_camera_get_single_config` wrapper (SHIM #6) that can synthesize a minimal TEXT widget for the `shutterspeed` widget when the camera rejects it, so pgphoto's `updateCameraViewFinder` does not see `ret:-1` and trigger a restart loop; synthesis only happens when `STAGE2_SHUTTER_FALLBACK=1`, shipped wrapper exports `0`. Targets the #187 shutter-widget failure mode (SP_SET_SHUTTER FAIL / degenerate camera-state burst on K-3 III connect). Installed via the tree path (`/app/sd/FwPkt/` streamed + 6/6 firmwareInfo MD5 matches on-device + plain reboot) after the zip `.part` flow kept dying on AP-link flaps. On-device provenance: libgphoto2 `2cde4485b`, build_id `o-v17a-shutter-fallback-off-20261012`. Pre-release gate GREEN 2026-10-17 (10 passed / 0 failed / 0 skipped). **Physical qualification PENDING — no camera on the USB bus at install time; SHIM #6 A/B (`STAGE2_SHUTTER_FALLBACK=0` vs `1`) and K-1 II regression check still outstanding before enabling by default.** Toolchain note: camlib .so files rebuilt with GCC 13.3.0 (vs o-v16g's GCC 6.3.0) from identical libgphoto2 source `2cde4485b`. Supersedes `.65` as the running build; `.55` remains the last *physically* tested build and the rollback target. See `docs/evidence/o-v17a-offline-validation-20261012/RELEASE-20261016.md`. |
| `.65` | o-v16g-k3iii-timed-bulb-20261010 | **installed on the device 2026-10-11; runtime provenance verified** — routes positive-duration K-3 III capture requests through pgphoto's timed Bulb helper. Offline gates, package structure, and exact firmwareInfo manifest validation passed at build time; on-device `openpolaris-libgphoto2-provenance.txt` matches the candidate (libgphoto2 `2cde4485b`, patcher `9d0efe0`, build_id `6.0.0.54.65-o-v16g-k3iii-timed-bulb-20261010`). K-3 III timed-Bulb Layer B qualification (duration/file/idle trace) is still pending; do not claim Bulb fixed until it passes. **Superseded as the running build by `.66` on 2026-10-17.** See `docs/evidence/o-v16g-k3iii-timed-bulb-20261010/SUMMARY.md`. |
| `.64` | o-v16f-bulb-branch-audit-20261010 | **DIAGNOSTIC — DO NOT STAGE** — omits the retired zero-bulb patch and verifies the original app branch, but static pgphoto analysis shows code 264 still reaches `captureImage`; no K-3 III Bulb action/duration bridge is implemented or physically tested. See `docs/evidence/o-v16f-bulb-branch-audit-20261010/SUMMARY.md`. |
| `.63` | o-v16e-bulbstart98-20261010 | **candidate; not installed** — carries libgphoto2 #98 recovery admission fix. Built before PR #99 merged; no physical Bulb qualification. See the provenance registry. |
| `.62` | o-v16c-context-lifetime-20261009 | **installed 2026-10-09; runtime provenance verified** — manual canary and forced download-teardown checks passed; Bulb duration and pgphoto dispatch remain unqualified. See `docs/evidence/o-v16c-context-lifetime-20261009/SUMMARY.md`. |
| `.61` | o-v16b-empty-path-capture-20261008 | **installed on the device 2026-10-08 15:39 local; reports `6.0.0.54.61`; build_id `6.0.0.54.61-o-v16b-empty-path-capture-20261008` confirmed on-device** — first candidate carrying the #183 empty-path capture fix (`captureImage ret 0` with a blank `CameraFilePath` now returns `GP_ERROR_CAMERA_ERROR` and logs `capture-outcome=empty-path` instead of the false `264 state:2/5/0` success; default ON via `STAGE2_CAPTURE_EMPTY_PATH_CHECK`, escape hatch `0`). Gate GREEN 2026-10-08 (only skip: `libgphoto2:test-gp-port`, no host DTR/CTS fixture); container suite 18 pass / 2 env-skipped; #183 regression `test_stage2_capture_empty_path.sh` 7/7. libgphoto2 `678d0dc3a` (docs-only since `f3a8ffeb`, no code delta), patcher `4be4a5f/main`. Published to `ian-morgan99/PrivateResearch` `firmware-packets/6.0.0.54.61--o-v16b-empty-path-capture-20261008/`. Staged with 6/6 on-device MD5+size matches; rebooted 14:39 UTC, gimbal upgrade success, staged package auto-cleaned. **Physical qualification FAILED for bulb (2026-10-08 16:37): the camera never actuates — no shutter sound, no file, and Benro Connect's own bulb path fails identically while staying on the red button. On-device tracing shows libgphoto2 returns -10 (GP_ERROR_TIMEOUT), not GP_OK, so #183's premise and this build's empty-path check are both inert for this failure. See `docs/evidence/o-v16b-bulb-trace-20261008/SUMMARY.md` and #186.** Supersedes `.60` as the running build. |
| `.60` | o-v16a-captureguard-20261006 | **installed on the device 2026-10-07 11:09; reports `6.0.0.54.60`; build_id `6.0.0.54.60-o-v16a-captureguard-20261006` verified on-device; **live canary PASSED 2026-10-07 11:47–11:52 local: 16/16 captures clean (5 guard-off, 11 guard-on incl. rapid-fire), RAW+JPEG card so `--expected-files 2` — see `docs/evidence/o-v16a-ab-20261007/SUMMARY.md`** — staged to `/app/sd/FwPkt` via tar stream with 6/6 on-device MD5+size matches against the on-card `firmwareInfo`; rebooted 2026-10-07 10:09 UTC, back with new FwVer at 11:29 local. Guard (`STAGE2_CAPTURE_GUARD`) confirmed compiled into `/app/lib/stage2/libpolaris_stage2.so` and confirmed NOT set in the shipped wrapper (default off, as registered). Supersedes `.59` as the running build; **superseded by `.61` on 2026-10-08** (`.61` = `.60` plus the #183 empty-path check; the `STAGE2_CAPTURE_GUARD` default is unchanged, still off). |
| `.59` | o-v15v-k1ii-msc-pid-20261006 | **installed on the device 2026-10-06; reports `6.0.0.54.59`; live canary pending (no camera on USB); superseded as the running build by `.60` on 2026-10-07** — see `docs/evidence/o-v15v-install-20261006/SUMMARY.md`. Gate GREEN 2026-10-06 (only skip: `libgphoto2:test-gp-port`, no host DTR/CTS fixture). Everything `.58` carried (incl. `4a8359f` crash-handler re-assertion, #175, #176, #173), plus libgphoto2 `1b65cbe0a` / `15c6b9805` / `f3a8ffebf` (#179 — K-1 II `0x0182` identified as the MSC PID instead of autodetecting to nothing and silently adopting hardcoded K-3 III abilities, and the R0 containment guard re-keyed onto product IDs). md5 `2afb6e3b087af03e8d0d902626e7327a`, appfs `e31baa64438a8a2f934dbb9ddcadf5a2`, libgphoto2 `f3a8ffebf285b0f32d2bef366f1c5c4f1687077d`, patcher `8949d83/main`. Published to `ian-morgan99/PrivateResearch` `firmware-packets/6.0.0.54.59--o-v15v-k1ii-msc-pid-20261006/`. Staged to `/app/sd/FwPkt` with 6/6 on-device MD5+size matches against the on-card `firmwareInfo`; rebooted 2026-10-06 06:28:44Z. |

## Why the registry exists (#169)

`.54` is the failure case: the baseline was left at `.53` when o-v15q was
installed, so `--next` derived `.54` again — a duplicate of a version already
running on hardware. A single mutable baseline cannot detect that, because the
information "`.54` was used" was not recorded anywhere the tool read.

`--next` now derives from `max(baseline, registry) + 1` and then skips anything
already in the registry, so a stale baseline can no longer produce a duplicate.
`--record` advances the baseline **and** appends to the registry in one step, so
the two cannot drift apart during a release.

Keep the human cross-check anyway — it is a secondary defence, not the primary
one: confirm the derived value against what the device actually reports
(`canary-probe.py --probe --expected-sw <value>`) before building.

When the next candidate is promoted, let `--record` update both entries in the
same commit as its provenance row and release evidence.
