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
| o-v3 | `out/k1ii-k3iii-fixed-v3/` (tree; **no canonical zip in repo**) | SD-zip: `5491835a…d5518018` | — | `d220682e…c4927da0620efa5` | release 2.5.34 (commit field blank in provenance) | patcher ~`f3dbff4`+`9e47a34` era (iolibs + post-repack assertion) | **v3 — installed on device** | Zipped by an agent session outside `patch.sh`; outer hash never recorded. Payload verified = v3 tree. Installed Sep 7 22:15 UTC. |

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

## Open follow-ups (do not block on these)
- [ ] Backfill blank `git_commit` fields in `out/k1ii-k3iii-fixed*` provenance files (v3 + fixed).
- [ ] Promote v3 to a canonical `builds/<date>-k1ii-k3iii-v3/FwPkt.zip` via `container/patch.sh` so it has a repo-tracked zip, then add its exact outer hash as a new row.
- [ ] Optional: create a private GitHub (or SMB-pinned) location for zip bytes; add a `zip_location` column when it exists.
