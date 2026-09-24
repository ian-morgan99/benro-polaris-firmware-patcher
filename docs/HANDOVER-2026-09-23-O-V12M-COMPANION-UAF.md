# Handover: o-v12m fixes pre-capture crash, exposes companion-file UAF

Date: 2026-09-23

This is the authoritative continuation point for Pentax K-3 III shutter issue
#122 and o-v12j/o-v12k crash issues #132-#134. Read
`PENTAX-CAPTURE-VERSION-LEDGER-2026-09-23.md` first, then this file.

## Current device state

- Polaris identity: SSID `polaris_d13e86`, BSSID `48:E7:DA:D4:B5:73`, route
  `192.168.0.1 dev wlp8s0`.
- Installed firmware: `6.0.0.54.23-o-v12m-observed-lifecycle`.
- Installed libgphoto2: `ba206d8af8e0e6f7e97c6051e4e2d89d7bdc52e7`.
- Installed patcher source: `5e05a0e5b7353242237f0567448d41a26e842f7f`.
- Installed packet registry id: `o-v12m-observed-lifecycle-20260923`.
- Zip MD5: `7413eb88321072b7c49ff83a2e0c5876`.
- Zip SHA-256: `3657967e1be91cbea60b307487af3888249e8d92b87fa0700176c2c2eb5f0a8c`.
- Appfs MD5: `029b5d2f1d411884569cbf5216b50588`.
- Private artifact commit: `91f54c5`.
- Installation used the canonical extracted `/app/sd/FwPkt` flow. All six
  on-card MD5s matched, `/sbin/reboot` caused a real reboot, the staged tree was
  consumed, FwVer/provenance match, and runtime maps/hashes passed.
- Camera USB currently enumerates as `25fb:0189`. Preview was restored ON by
  the bounded tester cleanup. Do not send another shutter on o-v12m.

Runtime matched-path hashes after install:

```text
core  5973e8c8999b1f4f01be70a9cafdb7ba
port  ad50e83594397aef48b63ed2375890cc
ptp2  163a5645f7c2a7b10911f81aa8bf447a
usb1  4423bba29bf8c5d899598841ec3e6310
```

## What o-v12m proved

Exactly one bounded code-264 capture was sent with preview first confirmed
OFF. Camera info reported K-3 III, `photoFormat:2` (RAW+JPEG), and pgphoto
reported `numOfCaptureImage 2`.

Unlike o-v12j/o-v12k, o-v12m did not crash on entry. The exact trace in
`/app/sd/system/log/Clog_000137.log` is:

```text
[stage2] capture[1]: enter type=0 mono=124
[stage2] capture[1]: real gp_camera_capture returned ret=0 elapsed=3s
New file is in location /IMGP3592.JPG on the camera
captureImageEvent:0 Path:IMGP3592.JPG
code[264],val[state:4;IMGP3592.JPG]
...
gp_list_count 2
gp_filesystem_get_file111
[stage2] *** CRASH sig=11 (SIGSEGV) si_addr=0xae579008 pc=0xb6c50878
```

Interpretation:

1. Moving output-contract discovery into post-capture polling fixed the earlier
   pre-Initiate crash boundary.
2. The primary JPEG completed and state 4 was published.
3. The companion was transferred/published, so Benro saw two filesystem files.
4. Benro crashed while retrieving the second file because the companion buffer
   had already been freed.
5. No second shutter was attempted. The test client was interrupted and
   restored preview ON.

`scp` closes on this device, so the raw Clog was not copied locally. The exact
relevant lines were retrieved read-only with `ssh ... strings ... awk`. Pull
`Clog_000137.log` before log rotation if a working transfer mechanism is
available; do not improvise a firmware/runtime mutation to retrieve it.

## Root cause and pushed source fix

In `pentax_reconcile_transfer_candidate()`, the companion buffer was passed to
`gp_file_set_data_and_size()`. That API takes ownership, but
`pentax_reconcile_extra_candidates()` subsequently freed `extra.data`. The
filesystem cache therefore held a dangling pointer. The later
`gp_filesystem_get_file` dereference matches the observed crash exactly.

Fix pushed to libgphoto2 PR #81 branch `rescue/final-shutter-20260923`:

