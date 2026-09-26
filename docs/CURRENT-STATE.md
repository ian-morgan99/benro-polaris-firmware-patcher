# Current repository state

This is the concise entry point for agents and maintainers. Read it before
searching historical handovers or raw evidence.

## 2026-09-25 convergence candidate

`o-v13c-boundary-trace-20260925` is the current **INSTALLED, RUNTIME-VERIFIED,
K-3 III TWO-SHOT CANARY PASS** candidate. It embeds libgphoto2 `4868d3649`,
patcher build `8b075f5`, and harness contract `a8b6581`; artifact bytes are
privately published at PrivateResearch `d92b1d094`. The sanctioned install
verified all six staged manifest entries before reboot; post-boot FwVer,
matched-stack hashes, loader maps and embedded provenance match the registry.

One RAW+JPEG canary and the corrected same-session two-shot gate passed. The
two shots each reported `[1,4,0]` and distinct same-stem DNG+JPEG pairs
(`SP_0086`, `SP_0087`) with no reconnect. The second shutter was not issued
until the first exposure completed, both output obligations were published,
and idle was observed. Exact transcript and remaining qualification limits are
in `evidence/o-v13c-boundary-trace-20260925/SUMMARY.md`.

The preceding o-v13 artifact was installed and failed two bounded first-shot
canaries: preview stopped and code 264 was accepted, but no shutter/completion/
773 followed and the session ended at `state:-10`. Runtime logs proved that
artifact still interposed the unsafe Stage-2 capture shim and never reached the
libgphoto2 admission trace. It is superseded; no second shutter was sent.

The minimum repeated ordinary-shutter acceptance question is now answered for
the attached K-3 III RAW+JPEG mode. Remaining physical qualification is scoped
to cancellation, Live View interaction, external mode/config changes, other
bodies/modes and soak; do not generalise this bounded pass to those paths.

A subsequent bounded Preview/Astro-equivalent check also passed: Preview was
started, suspended for three consecutive RAW+JPEG captures (`SP_0097` through
`SP_0099`, all `[1,4,0]`), then restored and confirmed ON. This qualifies the
Benro control-plane suspend/capture/restore transition, not sustained preview
JPEG delivery or the native OpenPolaris Astro UI.

## Installed candidate and protected fallback

As of 2026-09-24 the device has **o-v12n-companion-ownership**, build ID
`6.0.0.54.23-o-v12n-companion-ownership`, installed. It is a diagnostic
candidate, **not release-qualified**. Runtime provenance is libgphoto2
`ab0de090c` plus patcher `7bcbc39`; the registered artifact hashes are in
`FWPKT-PROVENANCE-CONTRACT.md`.

One K-3 III RAW-only first-shot canary completed with lifecycle `[1,4,0]` and
published `SP_0074.dng` (32,900,659 bytes). This proves only that one
single-output capture can complete. The same-session repeat-capture gate did
not pass: one run completed shot 1 (`SP_0078.dng`) and then lost the camera
before shot 2 was issued; a later run did not complete shot 1 and reported
`state:-10`. Do not describe o-v12n as fixing repeated capture.

The currently attached body is K-01 (`25fb:0131`). The normal product path
initializes it successfully as `pentax/k-01/state:1`; one still request
returned `-6` immediately, consistent with that separately gated model not
advertising capture support. This disproves the standalone Stage-2 CLI claim
that the package has zero supported cameras, but it does not qualify K-01 still
capture and says nothing about K-1 II. K-1 II remains **NOT TESTED** on o-v12n.

The immutable **o-v12l-recoverybaseline-20260923** artifact preserves
libgphoto2 `c0592d178`, the last source with physical first-capture Pixel Shift
RAW+JPEG completion evidence. It is privately published and registered but is
not installed and is not a final fix: its delayed companion/repeated-capture
behavior was not qualified.

The current review head is libgphoto2 `62402cc2c` on
`rescue/final-shutter-20260923`. It retains the o-v12n runtime behavior and
replaces the self-fulfilling ownership mock with a production helper used by
the real companion-publication callback. Focused Pentax tests and `ptp2.so`
compile pass. This is a source/test correction only; it does not justify a new
FwPkt until the o-v12n repeat-capture failure is understood.

