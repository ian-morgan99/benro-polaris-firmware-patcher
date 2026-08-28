# FwPkt Silent-Reject Post-Mortem (2026-08-27 combined-720p60)

**Symptom:** User flashes `builds/2026-08-27-combined-720p60/FwPkt.zip` (Pentax +
HDMI 720p60) onto the Polaris. The on-board updater does **not** install
anything, gives **no** error, **no** notification, **no** log entry on the
device UI. The Polaris reboots to the previous firmware and the user's
Pentax functionality never arrives. There is no "update failed" toast or
audio cue — the user has no signal that anything went wrong.

**Severity:** Critical. Silent rejection with no diagnostic is a user-trust
hazard: it is impossible to distinguish "I forgot to put the SD card in the
right slot" from "I built a bad packet."

**Scope:** Every `FwPkt.zip` that was packaged with `container/patch.sh`
**without** an in-process `firmwareInfo` regeneration step, after any
modification to `appfs.ubifs`. In this repository, the
`builds/2026-08-27-combined-720p60/FwPkt.zip` produced on 2026-08-27 was
exactly such a packet.

---

## Root cause: stale `firmwareInfo` after a layered repack

`polestar_app` (the on-board updater running in the Linux userspace of the
Hi3559V200) re-validates every component before it writes to NAND. The chain
is:

```
polestar_app
  └─ getFwInfo.sh
        └─ crcInfo  (reads FwPkt/firmwareInfo, recomputes MD5+size
                     of each component, string-compares both fields)
```

If **any** `KEY size:...` or `KEY MD5:...` line in `firmwareInfo` does not
match the on-board recomputation, the updater logs the failure internally,
**does not write NAND**, and **reboots** — the user sees the previous
firmware and no other signal. U-Boot is the only writer, and it is only
reached after `crcInfo` has approved the packet.

The combined 2026-08-27 build was assembled in two layers:

1. A `2026-08-23-pentax-only` run that produced a working Pentax `FwPkt.zip`
   with `appfs` MD5 `1775c7bc4eee7d549a36fa28bb13f367`.
2. A subsequent **HDMI geometry repack** in which `appfs.ubifs` was
   rewritten by `container/hdmi_geometry_patch.py`, producing a new
   `appfs` with MD5 `91629acf0494b7f43298f6821913124f` (same 64,356,352-byte
   size, but a different hash).

The repack re-zipped the `FwPkt/` tree, but did **not** re-run
`container/gen_firmwareinfo.py`. The shipped `firmwareInfo` still claimed
`appfs MD5:1775c7bc…` — the old Pentax-only hash. The on-board `crcInfo`
recomputed the actual MD5 (`91629acf…`), string-compared, found a mismatch,
and silently rebooted.

The full 6-entry verification of the broken packet (extracted from
`builds/2026-08-27-combined-720p60/FwPkt.zip.broken`):

| component | manifest size | actual size | manifest MD5 (claimed) | actual MD5 (recomputed) | result |
|---|---:|---:|---|---|---|
| config  | 326       | 326       | 1905e2d041be62b679f7dc6c64ab9d3a | 1905e2d041be62b679f7dc6c64ab9d3a | OK |
| uImage  | 4,188,435 | 4,188,435 | 5f6a0c1861a254371c4a956b57f26685 | 5f6a0c1861a254371c4a956b57f26685 | OK |
| rootfs  | 21,102,592 | 21,102,592 | 778b27bcade9ddc6ea4a7cb45254c551 | 778b27bcade9ddc6ea4a7cb45254c551 | OK |
| appfs   | 64,356,352 | 64,356,352 | 1775c7bc4eee7d549a36fa28bb13f367 | 91629acf0494b7f43298f6821913124f | **MISMATCH** |
| polaris403 | 84,328  | 84,328   | 4facafa7d29c1e6c2a125b8309c9b901 | 4facafa7d29c1e6c2a125b8309c9b901 | OK |
| polaris413 | 84,284  | 84,284   | c0299d06a15f5c2fbecb9a6db76a29c5 | c0299d06a15f5c2fbecb9a6db76a29c5 | OK |

A single mismatched line is enough to fail the whole update.

---

## Fix shipped in this repo (commit `40565d1`)

### 1. Fail-closed offline verifier

A new `container/verify_firmwareinfo.py` was added that re-runs the
on-board check on the host — parses the in-package `firmwareInfo`, walks
`camera/` and `gimbal/`, recomputes each MD5+size, string-compares both
fields. Exits 0 only on a perfect match; exits 1 with a per-line diff
otherwise. Stdlib-only (no extra packages in the patcher image).

This is the **same algorithm** the device runs, so any mismatch it would
have caught at flash time is now caught at build time.

### 2. Wired into `container/patch.sh` as a build gate

`container/patch.sh:386-396` now invokes the verifier immediately after
`gen_firmwareinfo.py` regenerates the manifest, and **refuses to zip** if
the verification fails. The build is fail-closed: a layered repack that
forgets to regenerate `firmwareInfo` cannot leave the pipeline anymore.

