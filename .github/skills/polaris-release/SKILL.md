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
  <candidate-id> <stock-FwPkt.zip-or-dir> <clean-libgphoto2-main> [build-id]
```

The script refuses a missing/dirty/detached/non-`main` libgphoto2 checkout.
It builds from the supplied stock FwPkt, runs the deterministic pre-release
gate, recomputes hashes, and uploads the exact ZIP to PrivateResearch.

## Required handoff

Record and hand over all of:

* patcher `main` SHA;
* libgphoto2 `main` SHA;
* candidate/build ID;
* ZIP MD5 and SHA-256;
* appfs MD5;
* PrivateResearch commit and path;
* gate result and any skipped prerequisites.

The candidate is **not installed** merely because the script succeeds. Device
installation must use `fwpkt-update-flow`, followed by runtime provenance and
the camera canary. Keep direct libgphoto2, packaged Polaris, and OpenPolaris
results separate.

## Review rule

Before physical testing, an independent reviewer must inspect the two source
SHAs, the gate transcript, the provenance row, and the exact PrivateResearch
artifact hashes. A historical or diagnostic build must have a distinct ID and
must not overwrite an existing artifact.