- commit `ab0de090c` — `ptp2/pentax: retain published companion buffer ownership`
- URL: https://github.com/ian-morgan99/libgphoto2/commit/ab0de090c
- after successful `gp_file_set_data_and_size()`, clear `buffer->data` and
  `buffer->size`, matching the existing primary-file ownership transfer.
- focused tests: `test-pentax-utils` PASS, `test-pentax-reconcile` PASS.
- full `ptp2.so` compile: PASS.
- `git diff --check`: PASS.

The preceding lifecycle commit is `ba206d8af`. Together they:

- fail closed on unreadable/unowned pre-capture state without destructive
  drain;
- discover RAW+JPEG `+524` from the same post-capture samples as candidate
  `+32/+36`;
- await exactly one companion after the primary for RAW+JPEG;
- require `+36 == 0` in the recovery predicate;
- retain companion-buffer ownership after publication.

## Current repositories

Patcher public main currently includes:

- `5e05a0e` — version/evidence ledger and interoperability lifecycle analysis;
- `03fdb57` — o-v12m provenance row;
- user's unrelated `.vscode/settings.json` remains modified and untouched.

Libgphoto2:

- worktree `/tmp/libgphoto-final-20260923` is on
  `rescue/final-shutter-20260923` at `ab0de090c` and tracked-clean (ignored
  build directory may exist);
- clean standalone clone `/tmp/libgphoto-v12m-clean` is stale at `ba206d8af`;
  do not use it for the next build without fetching/checking out `ab0de090c`.

Patcher clean build worktree `/tmp/benro-v12m-clean` is at `5e05a0e` and does
not include later documentation commit `03fdb57`. For the next clean build,
create/update a clean detached/standalone patcher checkout at the newest public
main SHA. Do not build from the dirty primary checkout.

## Exact next steps

1. Review PR #81 head `ab0de090c`, especially ownership after
   `gp_file_set_data_and_size()` and failure paths. Do not change the proven
   fail-closed pre-capture ownership policy.
2. Add a focused regression test if practical that proves a successfully
   published companion is not freed by the reconcile loop. If that requires an
   unreasonable full CameraFilesystem mock, record why and retain the exact
   live reproducer as integration coverage.
3. Build a clean next packet, suggested id
   `o-v12n-companion-ownership-20260923`, from exact libgphoto2 `ab0de090c` and
   current clean patcher main. Follow `docs/LIBGPHOTO2-UPGRADE-PROCESS.md`.
4. Immediately upload it with the `fwpkt-private-upload` skill and add the
   public registry row with recomputed zip MD5/SHA-256/appfs MD5.
5. Update PR #81 and patcher issues #122/#132 with the o-v12m trace and the
   ownership diagnosis before installation.
6. Install only through `fwpkt-update-flow`: prove BSSID/route/FwVer, empty
   target, stream the extracted tree, verify all six MD5s on-device, stop
   keepalive, `/sbin/reboot`, then prove FwVer/provenance/hashes/maps.
7. First canary: preview OFF, one RAW+JPEG Pixel Shift capture only. Require:
   real capture return, state 4/file event, two retrievable filesystem members,
   no SIGSEGV, stable pgphoto PID, USB present and PTP-openable.
8. Inspect the Clog before shot two. Only if all first-canary gates pass, issue
   shot two and require another complete two-object lifecycle with no stale
   candidate or `state:-1005`.
9. Then run the full ledger promotion matrix: JPEG-only x3, RAW-only x3,
   RAW+JPEG consecutive captures, Pixel Shift RAW+JPEG followed by another
   shutter, post-shot AF/config, preview demand restore, and process/session
   stability.
10. Live View heat is not closed by this capture fix. Default/demand-owned LV
    belongs in the persistent serialized pgphoto/OpenPolaris session owner, not
    a Stage-2 init write or timer. Keep preview OFF during capture qualification
    and track thermal causality separately under #123.
11. K-1 II and Canon R5 Mark II remain NOT TESTED for this candidate; do not
    inherit earlier PASS claims.

## Stop conditions

- Any crash, pgphoto PID change, `state:-10`, OpenSession `0x02ff/0x02fa`, or
  missing companion: stop before another shutter and preserve logs.
- A state 1 or state 4 acknowledgement alone is not PASS.
- Do not directly replace `/app` binaries to test the fix.
- Do not install the recovery baseline merely because it produced one file;
  it did not solve repeated RAW+JPEG ownership.
