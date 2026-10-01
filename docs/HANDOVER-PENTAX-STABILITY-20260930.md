# Pentax stability handover — resumed 2026-09-30

**Firmware remains PHYSICAL FAIL / NOT RELEASE-QUALIFIED.** Safe orphan-output
recovery is not implemented. The immediate physical prerequisite is attaching
the affected K-3 III directly to the PC, with no exposure running and camera
apps closed. No new shutter, candidate deletion, firmware build or installation
was performed in this resumption.

## One delivery line per owning repository

Continue in the canonical `main` checkouts:

- Patcher: `/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher`.
- Library: `/home/ian/Documents/VSCodeProjects/LibGphoto2/libgphoto2`,
  `df64a63300585dbd8642861d760668b1ace92f78`.
- App: `/home/ian/Documents/VSCodeProjects/OpenPolaris`,
  `5345e5e173fc8f057404d80d1ff394e5009821c9`.

The old parent `LibGphoto2` Git checkout was a NINA/research repository and must
not be used as a library build source. Its research files remain in place.
[Workspace convergence](WORKSPACE-CONVERGENCE-20260930.md) identifies every old
branch, its disposition, preserved worktree/dirty-state hashes and recovery
location in PrivateResearch. Temporary branches from this investigation are
integrated into main, and exact-SHA binaries are test fixtures rather than
additional active source trees. Final local/remote identities and inventory are
in `docs/evidence/workspace-convergence-20260930/`.

## Resolved source question; unresolved runtime fix

The complete IMAGE Transmitter 2 candidate path establishes:

- +32 = transfer candidate available, not exposure active;
- +36 = selector; value 1 is a new-transfer sentinel, not a durable image ID;
- +104 includes separate shooting and processing bits;
- IT2 inspects/transfers available output without needing a new shutter, then
  closes/publishes the file before releasing its candidate.

Both exact built camlibs, installed-lineage `fbc2e7e65` and current `df64a6330`,
mislabel synthetic conditions matching the recorded `+32=1,+36=1,+104=0` as
`capture-active`, while their session reconciler calls it a stale candidate.
That diagnostic conflict is demonstrated in production classifier functions.
It is not proof that the physical camera is idle or that the candidate belongs
to any particular request. Keep strict admission and candidate preservation.

[Source audit and exact tests](evidence/pentax-orphan-recovery-20260930/SUMMARY.md)
record the IT2 anchors, actual module hashes, durability gap, and implementation
acceptance cases. Reusing the current transfer helper alone is insufficient:
it can release a candidate after publication to process-local RAM, before a
surviving Polaris SD file is confirmed.

## Preserve the separate incidents

1. The [14:43 crash](evidence/pentax-shutter-crash-20260930-1443/SUMMARY.md)
   snapshot identifies **o-v13x / 6.0.0.54.43**. InitiateCapture returned
   0x2001, then pgphoto crashed without output/publication. This is acceptance,
   not completion; the crash-time maps/registers were unavailable.
2. The [16:00–16:04 refusals](evidence/pentax-busy-after-sd-recovery-20260930-1604/ASSESSMENT.md)
   were on **o-v15a / 6.0.0.54.44**. Four requests were blocked before initiation;
   SD capacity recovered independently. No requested SP_0151–SP_0154 output was
   published. The 17:35 UTC #149 review marks v15a physically failed.
3. The [post-reboot busy report](evidence/pentax-after-dual-reboot-busy-20260930/ASSESSMENT.md)
   lacks a matching retained code-264 request; do not assert it reached pgphoto.
4. Camera playback image `484-3701` was taken through Benro Connect; actor,
   request ownership, publication mapping and relation to selector 1 are unknown.
5. SP labels recur across sessions. Correlate original log, timestamp, pgphoto
   PID/generation and camera identity; never join events by SP label alone.

## Exact resume sequence

1. Read #149 and #145 latest reviews plus the audit above. Use repository skills
   and the libgphoto2 source/runtime ownership contract.
2. After operative confirmation, verify fresh PC USB `25fb:0189`. Use the frozen
   installed-source prefix at `LibGphoto2/libgphoto2/_baselines/`
   `fbc2e7e6544efc93cc708a1e7d2fdf2b2bf7c7cd/prefix`, with matched core/port,
   CAMLIBS/IOLIBS and loader proof. Begin with a bounded conditions-only read,
   capturing the complete debug response. Do not trigger a new exposure.
3. If the USB move cleared the state, record NOT REPRODUCED. Do not manufacture
   an orphan through a destructive disconnect. A direct source-boundary
   reproducer is required before changing library recovery behavior.
4. Implement #145's two cases: active/unknown operation stays blocked; recoverable
   orphan is inspected, transferred and durably published, retaining its camera
   candidate until exact publication acknowledgement. Associate an original
   request only with evidence; otherwise report recovered/orphan, never the
   newly refused shot. Add production-path owner-loss and failure tests first.
5. Only after that, use clean committed sources, the canonical release script,
   immutable provenance/private upload, package gate, supported install and
   physical regression matrix. Do not repackage unchanged behavior as a fix.

## Remaining dependencies and qualification

- #146: transport generation is distinct from mode/config epoch. M↔B refreshes
  config; true USB replacement requires identity-driven rebind. Preserve mount
  alignment/tracking across camera recovery.
- #148: requested duration, pre-delay, exposure, processing and API completion
  remain separate. Exact seconds/fractions must display correctly; locate
  editable client source instead of changing firmware to compensate for UI.
- #147 / OpenPolaris #94: sustained flicker was specifically associated with
  OpenPolaris + Benro Connect. App-side fixes already exist on application main;
  the physical A/B and sequence workload ownership remain owed.
- #160/#155: no generic -110 retry. A controlled ordinary 3-shot M RAW+JPEG run
  follows recovered single-shot ownership; Astro, panorama, Pixel Shift and
  other formats need separate qualification.
- Canon R5 II, Pentax K-3 III and K-1 II regression requirements remain in force.

Offline patcher gate: 16 container + 25 Python PASS, two nested prerequisite
skips. Both exact-source library deterministic suites: 14/14 PASS with the
hardware-dependent `no-ci` suite excluded. The initial unrestricted library run
failed that fixture-dependent test; see the audit. These checks do not qualify
or fix the hardware.
