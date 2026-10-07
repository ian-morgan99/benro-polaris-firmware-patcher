# Polaris display firmware-version release state

Benro Connect must receive the exact five-component version from code 780.
The release builder treats the value below as the last accepted display version
and refuses to build a candidate that is unchanged, lower, from another
version family, or missing the fifth build component.

```text
last_display_fwver=6.0.0.54.60
```

## Consumed-version registry (authoritative)

Every display version ever issued is listed below. `verify_display_fwver_monotonic.py`
reads these lines and refuses to hand out any of them again, **regardless of what
`last_display_fwver` says**. The list is append-only: never delete or edit an
entry, only add one when a candidate is claimed.

```text
consumed_display_fwver=6.0.0.54.53
consumed_display_fwver=6.0.0.54.60
consumed_display_fwver=6.0.0.54.59
consumed_display_fwver=6.0.0.54.58
consumed_display_fwver=6.0.0.54.57
consumed_display_fwver=6.0.0.54.56
consumed_display_fwver=6.0.0.54.54
consumed_display_fwver=6.0.0.54.55
```

| Version | Candidate | Notes |
| --- | --- | --- |
| `.53` | o-v15p | withdrawn artifact |
| `.54` | o-v15q | installed; reported `6.0.0.54.54` on code 780 |
| `.55` | o-v15r-supervisor-preload-20261005 | installed 2026-10-05; reports `6.0.0.54.55`. Superseded as the running build by `.59` on 2026-10-06; still the last *physically* tested build, so it remains the rollback target. |
| `.56` | o-v15s-orphan-candidate-recovery-20261005 | **superseded by `.57`, do not flash** — built 2026-10-05 and never installed, so its version is consumed but its content is a strict subset of `.57`. |
| `.57` | o-v15t-admission-deadlock-and-durability-20261006 | **superseded by `.58`, do not flash** — same libgphoto2 (`e6b55ad09`) and never installed, so its content is a strict subset of `.58`. It carried `e65404f5f` (#175 orphan recovery), `e0742ce03` (#176 durable save), `98ee8e67a` (#173 stale-output-obligation release — the self-locking gate behind "Bulb still fails" on `.55`) and `e6b55ad09` (#176 review durability made non-optional). |
| `.58` | o-v15u-first-capture-crash-pinpoint-20261006 | **superseded by `.59`, do not flash** — gate was GREEN but it was never installed (device was still on `.55`). `.59`'s libgphoto2 (`f3a8ffebf`) and patcher (`8949d83`) are both verified descendants of `.58`'s inputs (`e6b55ad09`, `984d5eb`) by `git merge-base --is-ancestor`, so its content is a strict subset of `.59`. |
| `.60` | o-v16a-captureguard-20261006 | **installed on the device 2026-10-07 11:09; reports `6.0.0.54.60`; build_id `6.0.0.54.60-o-v16a-captureguard-20261006` verified on-device; **live canary PASSED 2026-10-07 11:47–11:52 local: 16/16 captures clean (5 guard-off, 11 guard-on incl. rapid-fire), RAW+JPEG card so `--expected-files 2` — see `docs/evidence/o-v16a-ab-20261007/SUMMARY.md`** — staged to `/app/sd/FwPkt` via tar stream with 6/6 on-device MD5+size matches against the on-card `firmwareInfo`; rebooted 2026-10-07 10:09 UTC, back with new FwVer at 11:29 local. Guard (`STAGE2_CAPTURE_GUARD`) confirmed compiled into `/app/lib/stage2/libpolaris_stage2.so` and confirmed NOT set in the shipped wrapper (default off, as registered). Supersedes `.59` as the running build. |
| `.59` | o-v15v-k1ii-msc-pid-20261006 | **installed on the device 2026-10-06; reports `6.0.0.54.59`; live canary pending (no camera on USB); superseded as the running build by `.60` on 2026-10-07** — see `docs/evidence/o-v15v-install-20261006/SUMMARY.md`. Gate GREEN 2026-10-06 (only skip: `libgphoto2:test-gp-port`, no host DTR/CTS fixture). Everything `.58` carried (incl. `4a8359f` crash-handler re-assertion, #175, #176, #173), plus libgphoto2 `1b65cbe0a` / `15c6b9805` / `f3a8ffebf` (#179 — K-1 II `0x0182` identified as the MSC PID instead of autodetecting to nothing and silently adopting hardcoded K-3 III abilities, and the R0 containment guard re-keyed onto product IDs). md5 `2afb6e3b087af03e8d0d902626e7327a`, appfs `e31baa64438a8a2f934dbb9ddcadf5a2`, libgphoto2 `f3a8ffebf285b0f32d2bef366f1c5c4f1687077d`, patcher `8949d83/main`. Published to `ian-morgan99/PrivateResearch` `firmware-packets/o-v15v-k1ii-msc-pid-20261006/`. Staged to `/app/sd/FwPkt` with 6/6 on-device MD5+size matches against the on-card `firmwareInfo`; rebooted 2026-10-06 06:28:44Z. |

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
