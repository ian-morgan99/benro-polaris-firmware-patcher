# Release identity and handoff process

**Status: binding.** Every agent must use this process for a Polaris firmware
candidate. It exists to make the following questions answerable without guesswork:

1. What source produced the bytes?
2. Which exact artifact was built, and where is it now?
3. What does that artifact contain?
4. Was it only built, or was it gated, published, staged, installed, runtime-
   verified, or physically qualified?

The version shown by Benro Connect is only one field in the record. It is never
an artifact identity by itself.

## The authoritative documents

Use the documents for these separate purposes:

| Question | Authority |
|---|---|
| Which display versions are reserved or consumed? | [`RELEASE-VERSION-STATE.md`](RELEASE-VERSION-STATE.md) |
| Which bytes and source commits belong to an artifact? | [`FWPKT-PROVENANCE-CONTRACT.md`](FWPKT-PROVENANCE-CONTRACT.md) |
| Which lifecycle state has been proved? | This document and the candidate evidence record |
| How may it be installed? | [`FIRMWARE-INSTALL-PROCESS.md`](FIRMWARE-INSTALL-PROCESS.md) |
| What was actually running on the device? | [`CURRENT-STATE.md`](CURRENT-STATE.md) plus dated install evidence |

If two records disagree, stop. Do not resolve the disagreement from a filename,
an app display, or memory. Reconcile the hashes and exact commits first.

## Required identity tuple

Every candidate record must carry all of these values:

```text
candidate_id=                       # immutable human-readable build id
display_fwver=                      # exact five-component app-visible version
libgphoto2_commit=                  # full 40-character SHA
patcher_commit=                     # full 40-character SHA
stock_fwpkt_sha256=                 # exact input firmware package
libgphoto2_dirty_diff_hash=         # empty only for a clean source tree
patcher_dirty_diff_hash=            # empty only for a clean source tree
fwpkt_zip_path=                     # current local or durable repository path
fwpkt_zip_sha256=                   # full SHA-256
fwpkt_zip_md5=                      # full MD5, for firmwareInfo-era checks
appfs_md5=                          # value recorded in firmwareInfo
install_manifest_path=              # required for a deployable candidate
release_change_manifest_path=       # generated exact change/commit record
release_change_manifest_sha256=     # exact hash of the generated change record
```

The source commits, the ZIP hash, and the manifest must describe the same
candidate. A display version or a directory name cannot substitute for any of
them.

## Lifecycle states

`BUILT` and `GATED` describe the evidence available at each point; they do not
make an artifact unpublishable. Every gated candidate must be published so
independent testers can fetch the exact bytes and so the project retains a
complete test history. The states remain separate because publication does not
prove deployment, runtime identity, or camera behaviour.

Use these exact words. A later state does not follow merely because an earlier
command appeared to succeed.

| State | Minimum evidence | Wording allowed | Wording forbidden |
|---|---|---|---|
| `BUILT` | `FwPkt/`, ZIP, provenance, source SHAs | “built” | “installed”, “deployed” |
| `GATED` | pre-release gate transcript and current install manifest | “offline-gated candidate” | “hardware-tested” |
| `PUBLISHED` | durable PrivateResearch path and matching ZIP hash | “published at …” | “installed” |
| `STAGED` | supported installer log showing `/app/sd/FwPkt/` and on-device MD5 checks | “staged” | “flashed”, “running” |
| `INSTALLED-VERIFIED` | installer phase 6, uptime reset, exact on-device provenance and all manifest hashes | “installed and runtime-verified” | “camera-qualified” |
| `PHYSICALLY-QUALIFIED` | dated hardware evidence against the exact installed identity | “qualified for the recorded matrix” | “all cameras supported” unless the matrix proves it |
| `SUPERSEDED` | later identity record and retained rollback location | “superseded by …” | “deleted” unless deletion is separately recorded |
| `REJECTED` | recorded reason and retained artifact/hash | “rejected; do not stage” | “failed build” unless the failing gate is named |

`DEPLOYED` is not a sufficient state word. Say whether the package was staged,
installed-verified, or physically qualified. A published `BUILT`/`GATED`
artifact may be handed to an independent tester, but its publication record
must retain the fact that installation and camera qualification are pending.

## Canonical workflow

### 1. Select immutable inputs

Record the full libgphoto2 SHA, the full patcher SHA, and the stock `FwPkt`
SHA-256 before building. The source checkouts must be clean. A dirty source
tree is either rejected or recorded with its exact dirty-diff hash and is not a
release input.

Use the canonical builder:

```sh
./scripts/build-release-candidate.sh \
  <candidate-id> <stock-FwPkt.zip-or-dir> \
  <clean-libgphoto2-checkout> <build-id> <display-fwver> \
  --change-summary <release-change-summary.json>
```

The change summary is mandatory. Use
`docs/templates/release-change-summary.json`. It is the only human-authored
release description: it names the purpose, declared fixes, issue references,
validation focus, known limits, and the previous candidate's full source
SHAs. The builder checks that both baselines are ancestors of the current
`main` commits, calculates every commit in both ranges, and writes these
machine-checked files into the candidate directory:

```text
release-change-manifest.json   exact JSON identity, change list, and commit inventories
RELEASE-IDENTITY.md            readable copy for reviewers and testers
```

The verifier checks that the generated record's candidate ID, display version,
build ID, source SHAs, patcher SHA, ZIP SHA-256, and ZIP MD5 agree with the
candidate. The private uploader refuses to publish without both files. This is
the release-process guard against another `.74`/`.75`/`.76`/`.77`/`.84` record
whose version number was clear but whose fixes and commits were not.

Do not assemble a release by manually running `patch-polaris.sh`, copying a
camlib, or repacking a ZIP. Those actions can create a useful diagnostic
artifact, but they produce a `BUILT`/smoke artifact until rebuilt through the
canonical flow.

