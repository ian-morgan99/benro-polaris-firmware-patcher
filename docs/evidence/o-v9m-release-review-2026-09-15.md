# o-v9m release review and rollback record

Date: 2026-09-15
Candidate: `o-v9m-preview-throttle`
Status: RELEASE BLOCKED; device restored to o-v9l.

## Candidate provenance

- libgphoto2: `121675124e173da1864421acebea8e20c851c827`
- zip MD5: `cae3d7cafd70e68f9e086f1a354e3262`
- zip SHA-256: `82f5e6d47eed6717c91af61f2ea0b41aa0cd646705d2878bc7ec48363af55c4f`
- appfs MD5: `f8f764ee4b5fabf40307dd725fca49be`
- private artifact commit: `85b27d6`

## Build/release findings

The candidate passed package structure and firmwareInfo manifest gates. It was
built from a clean libgphoto2 checkout, but the patcher tree was dirty at build
time; the candidate therefore was not reproducible from its recorded patcher
ref and was not release-qualified.

The device was installed through the sanctioned extracted `FwPkt/` flow. After
installation, repeated Stage-2 initialization/app reconnect activity and a
general runtime outage were observed before post-install camera qualification.
The candidate is release-blocked.

## Recovery

The registered o-v9l artifact was staged through the same extracted-tree flow.
On-card hashes matched firmwareInfo. After reboot:

- build ID: `6.0.0.54.4`
- libgphoto2: `121675124e173da1864421acebea8e20c851c827`
- pgphoto/polestar and ports 22/8080/9090: healthy
- `/app/sd/FwPkt/`: consumed by the updater

## Prevention changes

- Dirty patcher worktrees now fail closed unless diagnostic-only
  `--allow-dirty-patcher` is explicitly supplied.
- Build provenance records patcher commit and dirty-tree hash.
- Post-repack appfs verification requires deterministic preview-throttle exports
  in the generated pgphoto wrapper.
- Hardware skill and libgphoto2 release process require clean inputs,
  packaged-wrapper verification, no-camera canary, camera matrix qualification,
  and last-known-good rollback.

## Test limits

Offline wrapper, USB supervisor, restart-lock, fail-closed package, Stage-2
compile where toolchain was available, and Python tests passed. Physical camera
qualification of o-v9m was stopped after the general outage; no claim is made
that the candidate fixed the original preview/USB failure.
