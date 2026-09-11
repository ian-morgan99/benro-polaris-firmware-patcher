---
name: fwpkt-private-upload
description: Publish every newly built FwPkt.zip to the PRIVATE ian-morgan99/PrivateResearch repo (firmware-packets/<registry-id>/) so other agents can fetch it online, while keeping the public repos free of firmware bytes. USE FOR: right after any patch-polaris.sh build produces out/<name>/FwPkt.zip; when another agent or machine needs a zip that only exists on this box; backfilling an existing out/ or builds/ zip that was never uploaded. DO NOT USE FOR: staging the zip onto the SD card (fwpkt-update-flow skill), building the zip itself (container/ + patch-polaris.sh), or committing zip bytes to any PUBLIC repo.
---

# FwPkt private upload — HARD RULE

> **HARD RULE.** Every `FwPkt.zip` this project produces is uploaded to the
> **private** `ian-morgan99/PrivateResearch` repo under
> `firmware-packets/<registry-id>/` **in the same session it is built**, before
> the build is handed off, installed, or discussed. The public repos
> (`BenroPolarisPatcher`, `OpenPolaris`, the libgphoto2 fork) keep only the
> registry *row* (hashes + commit links); the zip *bytes* live in
> PrivateResearch. This is the `zip_location` column the provenance contract
> reserved — it now exists, and it is this repo.

## Why this rule exists

- Zips are ~66 MB of firmware-derived bytes; the public repos' `.gitignore`
  says "NEVER commit firmware or firmware-derived blobs".
- A zip that only exists in one agent's `out/` directory is invisible to every
  other agent and machine. The 2026-09-07/08 v3 incident was exactly this: a
  hand-zipped tree whose outer hash matched no registry entry, so nobody could
  say "the zip on the card is build X".
- PrivateResearch is private (not public), so publishing there does not leak
  firmware bytes to the world — but it *is* online and cloneable by any agent
  with access, which is the point.

## The flow (run this after every successful build)

```bash
cd /home/ian/Documents/VSCodeProjects/BenroPolarisPatcher
bash .github/skills/fwpkt-private-upload/scripts/upload-fwpkt-to-pr.sh \
  --build out/<name>-<date> \
  --id <registry-id> \
  --status candidate \
  --note "<one line: what this build changes>"
```

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
   `$PR_CHECKOUT/firmware-packets/<id>/` and commits + pushes to
   `ian-morgan99/PrivateResearch`.
5. Prints a **paste-ready registry row** for
   `docs/FWPKT-PROVENANCE-CONTRACT.md`.

Then, in the same session:

6. **Paste the printed row into `docs/FWPKT-PROVENANCE-CONTRACT.md`** and set
   its `path / location` to
   `` `firmware-packets/<id>/FwPkt.zip` (ian-morgan99/PrivateResearch, private) ``.
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
    └── <registry-id>/            # e.g. o-v8 — MUST equal the registry id
        ├── FwPkt.zip            # the flashable package (FwPkt/ prefix intact)
        ├── README.md            # all four handoff values + verify commands
        └── build-source-provenance.txt   # if the build produced one
```

- One folder per registry id, **never** overwrite an existing folder's zip.
  A new build gets a new id (o-v9, o-v10, …). If you must re-upload the same
  id with different bytes, that is a *new* row in the registry — bump the id.
- The `FwPkt/` top-level prefix inside the zip is part of the on-board
  contract (see `docs/fwpkt-zip-layout-and-smb-delivery.md` §1). Never strip it.

## Receiving side (other agents)

To fetch a build:

```bash
git clone --depth 1 https://github.com/ian-morgan99/PrivateResearch.git
cd PrivateResearch/firmware-packets/<id>
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
4. **Overwriting `firmware-packets/<id>/FwPkt.zip`** with different bytes.
   Same id = same bytes, forever.
5. **Skipping the registry row because "it's only in the private repo".**
   The row lives in the public patcher repo; that is what makes the private
   bytes discoverable and verifiable.

## Backfilling existing builds

For zips already sitting in `out/` or `builds/` that were never uploaded, run
the same script with their registry id (look it up in
`docs/FWPKT-PROVENANCE-CONTRACT.md`) and update the row's location column to
point at PrivateResearch. Use `--dry-run` first to see what would be staged.