```bash
python3 /opt/patcher/gen_firmwareinfo.py /in/firmwareInfo /out/FwPkt > /out/FwPkt/firmwareInfo

# Fail-closed package-integrity gate. The on-board updater (polestar_app ->
# getFwInfo.sh -> crcInfo) recomputes the MD5 + size of every component and
# string-compares it against firmwareInfo. Any mismatch -> no NAND write,
# silent reboot, no notification. Re-run the same check here against the
# produced FwPkt so a build that shipped a stale manifest (e.g. a layered
# HDMI repack that forgot to regenerate firmwareInfo) cannot leave the
# pipeline. See container/verify_firmwareinfo.py for the rules.
if ! python3 /opt/patcher/verify_firmwareinfo.py /in/firmwareInfo /out/FwPkt; then
  die "firmwareInfo does not match the produced FwPkt -- the Polaris would silently reject this update. Refusing to zip."
fi
log "verified firmwareInfo against produced FwPkt (on-board check will pass)"
```

### 3. In-place repack of the broken `builds/2026-08-27-combined-720p60`

The user's broken packet was **not** deleted. Instead:

- `builds/2026-08-27-combined-720p60/FwPkt.zip` was overwritten with a
  packet that has a freshly regenerated `firmwareInfo`. The new manifest
  contains the same `91629acf…` MD5 that the file already has.
- `builds/2026-08-27-combined-720p60/FwPkt.zip.broken` was kept as a
  safety-net copy so the user can still re-derive what the on-board
  updater saw on 2026-08-27.
- `builds/2026-08-27-combined-720p60/build-source-provenance.txt` was
  appended with a `rebuild2_*` block recording the repack timestamp,
  commands run, and SHA-256 fingerprints before/after.

### 4. SHA-256 fingerprints

| file | SHA-256 | size | status |
|---|---|---:|---|
| `FwPkt.zip` (fixed)        | `ddc1aab69c97f9d2aea7492709c47f4ea3f1aca443fe5c08bf9ece41a2338e8e` | 68,468,962 | verifier OK 6/6 |
| `FwPkt.zip.broken`         | `fb4c37e0e00c4b61a42e3c3b6d515cc5a1c4b0676cc4bc54275f4a27c6e8adaf` | 68,484,760 | verifier FAIL on `appfs` |
| `build-source-provenance.txt` | (rebuilt text) | 3,144 | log entry appended |

The fixed and broken zips are also on the SMB backup share at
`smb://morganbackup.local/home/Projects/Pentax/BenroPolaris/2026-08-27_pentax-hdmi720p60-live_only/`
with SHA-256s re-verified on the share.

---

## Acceptance test results for the new gate

| test | input | expected | result |
|---|---|---|---|
| 1 | `builds/2026-08-27-combined-720p60/FwPkt.zip` (fixed) | PASS 6/6 | **OK** |
| 2 | `builds/2026-08-27-combined-720p60/FwPkt.zip.broken` (old) | FAIL on `appfs` | **OK** — 1 mismatch, exit 1 |
| 3 | fixed zip + 3-byte XOR mutation of `appfs.ubifs` | FAIL | **OK** — 1 mismatch, exit 1 |
| 4 | stock `firmware/FwPkt/FwPkt/` | PASS 6/6 | **OK** |

The gate is sound, fail-closed, and matches the device's check.

---

## Recommended user actions

1. **Try the Pentax-only packet first** if a pure libgphoto2 test is
   desired — it is unmodified at `builds/2026-08-23/FwPkt.zip`. Its
   `appfs` is `1775c7bc…` and the on-board check passes.
2. **Then try the fixed combined packet**
   `builds/2026-08-27-combined-720p60/FwPkt.zip` (SHA-256 above). The
   on-board check will pass for every component.
3. **Do not** use `builds/2026-08-27-combined-720p60/FwPkt.zip.broken` —
   it is kept for forensic reference only; the on-board updater will
   silently reject it.

---

## Why the build was structured this way (so it cannot recur)

The fix is not "remember to regenerate `firmwareInfo` after the repack."
Humans forget. The fix is that the build now **cannot** ship a packet
whose `firmwareInfo` does not match its files: the verifier runs in the
same process that runs the manifest regenerator, and the pipeline calls
`die` on a mismatch before the zip step.

The same fail-closed approach is being extended in adjacent work (see
issue tracker items on a clean source-to-combined pipeline) to cover
ZIP layout, stock-component drift, and UBIFS-geometry checks. The
current gate is the **manifest-integrity layer**; structural and
version-state checks are independent items and have not yet been
shipped.

---

## Related items in the issue tracker

The post-mortem closes the following pre-existing issues
(see `gh issue list --repo ian-morgan99/benro-polaris-firmware-patcher`):

- #19 — *Triage FwPkt install rejection* — the bug this doc describes
- #20 — *Verify `firmwareInfo` MD5/size, add fail-closed gate* — directly
  implemented as `container/verify_firmwareinfo.py` + `container/patch.sh:386-396`

It is **adjacent** to but does **not** close the following (they
require additional work that the manifest gate does not cover):

- #21 — *Validate FwPkt ZIP structure and stock-component consistency* —
  the next layer (layout / nested-dirs / duplicate members / stock drift)
- #22 — *Test Polaris updater version-state rules and UBIFS acceptance* —
  the third-line check (FwVer, downgrade, UBIFS geometry)
- #18 — *FwPkt.zip availability* — re-affirmed: file is on disk, new
  SHA-256 committed, no rebuild needed by the user

It **does not** address the deeper release-readiness items that remain
open (#1, #2, #8, #11, #12, #13, #15).
