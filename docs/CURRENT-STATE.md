# Current repository state

This is the concise entry point for agents and maintainers. Read it before
searching historical handovers or raw evidence.

## Installed candidate and protected fallback

As of 2026-09-23 the device has **o-v12m-observed-lifecycle**, build ID
`6.0.0.54.23-o-v12m-observed-lifecycle`, installed. It is a **failed diagnostic
build, not release-qualified**. It fixed o-v12j/o-v12k's pre-Initiate crash:
the first RAW+JPEG Pixel Shift capture returned success and published primary
`IMGP3592.JPG`. Benro then saw two filesystem entries and SIGSEGV'd in
`gp_filesystem_get_file` because the newly published companion buffer had been
freed after ownership transferred to `CameraFile`. No second shutter was sent.
Do not send another shutter on o-v12m. See
`HANDOVER-2026-09-23-O-V12M-COMPANION-UAF.md`.

The immutable **o-v12l-recoverybaseline-20260923** artifact preserves
libgphoto2 `c0592d178`, the last source with physical first-capture Pixel Shift
RAW+JPEG completion evidence. It is privately published and registered but is
not installed and is not a final fix: its delayed companion/repeated-capture
behavior was not qualified.

The next source candidate is libgphoto2 `ab0de090c` on
`rescue/final-shutter-20260923`. It reconstructs the output lifecycle from
IMAGE Transmitter 2, observes RAW+JPEG mode and candidate ownership after the
capture, removes destructive pre-capture draining, and checks candidate handle
`+36` during recovery. It also clears the companion transfer pointer after
`gp_file_set_data_and_size()` takes ownership, fixing the live o-v12m
use-after-free. Source tests/build pass. The immutable
`o-v12m-observed-lifecycle-20260923` FwPkt is privately published and
registered, but is not yet installed and has no physical result.
The historical ledger and promotion matrix are in
`PENTAX-CAPTURE-VERSION-LEDGER-2026-09-23.md`.

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