## Pre-upgrade baseline (2026-09-25)

Before the 2026-09-25 upgrade work, **o-v12s-preupgrade-20260925** was built
and registered as the rollback reference: libgphoto2 `50ba504` (latest fork
head, clean checkout) + patcher main `1c1d386`, build id
`6.0.0.54.26-o-v12s-preupgrade`, pre-release gate green (4/4). It is privately
published and registered in `FWPKT-PROVENANCE-CONTRACT.md`. The earlier
attempts o-v12q and o-v12r are superseded by it (see the registry addendum).
The historical ledger and promotion matrix are in
`PENTAX-CAPTURE-VERSION-LEDGER-2026-09-23.md`.
The current audit and next-action boundary are in
`HANDOVER-2026-09-24-O-V12N-AUDIT.md`.

The protected last broadly repeated-capture baseline is **o-v9p capture isolation**, build
ID `6.0.0.54.7`. Its immutable artifact, hashes, source commits and private
location are recorded in `FWPKT-PROVENANCE-CONTRACT.md`.

Recorded K-3 III qualification passed ordinary capture, five unique
Astro-equivalent DNG captures, preview restoration with 15/15 complete JPEGs,
a final DNG, stable processes/listeners/USB and bounded DHD counters. Preserve
its separate preview and still-capture cooldowns and the package assertions
which prove the preview-throttle exports reached the final appfs.

This does **not** prove that physical focus direction, K-1 II, Canon R5 Mark II,
the packaged OpenPolaris GUI, indefinite soak, or the underlying Broadcom
driver exhaustion are fixed. Those remain open or unqualified.

Authoritative public evidence:

- `FWPKT-PROVENANCE-CONTRACT.md`
- `evidence/o-v9p-capture-isolation-2026-09-16/SUMMARY.md`
- `evidence/o-v9q-bulb-timeout-2026-09-17/SUMMARY.md`
- `TESTED.md`
- `LIBGPHOTO2-UPGRADE-PROCESS.md`

## Repository state at issue #116 cleanup

On 2026-09-18, source commit `2b56e8d` recorded the Q build-id behavior. The
issue #116 hygiene pass restored the final-package assertions for P's preview
throttling and the isolated output mount used by the package regression test.
The unrelated `.vscode/settings.json` worktree edit was deliberately untouched.

No future source change is considered deployed without a registered immutable
FwPkt, verified hashes, supported install, cold reboot and post-boot runtime
proof.

## Hardware and release rules

- Read `.github/skills/polaris-debugging/SKILL.md` before live-device work.
- Use `.github/skills/fwpkt-update-flow/SKILL.md` for every firmware install.
- Do not replace binaries directly under `/app` as a supported fix.
- Keep direct libgphoto2, Polaris runtime and OpenPolaris E2E evidence separate.
- A protocol acknowledgement is not physical focus or capture proof.
- If required hardware is unavailable, report `NOT TESTED` or `BLOCKED`.

## Focused stability programme

The active experiment design is intentionally small:

- `pentax-capture-stability-experiments.md`
- `pentax-capture-stability-experiments.schema.json`
- `pentax-physical-operative-runbook.md`
- `pentax-agent-operative-prompts.md`
- `pentax-k1ii-second-pass.md`
- `pentax-mode-aware-liveness.md`
- `../tests/README-pentax-stability.md`

The former 154-file `pentax-stability-*` planning package was preserved in the
private archive and removed from the active tree because it duplicated these
rules across many tiny, often superseded documents.

## Archived material

Raw logs, firmware-derived binaries, the fragmented stability package and the
local LM Studio review ledger were preserved before cleanup in the private
`ian-morgan99/PrivateResearch` repository:

`archives/BenroPolarisPatcher/2026-09-17-pre-context-cleanup/`

PrivateResearch archive commits: `a3dc491` (documentation and ledger) and
`8deab7e` (historical session state). Issue #116's second-stage research and
raw-evidence corpus is preserved at
`BenroPolaris/repository-hygiene-116/2026-09-18/original/`, commit `a6afa37`.

The archive contains both a commit-exact documentation tarball and a working-
tree tarball, per-file SHA-256 manifests and the pre-cleanup worktree patch.
See `ARCHIVED-EVIDENCE.md` for the public retention policy.
