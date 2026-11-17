---
name: fwpkt-private-upload
description: Legacy private-upload skill — now a concise routing guide that delegates to polaris-release-orchestrator's PRIVATE_PUBLISHED phase. Uploads FwPkt.zip only; does not treat FwPkt-only upload as a sufficient release definition. Companion archives, docs, and remote verification are handled by the orchestrator and artifact-auditor skills.
---

# FwPkt private upload — routing guide (delegates to polaris-release-orchestrator)

This skill is a **concise routing guide**. It uploads `FwPkt.zip` to the private
`ian-morgan99/PrivateResearch` repo. It does **not** treat an FwPkt-only upload
as a sufficient release definition — a release requires FwPkt + all companion
archives + docs + remote verification, per the
`polaris-release-orchestrator` skill.

## When to use

Use this skill to upload a firmware ZIP after a build produces
`out/<name>/FwPkt.zip`. It is one phase (`PRIVATE_PUBLISHED`) of the
orchestrator lifecycle, not the whole release.

## Canonical command

```bash
bash .github/skills/fwpkt-private-upload/scripts/upload-fwpkt-to-pr.sh \
  --build out/<name>-<date> \
  --id <registry-id> \
  --status candidate \
  --note "<one line: what this build changes>"
```

## What this skill does NOT do

- Does **not** publish companion archives (`polaris-astro.zip`,
  `polaris-wifi.zip`, `astrometry-indexes.zip`) — that is
  `scripts/publish-astro-candidate.sh`, driven by the orchestrator.
- Does **not** generate `INSTALL.md` or `CHANGELOG.md` — that is
  `polaris-release-documentation`.
- Does **not** verify the remote entry — that is
  `polaris-release-artifact-auditor`.
- Does **not** stage the zip to the SD card — that is `fwpkt-update-flow`
  (device installation only).
- Does **not** treat "FwPkt uploaded" as "release complete."

## The flow (run this after every successful build)

The script does, in order (all fail-closed):

1. **Recomputes** zip MD5 + SHA-256 from the actual file — never copied from a
   doc or a previous row.
2. **Gate 1 (structural):** `container/validate_fw_package.py` on the zip
   (layout, required files, duplicates, stock-component drift).
3. **Gate 2 (manifest):** re-extracts the zip and re-MD5s every
   `firmwareInfo` entry against the shipped bytes — the same check the on-board
   updater runs. A mismatch here means the device would silently reject it.
4. Stages `FwPkt.zip` + a self-describing `README.md` (all four handoff values)
   + `build-source-provenance.txt` into
   `$PR_CHECKOUT/firmware-packets/<display-version>--<id>/` and commits + pushes to
   `ian-morgan99/PrivateResearch`.
5. Prints a **paste-ready registry row** for
   `docs/FWPKT-PROVENANCE-CONTRACT.md`.

Then, in the same session:

6. **Paste the printed row into `docs/FWPKT-PROVENANCE-CONTRACT.md`** and set
   its `path / location` to
   `` `firmware-packets/<display-version>--<id>/FwPkt.zip` (ian-morgan99/PrivateResearch, private) ``.
   Commit that doc change in the patcher repo. The registry row is the public
   pointer; the bytes stay private.

## Authentication

- With `GH_TOKEN` set (a token with write access to PrivateResearch), the push
  goes through a token-embedded URL so the token never lands in `.git/config`.
- Without it, the script uses the configured git credential helper — fine when
  you are already logged in on this box. If the push prompts or fails, set
  `GH_TOKEN` and retry; do not commit the zip to a public repo as a fallback.

## Layout contract (do not change without updating this skill)

```
ian-morgan99/PrivateResearch/
└── firmware-packets/
    └── <display-version>--<registry-id>/   # e.g. 6.0.0.54.68--o-v17c-colortemp-formless
        ├── FwPkt.zip            # the flashable package (FwPkt/ prefix intact)
        ├── README.md            # all four handoff values + verify commands
        └── build-source-provenance.txt   # if the build produced one
```

- **Folder naming.** The prefix is the five-component `display_fwver` — the
  version the Benro Connect app actually shows — because that is the only
  identifier visible on the phone. The registry id is kept as the suffix
  because display versions are **not unique**: nine were issued more than once
  (the #169 duplicate-version failure in `docs/RELEASE-VERSION-STATE.md`), so
  a version alone cannot identify a packet. `upload-fwpkt-to-pr.sh` reads the
  version from the build's own `build-source-provenance.txt` and **fails
  closed** if it is absent or malformed — never publish under a guessed
  version. Use `--display-fwver 6.0.0.54.N` only for a build that predates
  that field.
- One folder per registry id, **never** overwrite an existing folder's zip.
  A new build gets a new id (o-v9, o-v10, …). If you must re-upload the same
  id with different bytes, that is a *new* row in the registry — bump the id.
- The `FwPkt/` top-level prefix inside the zip is part of the on-board
  contract (see `docs/fwpkt-zip-layout-and-smb-delivery.md` §1). Never strip it.

## Receiving side (other agents)

To fetch a build:

```bash
git clone --depth 1 https://github.com/ian-morgan99/PrivateResearch.git
cd PrivateResearch/firmware-packets/<display-version>--<id>
md5sum FwPkt.zip        # == registry "zip MD5"
sha256sum FwPkt.zip     # == registry "zip SHA-256"
unzip -p FwPkt.zip FwPkt/firmwareInfo | grep '^appfs'   # appfs MD5 == registry
```

All three must match the registry row before the zip is staged on a device
(provenance gate in the `fwpkt-update-flow` skill). A zip whose hashes match no
registry row is *unprovenanced* — do not stage it.

## Things that are NOT allowed

1. **Committing `FwPkt.zip` (or any `*.ubifs`, `*.bin`, `firmwareInfo`) to a
   public repo.** The bytes go to PrivateResearch; only the row goes public.
2. **Uploading before both gates pass.** A structurally broken or
   manifest-stale zip on the private repo is worse than none — other agents
   will trust it because it is "the one in the registry".
3. **Copying hashes forward** from a doc, a chat message, or an old row.
   Always recompute from the file you are actually uploading.
4. **Overwriting `firmware-packets/<display-version>--<id>/FwPkt.zip`** with different bytes.
   Same id = same bytes, forever.
5. **Skipping the registry row because "it's only in the private repo".**
   The row lives in the public patcher repo; that is what makes the private
   bytes discoverable and verifiable.

## Backfilling existing builds

For zips already sitting in `out/` or `builds/` that were never uploaded, run
the same script with their registry id (look it up in
`docs/FWPKT-PROVENANCE-CONTRACT.md`) and update the row's location column to
point at PrivateResearch. Use `--dry-run` first to see what would be staged.
