# FwPkt Provenance Contract (cross-repo, cross-agent)

> **Status: binding convention.** Applies to every agent and human in
> `BenroPolarisPatcher`, `OpenPolaris`, and the `libgphoto2` fork, no matter
> which repo or session produced an artifact. If a fact appears in more than one
> place, this file is the source of truth for *which* FwPkt bytes are which.
>
> **Why it exists.** On 2026-09-07/08 a v3 build was zipped by one agent session,
> handed to the user as a bare `FwPkt.zip`, and staged on the SD card. Its outer
> MD5 (`5491835a…`) matched no entry in any repo, so for ~24 h nobody could say
> "the zip on the card is build X" without re-extracting it. The payload was
> correct (v3), but the *provenance chain* was broken because nothing recorded
> the outer hash + commit links at handoff time. This contract closes that gap.

## Core principles

1. **Version control is primary; hashes are the fingerprint.** Every FwPkt
   artifact is identified by (a) the `libgphoto2` source commit SHA it was built
   from, and (b) the patcher repo commit/branch that produced it. The zip's own
   MD5 + SHA-256 and its payload `appfs.ubifs` MD5 are recorded as the
   *fingerprint* to verify bytes at handoff — they never replace the commit link.
2. **Zips do not go in public git.** Zip bytes live on disk (`builds/`, `out/`)
   and on the SMB share / SD card. Only the registry row (hashes + commit links)
   is committed to a repo. The private zip location now exists: every built zip
   is uploaded to the **private** `ian-morgan99/PrivateResearch` repo under
   `firmware-packets/<registry-id>/FwPkt.zip` in the same session it is built
   (see the `fwpkt-private-upload` skill). The registry row's location column
   points there; other agents clone the private repo and verify all four
   handoff values before staging. Until a row has been uploaded, its location is
   a local path or `smb:`/`sd:` reference.
3. **Record before the artifact leaves your control.** The moment an agent (or
   human) produces or receives an FwPkt zip, it writes/updates its registry row
   *in the same session*, before the file is copied to another machine, repo, or
   card. A zip with no registry row is "unprovenanced" and must not be staged on
   a device.

## The registry (single source of truth)

One table, kept in this file. Every FwPkt artifact ever produced gets exactly one
row. Hashes below were recomputed from the files on disk on 2026-09-08 unless
marked otherwise.

