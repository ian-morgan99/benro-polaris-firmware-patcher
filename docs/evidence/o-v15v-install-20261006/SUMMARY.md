# o-v15v (6.0.0.54.59) — final build, publication and on-device install

Date: 2026-10-06 (UTC). Device: Benro Polaris at `192.168.0.1` (SSH as root).
Candidate: `o-v15v-k1ii-msc-pid-20261006`.
Requested by: "Ensure you issue a final build and upload to polaris. Be sure to
update version numbers."

## 1. Build and release gate

| item | value |
|---|---|
| candidate id | `o-v15v-k1ii-msc-pid-20261006` |
| display firmware version | `6.0.0.54.59` (derived by `verify_display_fwver_monotonic.py --next`) |
| build id | `6.0.0.54.59-o-v15v-k1ii-msc-pid-20261006` |
| libgphoto2 commit | `f3a8ffebf` (clean, on `main`) |
| patcher commit | `8949d83` |
| bulb patch | always applied (`--polestar-bulb-patch`) |
| `FwPkt.zip` md5 | `2afb6e3b087af03e8d0d902626e7327a` |
| `appfs.polaris.bin` md5 | `e31baa64438a8a2f934dbb9ddcadf5a2` |
| gate | **GATE GREEN** — full transcript in `out/build-o-v15v.log` |
| package output | `out/o-v15v-k1ii-msc-pid-20261006/` |
| publication | `ian-morgan99/PrivateResearch` @ `70e85fc9f`, path `firmware-packets/o-v15v-k1ii-msc-pid-20261006/FwPkt.zip` |
| zip sha256 | `d8380851af6034ee3230ef3a56b93824fcfc743dd3e73e985a82291dd427401b` |

## 2. Why `.59` supersedes `.58`

`.58` (`o-v15u`) was built and published but **never flashed**, and its content is
an ancestor of this build:

```
git merge-base --is-ancestor e6b55ad09 HEAD   # .58's libgphoto2 commit -> true
git merge-base --is-ancestor 4a8359f   HEAD   # .58's patcher commit     -> true
```

so `.59` is a strict superset of `.58` plus the corrected K-1 II PID
classification (`f3a8ffebf`) and the corrected R0 containment guard
(`15c6b9805`). `.58` is recorded as `superseded / never flashed` in
`docs/RELEASE-VERSION-STATE.md`, which is now at `last_display_fwver=6.0.0.54.59`
(commit `7efe367`).

## 3. Staging and install (per `.github/skills/fwpkt-update-flow/SKILL.md`)

| step | result |
|---|---|
| pre-install `/app/sd/FwPkt` | empty (no stale package) |
| transfer | extracted `FwPkt/` tree only (never the zip), 86 MB in under a minute |
| on-device `firmwareInfo` MD5 + size check | 6/6 files match the built package |
| reboot | `ssh 'sync; /sbin/reboot'` at 06:28:44Z (code-812 path not used) |
| device back | ~40 s later |

## 4. Post-install verification

| check | expected | observed |
|---|---|---|
| `FwVer` | `6.0.0.54.59` | `6.0.0.54.59` |
| provenance `build_id` / `git_commit` | this build | match |
| K-1 II MSC row in `ptp2.so` | present | `Pentax:K-1 Mark II (MSC mode, USB id 0182)` present |
| crash-handler re-assert marker | present | `STAGE2_REASSERT_CRASH_HANDLER` present |
| `pgphoto` process | single, stable | pid 250, stable |
| `Mlog` FATAL entries | 0 | 0 |
| `Clog` | empty | 0 bytes |

## 5. Physical qualification — PENDING

No camera was present on the device USB bus at install time: `state:-5` and no
`25fb:` device in the device's `lsusb` output. Per the fwpkt-update-flow skill
this is recorded as **installed, canary pending** rather than silently skipped.

When a camera is connected:

1. `./tests/run_prerelease_gate.sh --canary --expected-files <1|2>` against the
   live device.
2. Confirm the crash handler now reports a faulting PC on a bulb/capture crash
   (#176, #177).
3. For the open question in #179, capture `lsusb -v -d 25fb:0182` on a K-1 II
   left in MSC mode to see whether it exposes any PTP interface at all.

## 6. Rollback

`6.0.0.54.55` is the last physically tested build and is the rollback target; the
untouched stock package is in `builds/stock/`. Rollback uses the same extracted
`/app/sd/FwPkt/` + reboot flow.