### 2. Verify the candidate before handoff

Before deployment, the build directory must contain all of the following:

```text
FwPkt/
FwPkt.zip
build-source-provenance.txt
install-manifest.json
```

After the deployment attempt, it must also contain `build-release-candidate.log`
and `install.log`; a successful deployment additionally produces
`install-receipt.txt`.

The pre-release gate must pass against that exact directory. The ZIP hash in
`install-manifest.json` must match the ZIP on disk. The `FwPkt/FwVer` contents
must match `display_fwver` in the provenance. A missing manifest means
**not deployable**, even if the ZIP opens and the package looks complete.

The machine check is:

```sh
python3 scripts/verify-candidate-identity.py \
  out/<candidate-id> --require-deployable
```

Both `scripts/build-release-candidate.sh` and
`scripts/release/release-fwpkt.sh` run this check automatically. A failed check
stops the process before version publication, staging, reboot, or flash.

Record the version reservation in `RELEASE-VERSION-STATE.md`; a smoke or failed
deployment still consumes a version number and must never be silently rebuilt
under that number. The normal builder creates the durable provenance row after
the offline gate and before attempting deployment, so every candidate has a
published test record. A later deployment attempt updates that same published
record with its installer log and receipt.

### 3. Publish and identify the durable artifact

The canonical builder uploads the exact ZIP after the offline gates and before
the deployment attempt. The initial published status is `gated` (or
`candidate` in a manually maintained legacy row), which means it is available
to independent testers but is not yet proved installed on this particular
Polaris. If the target is unavailable, busy, or verification fails, the
published artifact remains valid test history and the logs record the failed
deployment attempt.

When deployment succeeds, the installer writes:

```text
build-source-provenance.txt  install_status=installed-verified
install-receipt.txt          target, device FwVer, ZIP hash, reboot evidence
build-release-candidate.log  complete build, gate, deployment and publication transcript
install.log                  standalone installer transcript
```

The published record contains the durable path, full ZIP hashes, source
identity, gate result, and current install status. Keep the local build path as
a secondary location only. `/tmp` is an ephemeral work area, not a release
location.

The handoff record must include:

- full ZIP SHA-256 and MD5;
- `appfs.ubifs` MD5 and the component MD5s from `firmwareInfo`;
- both source commits and both dirty-diff hashes;
- stock input hash;
- selected camlibs and optional package features such as USB-SCSI;
- gate result and evidence path;
- exact durable artifact path.

### 4. Deploy and runtime-verify through the supported installer

The canonical builder invokes the installer automatically after publication.
It stages the extracted `FwPkt/` tree, verifies every firmwareInfo MD5
on-device, reboots, proves the boot was real by an uptime reset, and checks the
exact build/source identity. It then updates the published record to
`installed-verified` and uploads the receipt and final logs without changing
the ZIP bytes.

The build script accepts only deployment options (`--host`, `--ssh-user`,
`--max-wait`, `--wake-wait`, and the explicit safety override `--allow-busy`).
When SSH is initially unavailable, the supported installer automatically tries
the documented Bluetooth/Wi-Fi wake path before refusing to stage anything.
It deliberately
rejects `--skip-trigger` and `--skip-verify` in the normal build wrapper, but
the standalone installer retains those modes for explicitly labelled staged
diagnostics.

### 5. Install an already-published candidate manually only through the supported installer

Use:

```sh
./scripts/release/release-fwpkt.sh <candidate-build-directory>
```

This stages the extracted `FwPkt/` tree, not only the ZIP. It refuses a missing
manifest, a changed ZIP, an unknown device identity, a busy camera, or a reboot
that cannot be proved by an uptime reset. Do not use the deprecated ZIP-only
installers or copy files directly into `/app`.

### 6. Write the install record immediately

After the installer completes successfully, create a dated evidence record under
`docs/evidence/<candidate-id>-install-<YYYYMMDD>/` containing:

```text
candidate_id
display_fwver_before and display_fwver_after
build_id
libgphoto2_commit
patcher_commit
fwpkt_zip_sha256
device FwVer
device openpolaris-libgphoto2-provenance.txt
uptime before and after
firmwareInfo/upgrade log evidence
install command and host/target
```

Update `CURRENT-STATE.md` with the running identity and update the candidate
record from `GATED` or `PUBLISHED` to `INSTALLED-VERIFIED`. Do not infer this
from a successful SSH reconnect or from a version label alone.

### 7. Qualify the hardware separately

A successful flash proves the firmware identity, not camera behaviour. Record
camera model, USB identity, mode, card/output settings, operation, expected
result, actual result, logs, and restoration/cleanup. Only then may the record
be promoted to `PHYSICALLY-QUALIFIED`, and only for the tested matrix.

## What must never happen again

- `.83`, `.84`, and a commit SHA are not interchangeable names.
- A parent commit is not the exact commit used to build the artifact.
- “Built from main” is incomplete without the full source SHAs and dirty hashes.
- A ZIP in `/tmp` is not a published or deployable release.
- A ZIP without `install-manifest.json` is not install-ready.
- A reboot or SSH outage is not proof of installation.
- A device version is not proof of the source commits that produced it.
- A passing offline test is not physical camera qualification.

## Current example: `.84` offline smoke artifact

The record at [`evidence/o-e8daf39ae-smoke-20261028/RELEASE-IDENTITY.md`](evidence/o-e8daf39ae-smoke-20261028/RELEASE-IDENTITY.md)
is deliberately marked `BUILT` only. It is an internal diagnostic artifact, not
an end-user candidate. It must not be called `.83`, and it must not be flashed
or handed to a tester until the canonical build output has completed deployment
and runtime verification.