| id | path / location | zip MD5 | zip SHA-256 (16) | appfs MD5 | libgphoto2 commit | patcher commit/branch | status | notes |
|----|-----------------|---------|------------------|-----------|-------------------|-----------------------|--------|-------|
| stock | `firmware/FwPkt.zip` | `90bdad51…d2980102` | `f980fe5245a1f85b` | `47f2ae68…397b` (TESTED_APPFS_MD5) | n/a (stock 4.0.0.32) | n/a | **stock reference** | Unmodified Benro May-2025. The baseline every build is diffed against. |
| b-0823 | `builds/2026-08-23/FwPkt.zip` | `25403283…1aca1837e` | `cc28906305162572` | `1775c7bc…bb13f367` | `da8c33482` (canonical Pentax) | pentax-only build | pentax-only | First Pentax libgphoto2 stack. No HDMI. |
| b-0827r2 | `builds/2026-08-27-combined-720p60/FwPkt.zip` | `e4a6a37d…ca8f45d4` (rebuild2) | `ddc1aab69c97f9d2` | `91629acf…21913124f` | `da8c33482` | layered on b-0823 + HDMI 720p60 live-only | combined (rebuild2) | rebuild2 fixed the stale firmwareInfo appfs MD5. Round-trip verified, not device-validated. |
| b-0829 | `builds/2026-08-29-libgphoto2-only/FwPkt.zip` | `25403283…1aca1837e` (=b-0823) | `cc28906305162572` | `1775c7bc…bb13f367` | `da8c33482` | repackaged from b-0823 (branch `agents/libgphoto2-only-fork`) | libgphoto2-only repackage | Byte-identical payload to b-0823; named deliverable only. |
| b-0830 | `builds/2026-08-30-padded-appfs/FwPkt.zip` | `92da8883…b5fa22b94067` | `0d4ae8101cc190ee` | `4bd9131b…ff39ea` | `da8c33482` | padded-appfs experiment (branch `agents/libgphoto2-only-fork`) | padded-appfs test | Appended one 0xFF PEB to restore stock partition size. Hypothesis test, not a release. |
| b-0905 | `builds/2026-09-05-combined-pentax256-hdmi720p60/FwPkt.zip` | `e6fe0c9c…40b474e6` | `df237eb1f88f6411` | `b3e608a0…46f11abf` | `91f4c9146` (ian-morgan99/libgphoto2 master) | patcher `1c2f9ce` + HDMI `b3aa306` (extracted via git show) | combined pentax256+hdmi | First build with real Pentax vendor code backing the 256 MiB capture cap. Round-trip verified, not device-validated. |
| b-0907cand | `builds/2026-09-07-k1ii-k3iii-candidate/FwPkt.zip` | `955ec67a…40ec94e` | `61a000cf62d911b8` | `d745fe16…c49d3d1` | `6aa3e4e66` (ian-morgan99/libgphoto2) | patcher `af5b0d3` (per OpenPolaris handover doc) | K-1II/K-3III candidate | Clean libgphoto2 commit; provenance fields partially filled. |
| o-fixed | `out/k1ii-k3iii-fixed/FwPkt.zip` | `dcfeb60c…4588148` | `196253430f9f4725` | `b8104485…ac80e94ae1` | release 2.5.34 (commit field blank in provenance) | patcher ~`fbf5539` era (pre-iolibs fix) | fixed (pre-iolibs) | Contains port-strip fix, NOT the iolibs/stock-core fix. |
| o-v3 | `out/k1ii-k3iii-fixed-v3/` (tree; **no canonical zip in repo**) | SD-zip: `5491835a…d5518018` | — | `d220682e…c4927da0620efa5` | **vanilla 2.5.34 (NOT the fork)** | patcher ~`f3dbff4`+`9e47a34` era (iolibs + post-repack assertion) | **v3 — installed on device, SUPERSEDED** | Built *without* `--libgphoto2-source`, so `build_ptp2.sh` downloaded the vanilla GitHub release tarball. Its `ptp2.so` (877,348 B) has **none** of the Pentax-fork markers (`pentax_identify_supported_model`, "stale Pentax session", etc.) — confirmed by string comparison against the candidate fork build. This is why K-1 II / K-3 III fell into the `-2` config loop on-device. Zipped outside `patch.sh`; outer hash never recorded. Installed Sep 7 22:15 UTC. |
| **o-v4** | `out/k1ii-k3iii-fixed-v4-20260908/FwPkt.zip` | `d0674ef6…e7a8fd90` | `cfcd8c7c0942e739` | `85c3a693…a87781` (appfs) | **`6aa3e4e66` (ian-morgan99/libgphoto2 master, the real Pentax fork)** | patcher main @ `a975933` era; built via `patch-polaris.sh --libgphoto2-source LibGphoto2/libgphoto2` | **v4 — CORRECT fork build (INSTALLED BASELINE)** | Built 2026-09-08 with the Pentax fork mounted as source input. `ptp2.so` = 927,572 B (matches candidate), all fork markers present (`pentax_identify_supported_model`, "stale Pentax session", K-1 II / K-3 III models). Provenance: `git_commit=6aa3e4e66`, dirty_diff_hash recorded. Installed on the Polaris as of 2026-09-08; superseded as staging candidate by o-v5b (keep v4 as the factory-restore reference for this device). |
| **o-v5** | `out/k1ii-k3iii-v5-aperture-alias-20260909/FwPkt.zip` | `751250ce…edbc87a` (full: `751250ce18adc61dcb30aabe6edbc87a`) | `af021c8f39747bdf` (full SHA-256 in build log `/tmp/build-v5-*.log`) | `0717190c…ff74` (appfs) | **`0f0858087` (ian-morgan99/libgphoto2 master = v4 base `6aa3e4e66` + #53 Pentax `aperture` alias commit)** | patcher main @ `2c52c40`; built 2026-09-09 via `patch-polaris.sh --fwpkt firmware/FwPkt (PrivateResearch copy) --libgphoto2-source LibGphoto2/libgphoto2 --allow-dirty-source` | **v5 candidate — SUPERSEDED by o-v5b** (built before the #69 duplicate-registration fix landed) | v4 + generic `aperture` widget for Pentax. All build gates passed incl. post-repack content assertion (#38/#39 fix). Kept for provenance; do not stage — use o-v5b. |
| **o-v5b** | `out/k1ii-k3iii-v5b-aperture-alias-plus69-20260909/FwPkt.zip` | `2c11a5b6…f6aa` (full: `2c11a5b6f3143e5c3b815e210803f6aa`) | `073d29405b922db8` (full SHA-256 in build log `/tmp/build-v5b-*.log`) | `0d445fc0…a26` (appfs) | **`990281d72` (ian-morgan99/libgphoto2 master = v4 base + #53 aperture alias `0f0858087` + public-API test upgrade `e8dfddfca` + #69 duplicate-registration fix)** | patcher main @ `6a0ddab`; built 2026-09-09 via `patch-polaris.sh --fwpkt firmware/FwPkt (PrivateResearch copy) --libgphoto2-source LibGphoto2/libgphoto2 --allow-dirty-source` | **v5b candidate — BEST build; PENDING K-1 II hardware validation** | v4 + #53 `aperture` alias + #69 cleanup. All build gates passed incl. post-repack content assertion (#38/#39 fix) and firmwareInfo cross-check. `ptp2.so` = 927,572 B (v5's 927,600 minus the removed duplicate entry). Provenance file: `git_commit=990281d72`. This is the build to stage on the SD card for the K-1 II round. |
| **o-v6-lockfix** | `out/k3iii-lock-recovery-v6-clean-20260909/FwPkt.zip` | `7a1ba1c69845fd77e4b9a4ba104744ba` | `93903726570dfd20f014da4c5c1429240144dd28b4dbb9a64489aa44805e0de3` | `e2c479db2fa8339e6b20d075c363ee1a` (appfs SHA-256 `fbf4916f028fc105ba4e460f65911f1ca10e8024cb9b284b3b8b223857f58e1e`) | **[`990281d72`](https://github.com/ian-morgan99/libgphoto2/commit/990281d72b751267f5c1d20567a5f9ec3bb0fa9d)** | patcher main @ **[`5d6b59f`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/commit/5d6b59fc0b9be6386c6994ad74ec8f1fedb2064f)** | **clean-source recovery candidate; PENDING INSTALL** | Fixes persistent ownerless pgphoto launch locks (#34) and installs the stock core/port as a matched pair (#51). Built from a clean detached clone; `dirty_diff_hash=` is empty. All ARM ABI/symbol, Stage-2, post-repack content, firmwareInfo, and ZIP-layout gates passed. This exact artifact is the only v6 candidate authorised for staging. |
| **o-v7-preview-shims** | `out/k1ii-k3iii-v7-preview-shims-20260910/FwPkt.zip` | `9e2addfc4f904aff82f21031419609d0` | `8e51c1b4f8f0b574ddd0e5cc85f8ade1e268e5d4fc63dc491376ed0982c8c2cf` | `66cb2604376587721eb6bd5ab661b681` (appfs) | **[`38780d88b`](https://github.com/ian-morgan99/libgphoto2/commit/38780d88bbb0d937f87a03677b990942dd3c6c09)** | patcher main @ **[`de98a23`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/commit/de98a23)** (includes `08a8730` Shim #4 pentaxpclvkeep, `446fbfd`+`de98a23` Shim #5 non-blocking preview backoff, `6902962` min-interval rate gate, `b7b93a3` exit-safe wrapper termination) | **candidate — PENDING K-3 III on-device verification** | First build carrying the Stage-2 preview shims (#36/#55): keep-live-view at init, non-blocking timeout cooldown, 2 s minimum-interval gate (all env-gated: `STAGE2_PENTAX_KEEP_LV`, `STAGE2_PENTAX_PREVIEW_BACKOFF[_MAX/_SECS]`, `STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_SECS`). Built 2026-09-10 via `patch-polaris.sh --fwpkt firmware/FwPkt (PrivateResearch copy) --libgphoto2-source LibGphoto2/libgphoto2 --allow-dirty-source` (dirt = 2 untracked test JPEGs; tracked tree clean). All gates passed incl. #51 matched core+port replacement, post-repack content assertion (#39), firmwareInfo cross-check, ZIP layout. Verification plan: frame churn bounded (~0.5 Hz max + 30 s cooldown after 3 timeouts), `wlan0` stable during preview-on session, SSH reachable, and the -110 rate-limited return verified benign on the 9090 protocol (TA #55 acceptance). |
| **o-v8-modelgate** | `out/k1ii-k3iii-v8-modelgate-20260910/FwPkt.zip` | `b2812f30da00556453adfa89d9811fda` | `da3bf8ed8dbc07bd1955e267c75fc792a6ddb5cd6351aa46d03763c36e3a1c01` (full SHA-256) | `e5303037d3e407c2ff245c3a28a9c606` (appfs, matches firmwareInfo) | **[`5e1436fc0`](https://github.com/ian-morgan99/libgphoto2/commit/5e1436fc0c7086afac015269318c4d69ef88e3d6)** (test-only delta over o-v7's `38780d88b`: `examples/pentax-safe-focus.c` + docs; runtime camlib/core/port byte-identical to o-v7) | patcher main @ **[`46f3e67`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/commit/46f3e67)** (adds `0953dde` case-insensitive Pentax/Ricoh/GX10 model gate — the fix that makes o-v7's Shims #4/#5 actually engage; plus docs/provenance commits) | **candidate — PENDING on-device verification of `[stage2] keep-lv:` activation** | Built 2026-09-10 via `patch-polaris.sh --fwpkt firmware/FwPkt (PrivateResearch copy) --libgphoto2-source LibGphoto2/libgphoto2 --allow-dirty-source` (dirt = 2 untracked test JPEGs; dirty_diff_hash `4fac6d93…`). All gates passed incl. #51 matched core+port, post-repack content assertion (#39), firmwareInfo cross-check, ZIP layout. Purpose: prove the keep-lv shims now log `[stage2] keep-lv:` on K-1 II / K-3 III / K-01 (o-v7 field test showed them silently inactive due to the colon-prefix gate bug). |
| **o-v9-reviewed-controls** | `firmware-packets/o-v9-reviewed-controls/FwPkt.zip` (`ian-morgan99/PrivateResearch`, private) | `67e8411f084f672919ecd29db5601b2e` | `ca55f7de51cececcf57216521b822302c840f6ae9f8953ec37cae8936a48b0e4` | `3048c708ed75d829567e96d2ef74bb88` | **[`4c2fa7d62`](https://github.com/ian-morgan99/libgphoto2/commit/4c2fa7d62a42171ee981f2a1b502a8b29666642e)** | patcher main @ **[`b3b0e99`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/commit/b3b0e99)** | **SUPERSEDED by o-v9b** | First clean-source build after control audit. Package gates passed, but the subsequent source-input regression audit found that an inaccessible Git object database could make the dirty-status check inconclusive; replaced by o-v9b built after fail-closed fix `152bd33`. Do not stage. |
| **o-v9b-reviewed-controls** | `firmware-packets/o-v9b-reviewed-controls/FwPkt.zip` (`ian-morgan99/PrivateResearch`, private) | `215166be90dc3dabc31ae2ca552b6396` | `ac94301e6bccf971` (full: `ac94301e6bccf971130b477959b7feba8ba8ab3b5db5943b7cbf4ff897ca4eb7`) | `414950000b9a4fd17df18ffd4be2b8e7` | **[`4c2fa7d62`](https://github.com/ian-morgan99/libgphoto2/commit/4c2fa7d62a42171ee981f2a1b502a8b29666642e)** | patcher main @ **[`152bd33`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/commit/152bd33)** | **SUPERSEDED by o-v9c** | Clean, self-contained-source rebuild carrying o-v8's corrected Stage-2 Pentax model gate plus reviewed generic `manualfocusdrive`. Guessed `autofocusdrive` and scalar `imageformat` mappings were excluded before build. Replaced only so the public fail-closed source-selection fix is itself part of the candidate's exact patcher revision. |
| **o-v9c-failclosed-source** | `firmware-packets/o-v9c-failclosed-source/FwPkt.zip` (`ian-morgan99/PrivateResearch`, private) | `a25079001022fa80068a54c35ca862a2` | `f4c522320f209d60` (full: `f4c522320f209d608d0e9d33a5b55a49121bd3756af6fc13cf8abc545d91dbc1`) | `ecd1687ab5b0b97dc84a2dfc6b2da04f` | **[`1ef21463b`](https://github.com/ian-morgan99/libgphoto2/commit/1ef21463b56ef2d132c2d370ce69833a33848ecc)** | patcher main @ **[`1bd7e78`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/commit/1bd7e78)** | **SUPERSEDED by o-v9d** | Clean-source build with source-selection fail-closed. Replaced because its duplicate generic near/far focus registrations route K-1 II to the K-3 III opcode; do not stage. |
| **o-v9d-model-aware-focus** | `firmware-packets/o-v9d-model-aware-focus/FwPkt.zip` (`ian-morgan99/PrivateResearch`, private) | `90968076a1841e46017372a390277a0d` | `f673123958e0d095` (full: `f673123958e0d09576633a113850e7e1226759910528675957ca3b53be016e8e`) | `1068c3b99272f99b9c0d3f033960aee5` | **[`90de508a5`](https://github.com/ian-morgan99/libgphoto2/commit/90de508a5441cb7e2b1b02d601b15a7547d7bcee)** | patcher main @ **[`af5d7d5`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/commit/af5d7d5)** | **INSTALLED 2026-09-11; live view PASS; focus and capture FAIL** | Boot/runtime integrity passed. K-3 III live control passed, followed by one continuous 120 s stream with 58 complete JPEG frames (~0.483 fps); all 24 health samples retained the route and ports 22/9090. Live view then stopped cleanly. Operator observed no focus movement despite 311 `ret:0`; pgphoto did not log model-aware `0x9017` dispatch. Capture began but terminated `-110` because transfer candidate 1 was still pending, mapped to `state:-1005` / Shot failed. Camera recovered to state 1. See `docs/evidence/fwpkt-install/v9d-k3iii-qualification-2026-09-11/SUMMARY.md`; patcher #37/#47/#54, OpenPolaris #80 and libgphoto2 #59. |
| **o-v9e-focus-idle-wait** | `firmware-packets/o-v9e-focus-idle-wait/FwPkt.zip` (`ian-morgan99/PrivateResearch`, private) | `89e3714ee5f650c5d2463be11996b0ca` | `9af10ebf42b17193` (full: `9af10ebf42b17193e073f46902b6a5263509a6be19155ee307e8fc3350d52583`) | `3434cd42b3d092552c9599ff338fffc3` | **[`90de508a5`](https://github.com/ian-morgan99/libgphoto2/commit/90de508a5441cb7e2b1b02d601b15a7547d7bcee)** | patcher main @ **[`37bac5b`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/commit/37bac5b)** | **INSTALLED 2026-09-11; K-3 III live view and manual focus PASS** | Reproducible clean-source successor to o-v9d. Extends only pgphoto's structurally discovered pre-dispatch `waitCameraIdle` budget from 500 ms to 3000 ms; opcode, direction, magnitude, and completed-movement retry behavior are unchanged. Focused tests 5/5 PASS; full-stack/package gates PASS. On K-3 III, held PC-LV delivered 44 complete JPEGs, manual focus returned raw `0x2001`, frames continued, and the operator explicitly confirmed the app manual-focus controls work. Autofocus is not qualified by this result and remains tracked separately. Processes and ports 22/8080/9090 remained healthy. Capture timeout remains separate. See `docs/K3III-FOCUS-RECOVERY-PLAN-2026-09-11.md` and patcher #47. |
| **o-v9f-stability-candidate** | `firmware-packets/o-v9f-stability-candidate/FwPkt.zip` (`ian-morgan99/PrivateResearch`, private) | `b2703baf0ea8d57992c780eeb2bb1a33` | `c3a14fe6d8cb242b` (full: `c3a14fe6d8cb242b811b436ec6d37e7e485d18b1c84a251e2e0194905e59ed6b`) | `6de58bfbd8a001b8254c90b1474ede5f` | **[`a96aa9fc4`](https://github.com/ian-morgan99/libgphoto2/commit/a96aa9fc45c4b364701a82827f8e57967ad38c07)** | patcher main @ **[`1b021e9`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/commit/1b021e9)** | **INSTALLED 2026-09-11 18:45 (SD/cold-boot); K-1 II focus PASS, config reads FAIL** | Stability candidate built from canonical stock MD5 `90bdad51...`: debounced single-owner USB camera-identity restart for body swaps; bounded K-3 III focus-mode-1 autofocus with active-PC-LV and no-candidate guards; post-capture extra-candidate descriptor diagnostics that preserve unknown data; corrected generic K-1 II focus direction. Full ARM/core/port/boundary, firmwareInfo, embedded-payload and ZIP-layout gates PASS. **2026-09-11 K-1 II qualification (clean boot, `25fb:0183` PTP):** camera detect/state PASS (`state:1`), 8080+9090 up, `manualfocusdrive ret 0` + `getFocusInfo ret 0` (the o-v9d `0x02fa` focus failure is fixed); capturetarget/shutterspeed/ISO reads return `get_single_config -2` → pgphoto `ret -1`, controls dead in app (issue #59). Note: an earlier zip-only SD staging was silently ignored by the watcher, so ~5 h of K-1 II testing ran on o-v9d (issue #58); this row's install is the first correct one. See `docs/evidence/k1ii-ov9f-2026-09-11/`. |
| **o-v9g-issue73-reconcile** | `out/v9f-issue73/FwPkt.zip` (local; to be published to `firmware-packets/o-v9g-issue73-reconcile/`) | `df6ba3e7d578c982c43681f444ce1af4` | `fff19caf23501716` (full: `fff19caf23501716…`) | `c90f951eff1b305522c3ba42966011d5` | **[`90736a1ac`](https://github.com/ian-morgan99/libgphoto2/commit/90736a1acfdda7865a532b791398da5a0f95c268)** | patcher main @ **[`52336aa`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/commit/52336aa)** | **BUILT 2026-09-12 (not yet installed); libgphoto2 #73 dual-format candidate reconciliation** | Successor to o-v9f-stability-candidate. Adds post-capture reconciliation of all transfer candidates from the same initiated exposure (bounded count/time, GetAllConditions verification after each deletion) so a RAW+ / dual-format shot no longer leaves a second pending candidate that blocks the next shutter with `-110`/`state:-1005`. Pre-capture stale-candidate barrier preserved unchanged. Built via documented `./patch-polaris.sh` (full mode, clean source clone at `90736a1ac`, stock FwPkt appfs MD5 `47f2ae68…`). Addresses patcher #60 (RAW+ intervalometer Shot Failed) and libgphoto2 #73. Not yet hardware-qualified: two consecutive K-3 III captures in dual-format config required before release claim. |

### Registry rules
- **One row per artifact.** Never reuse a row for two different byte sets.
- **Hashes are recomputed, not copied forward.** When you add a row, run
  `md5sum`/`sha256sum` on the actual file and read the appfs MD5 from that build's
  `firmwareInfo`. Do not trust a prior doc's number.
- **Commit links are mandatory for non-stock builds.** If you don't know the
  libgphoto2 SHA or patcher commit, fill `?` and open an issue to backfill — do
  not leave it blank silently (the v3 row is the anti-example).
- **Status vocabulary** (from `docs/CRITICAL-REVIEW.md`): `stock reference`,
  `pentax-only`, `combined`, `candidate`, `fixed`, `vN`. Add a short note for any
  non-obvious state.

## The handoff rule (binds every repo + agent)

When an FwPkt zip crosses a boundary — between repos, agents, humans, machines,
or onto the SD card — the sender MUST pass **all four** of these with it:

1. the registry `id` (e.g. `o-v3`),
2. the zip MD5 + SHA-256,
3. the payload appfs MD5,
4. the libgphoto2 commit SHA + patcher commit/branch.

The receiver MUST verify the received file's MD5+SHA-256 match the registry row
**before** staging it on a device or copying it further. If they don't match, stop
and reconcile — do not stage an unprovenanced zip.

Concrete check (run before any SD-card staging):
```bash
# given the sender's claimed values:
md5sum FwPkt.zip            # must equal registry "zip MD5"
sha256sum FwPkt.zip        # must equal registry "zip SHA-256"
unzip -p FwPkt.zip FwPkt/firmwareInfo | grep 'appfs'   # appfs MD5 must match registry
```

## Where each repo records its side

| Repo | What it owns | Where the row lives |
|------|--------------|---------------------|
| `BenroPolarisPatcher` | All builds, the patcher pipeline, this registry | **this file** (canonical) + `docs/RUN-JOURNAL.md` for the chronological narrative |
| `OpenPolaris` | Delivery (`ScpFirmwareDelivery`), protocol codes, HW test results | Records the *received* registry id + hashes in its handover doc; links back here. Does **not** re-derive provenance. |
| `libgphoto2` fork | The Pentax source commits that builds are made from | Provides the commit SHA a build is pinned to; does not track FwPkt zips itself. |

## Build-process rule: always pass `--libgphoto2-source` (the v3 root cause)

**A Pentax build MUST be built with our fork mounted as source input, or it
silently ships vanilla libgphoto2.** This is the exact failure behind the 2026-09-07/08
incident: `out/k1ii-k3iii-fixed-v3` was built *without* `--libgphoto2-source`, so
`container/build_ptp2.sh` fell through to its last branch — downloading the vanilla
`gphoto/libgphoto2` 2.5.34 release tarball from GitHub. The result: a `ptp2.so` with
**none** of our Pentax vendor-mode / stale-session code, which is why both the K-1 II
and K-3 III fell into the `gp_camera_get_single_config … failed: -2` loop on-device.

The correct invocation (see `patch-polaris.sh`):

```bash
bash patch-polaris.sh \
  --fwpkt firmware/FwPkt.zip \
  --libgphoto2-source /home/ian/Documents/VSCodeProjects/LibGphoto2/libgphoto2 \
  --allow-dirty-source \
  --out <absolute-path>          # docker -v needs an absolute path
```

Three guards make this safe and verifiable:
1. **Full mode fails closed without `--libgphoto2-source`.** The conspicuous
   `--allow-vanilla-source` escape hatch is only for intentional stock builds;
   provenance then records `vanilla_source_explicit=1`. It must not be used for
   a Pentax candidate.
2. **The build log must print** `[build] using mounted local source` (not the vanilla
   `wget` path) and `[patcher] local-source Pentax candidate marker: present`.
3. **Post-build, verify the fork markers are actually in the shipped `ptp2.so`:**

   ```bash
   PTP=$(find <out>/stage2-ondisk -name ptp2.so | head -1)
   for s in "pentax_identify_supported_model" "stale Pentax session" \
            "K-1 Mark II" "observing camera state" "Pentax vendor mode enabled"; do
     strings "$PTP" | grep -qF "$s" && echo "OK  $s" || echo "MISSING  $s"
   done
   ```

   A correct fork build's `ptp2.so` is ~927 KB and has all markers present; a vanilla
   build is ~877 KB and has none. If any marker is missing, the build picked up stock
   libgphoto2 — do not stage it. Record the resulting row in this registry with the
   real `git_commit` (read from `<out>/build-source-provenance.txt`).

## Open follow-ups (do not block on these)
- [ ] **Stage v4** (`o-v4`, zip md5 `d0674ef6…`) on the SD card and re-test K-1 II /
      K-3 III — this is the first build with the real Pentax fork in `ptp2.so`.
- [ ] Backfill blank `git_commit` fields in `out/k1ii-k3iii-fixed*` provenance files
      (v3 + fixed were vanilla; v4 has it filled).
- [x] Private GitHub location for zip bytes now exists:
      `ian-morgan99/PrivateResearch/firmware-packets/<registry-id>/` (see the
      `fwpkt-private-upload` skill). New rows record their location there;
      pre-existing rows keep their local/`smb:`/`sd:` references until
      backfilled.
