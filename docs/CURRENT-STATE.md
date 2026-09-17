# Current repository state

This is the concise entry point for agents and maintainers. Read it before
searching historical handovers or raw evidence.

## Protected firmware baseline

The protected last-known-stable baseline is **o-v9p capture isolation**, build
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
- `RUN-JOURNAL.md`
- `TESTED.md`
- `LIBGPHOTO2-UPGRADE-PROCESS.md`

## Repository state at context cleanup

On 2026-09-17, `main` was synchronized with `origin/main` at `5309bfd`, with
three pre-existing uncommitted files deliberately left untouched:

- `container/patch.sh`
- `container/test_polaris_pentax_build_package.sh`
- `docs/FWPKT-PROVENANCE-CONTRACT.md`

Those edits appeared to revert the post-#74 FwVer behavior, remove a packaged
preview-throttle assertion, and remove the o-v9o/o-v9p registry rows. They are
not part of this context cleanup and must be resolved separately without
weakening o-v9p or deleting provenance.

No newer source change is considered deployed without a registered immutable
FwPkt, verified hashes, supported install, cold reboot and post-boot runtime
proof. In particular, local Bulb-related work observed on 2026-09-17 had no
new registry row or install evidence.

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
`8deab7e` (historical session state).

The archive contains both a commit-exact documentation tarball and a working-
tree tarball, per-file SHA-256 manifests and the pre-cleanup worktree patch.
See `ARCHIVED-EVIDENCE.md` for the public retention policy.
