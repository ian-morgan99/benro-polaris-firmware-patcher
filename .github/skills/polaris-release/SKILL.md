---
name: polaris-release
description: Build and publish a provenance-complete Polaris firmware candidate from libgphoto2 main.
---

# Polaris release skill

Use this skill whenever producing a firmware candidate intended for review,
installation, or physical testing. Do not hand-roll a Docker build, copy
runtime binaries into `/app`, or publish a ZIP without provenance.

## Required command

From the patcher repository root:

```sh
./scripts/build-release-candidate.sh \
  <candidate-id> <stock-FwPkt.zip-or-dir> <clean-libgphoto2-main> [build-id] \
  --change-summary docs/templates/release-change-summary.json
```

The script refuses a missing/dirty/detached/non-`main` libgphoto2 checkout, and
also refuses a missing/dirty/detached/non-`main` patcher checkout before doing
any expensive work. It
first runs the libgphoto2 Meson deterministic regression pack, then builds
from the supplied stock FwPkt, runs the patcher/package deterministic
pre-release gate, publishes the exact ZIP to PrivateResearch, then attempts
deployment through `scripts/release/release-fwpkt.sh` and proves the running
identity when hardware is available. A deployment failure does not retract the
published gated artifact. Use `--host`, `--ssh-user`,
`--max-wait`, or the explicit `--allow-busy` safety override when required;
the release wrapper rejects `--skip-trigger` and `--skip-verify`.

**One version, one set of commits.** The app-visible version is derived, never
typed, and when the candidate passes the gate it is claimed *and bound* to the
exact libgphoto2 and patcher commits it was built from, in
`docs/RELEASE-VERSION-STATE.md`. Both directions are enforced: a version may
never describe a second commit set, and an unchanged commit set may never be
issued under a new version. That is why a dirty patcher tree is refused — a
binding made from uncommitted work would be a claim about a commit that does not
describe the build. Commit or stash first, then release. Rebuilding an unchanged
tree to "try again" is expected to fail here; change something or reuse the
existing version.

The regression order is therefore: libgphoto2 unit/production-path tests,
patcher and Stage-2 tests, package/manifest validation, then (only after
installation) the live canary and physical camera matrix. No hardware claim
is inferred from the offline pack.

## Required handoff

Record and hand over all of:

* patcher `main` SHA;
* libgphoto2 `main` SHA;
* candidate/build ID;
* ZIP MD5 and SHA-256;
* appfs MD5;
* PrivateResearch commit and path;
* gate result and any skipped prerequisites.

The candidate is published after the offline gate even when this rig cannot
deploy it. The published status must distinguish `gated` from
`installed-verified`; physical camera qualification remains a separate gate.
Keep direct libgphoto2, packaged Polaris, and OpenPolaris results separate.

`--change-summary` is mandatory. Start from
`docs/templates/release-change-summary.json` and state the previous candidate,
the purpose, each declared fix, issue references, validation focus, and known
limits. The builder then generates `release-change-manifest.json` and
`RELEASE-IDENTITY.md` containing the exact source SHAs, every commit since the
declared baselines, stock-package hash, ZIP hashes, and appfs hash. The
identity verifier and private uploader refuse a candidate missing either file.
Those two files are published beside the ZIP and are the authoritative answer
to “what exactly went into this version”; never reconstruct that answer from a
version number, branch name, or memory.

## Review rule

Before physical testing, an independent reviewer must inspect the two source
SHAs, the gate transcript, the provenance row, and the exact PrivateResearch
artifact hashes. A historical or diagnostic build must have a distinct ID and
must not overwrite an existing artifact.
