# v109 publication receipt — 2026-11-15

Later deployment update: firmware identity and Astro kit passed installation
at 12:19:09/12:26:30 UTC. No v109 captures ran. Installed camera-file hashes,
independent review and physical qualification remain open. The original
publication-stage account below is historical; see [LIVE-SESSION.md](LIVE-SESSION.md)
and WBS 8.17.18 for the completed handover and explicit verification gap.

PrivateResearch artifact commit:
`ca09e479076d10552aa2b7fe513b3006a3950689`.

[Release directory](https://github.com/ian-morgan99/PrivateResearch/tree/ca09e479076d10552aa2b7fe513b3006a3950689/firmware-packets/6.0.0.54.109--astro-v109-camera-mainline-20261115)
contains FwPkt, Astro/Wi-Fi/index archives, README/INSTALL/RELEASE-NOTES,
complete identity/manifests, SHA256SUMS, test records, LGPL corresponding source,
Astro/Wi-Fi source/licences and retained v108 camera evidence. There were 70
files at the artifact commit; subsequent receipt/research-snapshot additions
do not change any of the five published archive bytes.

GitHub accepted the push and independently reported the commit on main.
A fresh download of FwPkt.zip through GitHub's contents API at that immutable
commit passed cmp against the built ZIP. Recomputed SHA-256:
`504d4a36c32a74b31358b983043152dd127aea2226524d7a897b98b236f3cda3`.
Remote FwPkt Git blob `9ac511f23bbe8c6ca4bfbd3b1be1c35acd4f04d5`,
size 68,408,523 bytes. The API also listed all standard top-level records and
archives. Remote directory listing and download verification are retained in
the private evidence package.

## Process exceptions and why they are bounded

- Standard Astro publisher ran its identity/hash/copy steps, then Git rejected
  the fresh clone's unset author identity. Only the temporary clone received the
  existing canonical Codex Build Agent identity, after inspecting its staged
  destination; its original commit/push steps then completed. No global config.
- The archive verifier accepts builder directories but not the publisher's
  flat ZIP layout (#292). The failed attempt is retained. Each of five archive
  copies passed cmp; conformance then reopened the identical builder-layout
  archives: 21 checks, zero failures/unknowns. Independently, the published
  firmware ZIP passed all CRC checks. This is not a claimed flat-layout PASS.
- Firmware LGPL corresponding source/licences sit outside the Astro tarball
  and were explicitly added to this publication (#331). The builder produced
  the exact transformed source archive; no source or binary was reconstructed.
- Raw logs and original licence texts retain original whitespace. Authored
  Markdown passes diff --check; evidence bytes were not "cleaned up".
- GitHub warned that two archives exceed its recommended 50 MB size but
  accepted them (each is below the hard limit). No history rewrite or LFS
  migration was attempted during this release.

## Issue receipts

- [ian-morgan99/benro-polaris-firmware-patcher#216](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/216#issuecomment-6890825645)
- [ian-morgan99/benro-polaris-firmware-patcher#214](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/214#issuecomment-6890825476)
- [ian-morgan99/benro-polaris-firmware-patcher#340](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/340#issuecomment-6890825427)
- [ian-morgan99/benro-polaris-firmware-patcher#251](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/251#issuecomment-6890825817)
- [ian-morgan99/benro-polaris-firmware-patcher#145](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/145#issuecomment-6890827002)
- [ian-morgan99/benro-polaris-firmware-patcher#235](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/235#issuecomment-6890827589)
- [ian-morgan99/benro-polaris-firmware-patcher#327](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/327#issuecomment-6890827427)
- [ian-morgan99/benro-polaris-firmware-patcher#218](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/218#issuecomment-6890827764)
- [ian-morgan99/benro-polaris-firmware-patcher#292](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/292#issuecomment-6890829271)
- [ian-morgan99/benro-polaris-firmware-patcher#331](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/331#issuecomment-6890829227)
- [ian-morgan99/libgphoto2#165](https://github.com/ian-morgan99/libgphoto2/issues/165#issuecomment-6890829244)
- [ian-morgan99/libgphoto2#164](https://github.com/ian-morgan99/libgphoto2/issues/164#issuecomment-6890828838)
- [ian-morgan99/libgphoto2#143](https://github.com/ian-morgan99/libgphoto2/issues/143#issuecomment-6890830800)
- [ian-morgan99/libgphoto2#115](https://github.com/ian-morgan99/libgphoto2/issues/115#issuecomment-6890830996)
- [ian-morgan99/OpenPolaris#56](https://github.com/ian-morgan99/OpenPolaris/issues/56#issuecomment-6890830307)
- [ian-morgan99/benro-polaris-test-harness#18](https://github.com/ian-morgan99/benro-polaris-test-harness/issues/18#issuecomment-6890830695)
- [PrivateResearch #10](https://github.com/ian-morgan99/PrivateResearch/issues/10#issuecomment-6890841846)
- [Merged PR #346](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/pull/346#issuecomment-6890842066)

17 existing issues plus one merged PR were updated; none was bulk-closed.
All 327 open issues across the four code repositories are indexed publicly.
The additional ten open PrivateResearch issues are snapshotted/dispositioned
privately, making 337 across all five repositories; research restrictions are
preserved.

## Handoff state at original publication, before later deployment

Build source fcc2b5fa54e5c8a30893866c81c98531ba42e5ee and driver
e4840f4290ad5acc4df5c228dc9520b044366b87 remain immutable. Later main commits
contain verification tools and records only, not silently rebuilt v109 bytes.
All source work used the canonical main checkout. One read-only driver source
snapshot and one temporary publication clone are build/publication resources,
not competing development worktrees.

No hardware install, camera command, motor movement, rollback or power action
occurred in this release round. #251 and the matrix in SUMMARY.md remain open.
Primary source work is committed/pushed; the user's existing PrivateResearch
modified pentax_firmware/k5_2_107.zip and untracked docs/ are deliberately
preserved. They must not be discarded to manufacture a clean research checkout.
