# FwPkt.zip Layout Contract and SMB Delivery Notes (2026-08-28)

This document records the **layout contract** of a flashable `FwPkt.zip` and
the **candidate-zip verification matrix** we ran before picking the build to
ship. It also records the **SMB delivery convention** so future maintainers
and end-users know which file on the share is the current one and how it
relates to the repository's `builds/` directory.

It is meant to be read alongside [silent-fwpkt-reject-postmortem.md](silent-fwpkt-reject-postmortem.md),
which covers the silent-reject root cause and the structural validator.

---

## 1. The FwPkt/ prefix is mandatory

A `FwPkt.zip` that the Polaris will accept **must** have `FwPkt/` as the
single top-level directory in the archive. This is a hard contract enforced
by the on-board `polestar_app`:

- It is the prefix the updater looks for when it unpacks the zip onto
  the staging area before NAND write.
- The validator `container/validate_fw_package.py` checks this as
  condition #1 ("top-level layout must contain exactly one entry, 'FwPkt/'")
  and refuses to ship any zip that fails.

### 1.1 What we tested

To rule out the hypothesis that the prefix could be safely stripped (the
question "can I just take the inner files and rezip them without the FwPkt
folder?" was raised repeatedly), we ran a controlled experiment:

1. Take a known-good `FwPkt.zip`.
2. Extract the inner files into a flat directory.
3. Rezip that flat directory (no `FwPkt/` prefix, files at zip root).
4. Run the result through `validate_fw_package.py`.

Result: the validator returned **12 errors** and refused to ship the zip.
This is consistent with the on-board updater's behaviour: a flat zip is
silently rejected, with no diagnostic on the device.

**Conclusion:** the prefix is part of the on-board contract. Do not strip
it. Do not "fix" the zip by moving files up a level and rezipping.

### 1.2 Where this contract comes from

The stock `firmware/FwPkt.zip` in the repo and the
`~/Downloads/FwPkt.zip` from Benro's official distribution both **already**
use the `FwPkt/` prefix:

```
$ md5sum firmware/FwPkt.zip ~/Downloads/FwPkt.zip
90bdad511f556f25a2904ae9d2980102  firmware/FwPkt.zip
90bdad511f556f25a2904ae9d2980102  /home/ian/Downloads/FwPkt.zip
```

Both are byte-identical and both pass the validator. The premise that the
stock zip has the files at the top level is incorrect — the prefix has
been part of the contract from the start.

---

## 2. Checksum location: per-file, not zip-level

The integrity check is **per-file** via the `FwPkt/firmwareInfo` manifest:

```
KEY size:<decimal bytes>
KEY MD5 :<hex md5>
KEY src :<relative path inside FwPkt/>
```

`crcInfo` (invoked by `getFwInfo.sh`, invoked by `polestar_app`) recomputes
both fields for every entry and string-compares them against the manifest
lines. There is **no** check on the zip itself — the zip's central
directory CRC, the compression method, the extra fields, and so on are
all irrelevant to the Polaris as long as the bytes inside the zip match
the manifest.

Practical consequence: it is safe to rezip the same `FwPkt/` tree with a
different zip tool, a different compression level, or even to repackage
after a cosmetic move, **as long as** the per-file bytes and the
`firmwareInfo` manifest are unchanged. The validator's role is to catch
the case where this contract is about to be broken (missing file, stale
manifest, wrong layout) before the user puts the SD card in the gimbal.

---

## 3. Candidate-zip verification matrix

The following matrix records the verdict of `validate_fw_package.py` on
every candidate `FwPkt.zip` we had on hand as of 2026-08-28, so future
maintainers can see *why* the build we shipped is the one we shipped.

| File                                                                      | MD5                              | Entries | Verifier | Notes |
|---------------------------------------------------------------------------|----------------------------------|---------|----------|-------|
| `firmware/FwPkt.zip`                                                      | `90bdad511f556f25a2904ae9d2980102` | 10      | PASS     | Pristine stock. Baseline. |
| `~/Downloads/FwPkt.zip`                                                   | `90bdad511f556f25a2904ae9d2980102` | 10      | PASS     | Byte-identical to stock. |
| `builds/2026-08-23/FwPkt.zip`                                             | `25403283…`                       | 10      | PASS     | Layered Pentax-only build; works. |
| `builds/2026-08-27-combined-720p60/FwPkt.zip`                             | `e4a6a37d84745cb05b02d6e5ca8f45d4` | 10      | PASS     | Combined Pentax + HDMI 720p60 + live-view. The shipped build. |
| `SMB:BenroPolaris/FwPkt.zip` (top-level, older copy)                      | `fd8147c9…`                       | 10      | PASS     | 2026-08-23 base + 2026-08-27 09:31 appfs. Pre-dates the combined build. |
| `SMB:BenroPolaris/2026-08-27_pentax-hdmi720p60-live_only/FwPkt.zip`       | `e4a6a37d84745cb05b02d6e5ca8f45d4` | 10      | PASS     | Earlier delivery of the combined build. |
| `SMB:BenroPolaris/2026-08-28_latest_pentax-hdmi720p60-live_only/FwPkt.zip` | `e4a6a37d84745cb05b02d6e5ca8f45d4` | 10      | PASS     | Current recommended flash target. |
| `/tmp/c2-rebuild/out/FwPkt.zip`                                           | (broken)                          | 8       | **FAIL** | Clean rebuild against the wrong Pentax source. Missing both gimbal bins. |
| Flat rezip test (no `FwPkt/` prefix)                                      | (rebuilt)                         | 10      | **FAIL** | 12 errors. Confirms the prefix is mandatory. |

### 3.1 What the c2-rebuild failure proved

The c2-rebuild was an attempt to do a fully clean Pentax rebuild using a
local libgphoto2 source tree that was supposed to be the Pentax fork. It
produced an 8-entry `FwPkt.zip` missing both
`FwPkt/gimbal/polaris403_2.0.0.22.bin` and
`FwPkt/gimbal/polaris413_2.0.0.22.bin` — exactly the kind of structural
error the validator exists to catch. The validator caught it before the
user had a chance to put it on an SD card.

The local source tree turned out to be upstream libgphoto2 without the
Pentax candidate marker in `ptp2`. The clean rebuild is unfinished work;
the deliverable is the layered `2026-08-27-combined-720p60` build.

### 3.2 What the flat rezip failure proved

That the prefix cannot be stripped even when the inner contents are
correct. The 12-error verdict is the validator's loudest possible
response, and it matches the on-board updater's silent-reject behaviour.

---

## 4. SMB delivery convention

We ship to the user's SMB backup share at
`smb://morganbackup.local/Projects/Pentax/BenroPolaris/`. Each
delivery lives in its own subfolder named
`YYYY-MM-DD_<short-descriptor>/` so the share stays self-documenting
and old deliveries can be diffed by date.

### 4.1 Folder naming

`YYYY-MM-DD_<short-descriptor>/`

- `YYYY-MM-DD` is the date the folder was created.
- `<short-descriptor>` is a short, human-readable summary of what is in
  the folder, using kebab-case. For the combined build we use
  `latest_pentax-hdmi720p60-live_only`:
  - `latest` — supersedes any earlier folder with the same content
  - `pentax` — the Pentax camlib patch is applied
  - `hdmi720p60` — HDMI output is set to 720p60 (not 1080p)
  - `live_only` — only live-view is wired up; playback UI is untouched

### 4.2 Folder contents

Every delivery folder contains:

| File                          | Purpose                                                                 |
|-------------------------------|-------------------------------------------------------------------------|
| `FwPkt.zip`                   | The flashable package. The only file the Polaris cares about.           |
| `build-source-provenance.txt` | Per-build log of sources, options, and intermediate hashes.             |
| `README.txt`                  | Date, source path in the repo, validator verdict, MD5 and SHA-256, and a one-line "what is in this build". |

### 4.3 Relationship to the repo

Each delivery's `FwPkt.zip` is byte-identical to a file in
`builds/<date>-<descriptor>/FwPkt.zip` in the repository. The
`build-source-provenance.txt` and `README.txt` exist so the share is
self-describing even when the repo is unavailable (e.g. flashing from
a fresh checkout on a different machine).

### 4.4 Don't ship the top-level `BenroPolaris/FwPkt.zip`

The top-level `FwPkt.zip` on the share is a 2026-08-23 base build with a
2026-08-27 09:31 appfs (md5 `fd8147c9…`). It still passes the validator
and the Polaris will not reject it, but it does **not** contain the
Pentax camlib or the HDMI 720p60 patch — so it will not deliver the
Pentax functionality the user wants. New deliveries should always be
made into a new dated subfolder, never overwrite the top-level file.

---

## 5. How to verify a delivery

To verify a delivered zip before flashing:

```bash
python3 container/validate_fw_package.py /path/to/delivered/FwPkt.zip
```

Expect:

```
PASS: 0 errors, 0 warnings
  FwPkt/                              0 B
  FwPkt/camera/                       0 B
  FwPkt/camera/appfs.ubifs            64,356,352 B
  FwPkt/camera/config                 326 B
  FwPkt/camera/rootfs.ubifs           21,102,592 B
  FwPkt/camera/uImage                 4,188,435 B
  FwPkt/firmwareInfo                  399 B
  FwPkt/gimbal/                       0 B
  FwPkt/gimbal/polaris403_2.0.0.22.bin 84,328 B
  FwPkt/gimbal/polaris413_2.0.0.22.bin 84,284 B
```

Then check the MD5 against the value in `README.txt`. If either check
fails, do not flash the zip.

---

## 6. Acceptance against the open follow-ups

These notes are the post-fix record for the user questions raised in
this branch:

- "Can I just rezip the inner files without the FwPkt folder?" — No.
  See §1.1.
- "Is the checksum at the zip level?" — No, per-file via
  `firmwareInfo`. See §2.
- "Which file on the share should I flash?" — The one in
  `2026-08-28_latest_pentax-hdmi720p60-live_only/`. See §4.4.
- "Why are there two folders with the same content?" — The
  `2026-08-27_pentax-hdmi720p60-live_only/` folder is the first
  delivery; `2026-08-28_latest_…` is the same bytes re-shipped under a
  clearer name on 2026-08-28, with a README explaining the
  relationship. See §4.

The validator, the fixes to `container/patch.sh`, and the
`container/verify_firmwareinfo.py` integration are already in the
`ec01ab2` commit. This document is the human-readable companion.
