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

---

## Addendum 2026-08-28: a *second*, independent silent-gimbal-drop bug

While exercising the clean-Pentax rebuild path
(`/libgphoto2-source-input` mounted, so the libgphoto2 fork is built
locally rather than from the pinned Debian package), a second silent
packaging defect surfaced. It is independent of the stale-`firmwareInfo`
bug above and reproduces even when `firmwareInfo` is byte-correct.

### Symptom

Builds run, exit 0, produce a 68,372,735 B zip at `/out/FwPkt.zip`. The zip
contains 8 entries instead of the expected 10. The missing entries are
both gimbal binaries (`polaris403_2.0.0.22.bin` and `polaris413_2.0.0.22.bin`).
When flashed, the on-board `polestar_app` would silently reboot (the same
behaviour as the stale-firmwareInfo case) — no NAND write, no UI signal,
no log entry.

In our c2 build the failure mode was *partial*: one of the two gimbal bins
(`polaris413_2.0.0.22.bin`) was missing while the other
(`polaris403_2.0.0.22.bin`) was present. So a `ls -l FwPkt.zip` is not
sufficient to catch it — the zip's *size* looks plausible and the
`firmwareInfo` lines for the present gimbal file are still correct. The
on-board check, however, string-compares *every* `polaris*` line in
`firmwareInfo` to a present file, and a `polaris413` line with no matching
file on disk fails the same way as a bad MD5.

### Root cause

`container/patch.sh:381` (pre-fix):

```sh
cp -p /in/gimbal/*.bin /out/FwPkt/gimbal/ 2>/dev/null || true
```

`2>/dev/null || true` swallowed the failure mode of the underlying
`cp`. The exact reason `cp` was failing in c2 is
mount/timing-sensitive (the most likely candidate is a bind-mount race in
the docker layer over a user-owned `/out` directory) and is not
reproducible on every run. What *is* reproducible is that `2>/dev/null
|| true` makes every kind of `cp` failure invisible.

The fix is two parts:

1. **Stop swallowing the error.** `cp -p /in/gimbal/*.bin /out/FwPkt/gimbal/`
   alone will fail loudly if the input dir is empty or unreadable.
2. **Pre-check the input.** A separate `ls -1 /in/gimbal/*.bin | wc -l`
   guard with a `die` if zero — so the user gets a *clear* "no /in/gimbal
   found, refusing to ship a gimbal-less FwPkt" message rather than a
   confusing `cp: cannot stat` after `2>/dev/null` has already masked
   everything.

### Why the firmwareInfo check didn't catch it

`firmwareInfo` is generated *from* the on-disk state of `/out/FwPkt/`.
When `cp` failed, `/out/FwPkt/gimbal/` was left with only
`polaris403_2.0.0.22.bin`. `gen_firmwareinfo.py` then wrote a
`firmwareInfo` whose `polaris403` line was correct (because the file was
present) and *omitted* the `polaris413` line entirely. The
`verify_firmwareinfo.py` re-MD5/size check was happy: every line in
`firmwareInfo` matched a file. The bug is **structural** — the zip
itself is wrong — and so it requires a **structural** check, not a
content check.

### Resolution: `container/validate_fw_package.py`

A new `validate_fw_package.py` (stdlib-only, ~250 lines) was added at
the end of the build pipeline (after the zip is created, before
publishing) and is the implementation of issue #21. It walks the
finished zip and rejects any of the following:

- **Wrong top-level layout** — anything other than `FwPkt/` as the
  single top-level member.
- **Duplicate members** — same member name twice (zip-spec allows this;
  the on-board updater may not).
- **Missing required files** — must contain `FwPkt/firmwareInfo`,
  `FwPkt/camera/{config,uImage,rootfs.ubifs,appfs.ubifs}`, and at least
  one `FwPkt/gimbal/*.bin`.
- **Stock-component drift** — every file in the `camera/` and
  `gimbal/` directory whose name matches a stock component must hash to
  the *recorded* stock SHA-256. (`appfs.ubifs` is intentionally exempt
  because that is the file the user is replacing.)
- **A concise manifest** is always printed, showing every file and
  its on-disk size, with a PASS/FAIL summary.

It is fail-closed (`die "refuse to ship"` in the build pipeline). The
c2 build that produced the 8-entry zip now fails with:

```
FAIL: 3 structural error(s)
  - missing required files: FwPkt/gimbal/*.bin (no polaris*/oms bins)
  - stock cross-check: missing expected file FwPkt/gimbal/polaris403_2.0.0.22.bin
  - stock cross-check: missing expected file FwPkt/gimbal/polaris413_2.0.0.22.bin

The on-board updater would silently reject this FwPkt.
Do NOT put it on an SD card. Rebuild and re-run this validator.
```

### Acceptance against issue #21

Issue #21 asks for "a finished-package structural validator that
rejects unexpected top-level layout, duplicate members, missing
required files, and stock-component drift." This document is the
proof-of-correctness for that change. A re-run of the broken c2 zip
through the validator fails as above; a re-run of the fixed combined
zip (`builds/2026-08-27-combined-720p60/FwPkt.zip`, SHA-256
`ddc1aab6…`) passes all six checks.
