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
   is committed to a repo. If a private zip-repo is created later, add its URL as
   a `zip_location` column; until then `zip_location` is a local path or `smb:`/`sd:` reference.
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

Two guards make this safe and verifiable:
1. **The build log must print** `[build] using mounted local source` (not the vanilla
   `wget` path) and `[patcher] local-source Pentax candidate marker: present`.
2. **Post-build, verify the fork markers are actually in the shipped `ptp2.so`:**

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
- [ ] Optional: create a private GitHub (or SMB-pinned) location for zip bytes; add a
      `zip_location` column when it exists.
