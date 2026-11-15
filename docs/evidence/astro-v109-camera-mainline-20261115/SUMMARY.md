# v109 camera/mainline release evidence — 2026-11-15

Update: user-authorized deployment completed on 2026-11-15; firmware identity
verified at 12:19:09 UTC and Astro kit at 12:26:30. Camera qualification and
installed camera-file hash verification remain open. No v109 capture ran.
Issue #251 remains blocking. See [LIVE-SESSION.md](LIVE-SESSION.md) for exact
receipts, the identity-versus-hash verification gap and the final handover.

## Exact identity

- Candidate: `astro-v109-camera-mainline-20261115`; display `6.0.0.54.109`.
- Patcher source: `fcc2b5fa54e5c8a30893866c81c98531ba42e5ee`, clean main at build.
- Driver source: `e4840f4290ad5acc4df5c228dc9520b044366b87`, clean main.
- FwPkt SHA-256: `504d4a36c32a74b31358b983043152dd127aea2226524d7a897b98b236f3cda3`.
- FwPkt MD5: `e3aa53d05004671bb5e69e2edba7e89f`; size 68,408,523 bytes.
- appfs MD5: `1a74a80be1b5c51f8396209d4729fd5a`.
- Astro tar SHA-256: `9edcd24c928dab7941a6dc83ad3c9df61c17a1dcf5ed51ac6f0fc2623b624048`.
- Stock input SHA-256: `f980fe5245a1f85b58d0c2db523402d1af72ddfff782acba99a4eadfdca54d2f`.
- Private location: `ian-morgan99/PrivateResearch`,
  `firmware-packets/6.0.0.54.109--astro-v109-camera-mainline-20261115/`.
- v108 comparison: driver `51f636d825013dcb87bab972a329114f12a7063a`,
  patcher `4a412fff06df7cb04597d70f75a21a77a5340e40`.

## Changes and evidence

Accepted driver main contributes held-Bulb admission through the shared recovery
probe (#165, daef5b7be), source-bounded form-less colour temperature (#164,
1bf8ba51a), timeout phase diagnostics (a09622106), and single-config getter
error propagation (4cbfcf27e). No new camera-protocol edit, guessed opcode,
blanket retry or timeout expansion was introduced this round.
RELEASE-IDENTITY.md contains the full 21-driver/52-patcher commit delta.

This round merged PR #346 and hardened explicit full driver pins, supplied-source
equality, main-only Astro builds, automatic successful candidate version binding,
missing-artifact failure, isolated env-forwarding tests, and stale generated
Docker-route repair. Post-build publication validation now uses --claimed to
check the exact recorded tuple and recognizes the builder's nested Astro ZIP.
Wrong/missing pins, reused build versions, empty/missing archives and conflicting
duplicates still fail. These post-build tooling edits do not change candidate
bytes or source identity.

Accepted Astro main improvements from the other owner are included: scale-aware
index pruning, size-aware downsampling, HTTPS/hash-verified acquisition, opt-in
timings and bilinear weight reuse. No new Astro algorithm work was undertaken.

Consumed 4cbfcf27e impact: Pentax-only: NO; generic PTP2: YES; all vendors using
the shared failed function-property getter can be affected. Successful getters
retain previous behavior; failed getters now return the error instead of
GP_OK/null. Host/targeted tests pass; physical Canon/non-Pentax regression has
NOT been run and remains an adoption gate.

## Verification

| Check | Result | Boundary |
|---|---|---|
| Build doctor | 28 pass, 0 warning, 0 skip | Host prerequisites |
| Exact clean driver host pack | 26/26 pass, research capture disabled | Isolated Meson host, not shipped autotools binary |
| Final prerelease gate | 27 pass, 0 fail, 0 gate-level skip | Candidate/offline |
| Python inside gate | 815 pass, 13 test-level skips, 11 subtests pass | Test-level skips remain explicit |
| Container harness | 31 pass | Executable offline contracts |
| Candidate Astro tests | 81 pass, 3 skip | Offline |
| Publication/version focused tests | 57 pass | Exact claim and archive layouts |
| Artifact conformance | 21 checks, 0 failures, 0 unknowns | Actual Astro package |
| ARM Stage-2 | 100,000 instructions, 265 resolved, 0 unresolved relocations | ELF loader/execution only |
| Identity/dependencies/manifests | PASS | Packaged bytes, not installed runtime |
| Shipped delta vs v108 | 3 of 11 mandatory files changed | FwVer, ptp2.so, provenance |
| Baseline marker audit | No missing source commits; nothing to probe | Ancestry screen, not behavioral proof |
| R1/R3/R4/R5 checks | PASS | Claimed version, main, archives, current payload |

Core/port/loader components remain byte-identical to v108; Astro kit changes
are recorded separately. The original build gate had one ARM prerequisite skip
from a harness path missing /src. Its transcript is retained unchanged; the
later mandatory-ARM gate supersedes it. Python/Unicorn/Flask prerequisites live
only in ignored out/.build-env/python; no system/hardware configuration changed.

ARM binary SHA-256:
`f167e66864479060af82f012891a9df5145d14cbcb735b66a0d2317a22a082ec`.
Harness revision: `81a40299c9fde92e80f4870880e6d25bf240c74f`.
ARM execution does NOT prove PTP, shutter closure, flashing, Wi-Fi or on-device
solving. Library dependency checks use a captured-loader allowlist, not a fresh
device /app/lib inventory.

## Hardware truth and next gates

No hardware was accessed for this release. Recent v108 evidence outranks older
pre-#304 observations. Two ordinary K-1 II JPEG captures SP_0018/SP_0019 passed
full lifecycle plus downloaded-file checks on v108 only. Earlier capture failure,
command-261 -2110 writes and RAW+JPEG publication remain separate open failures.
The consumer published JPEG and deleted the RAW member; this is not dual-output
success.

The direct K-3 III session obtained previews but failed exact shutter restoration
and then disappeared from USB. Do not promote it to a setting/capture pass or
guess recovery sequences. Original-value obligations remain in the canonical
driver hardware log; an ACK is not physical focus movement.

Next sequence: independent review; exact-driver direct-PC fresh-session
read/write/read-back/restore matrix; supervised Manual/Bulb/early-cancel/noise-
reduction/repeat and physical closure; canonical FwPkt install with uptime-reset
and all installed hashes; Polaris-local camera matrix; Benro Connect/OpenPolaris
arrays/completion; Astro integration with its owner; previously qualified
non-Pentax regression before promotion.

See [camera dispositions](CAMERA-ISSUE-DISPOSITION.md) and
[all open issues](OPEN-ISSUE-INDEX.md). No bulk issue closures.
Raw photos/logs and issue-body snapshots are PrivateResearch-only.
