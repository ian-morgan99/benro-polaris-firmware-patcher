# o-v17d-darkframe-budget-20261023 (`6.0.0.54.69`) — flash + qualification attempt

Date: 2026-10-23. Flashed via the sanctioned SD-card on-boot watcher path
(`.github/skills/fwpkt-update-flow/SKILL.md`). No NAND was written over SSH.

## Candidate identity (built by scripts/build-release-candidate.sh)

| field | value |
|---|---|
| build_id | `6.0.0.54.69-o-v17d-darkframe-budget-20261023` |
| libgphoto2 | `731d7fbd5b5c590490f2783dd549762fc5dc3b9d` (main, clean) |
| patcher | `437e0d3fac284ef8b1502d58bd4336e0bbff5ec8` (main, clean) |
| zip MD5 | `52a617302021a5dc167360f083bed122` |
| zip SHA-256 | `9dc904553923e3930082cb9055ff1df6f0b5759169ad2b5e75bd071d839eb7dc` |
| appfs MD5 | `c8c0c1a41e540d94a832141077e0aab8` |
| published | `ian-morgan99/PrivateResearch` → `firmware-packets/6.0.0.54.69--o-v17d-darkframe-budget-20261023/FwPkt.zip` |

All four handoff values were recomputed from the bytes and matched the registry row
before staging, per the provenance contract.

## Gate before staging

`GATE: GREEN — 12 passed, 0 failed, 0 skipped`, including `--device-libs
out/device-lib-baseline.txt` (163 sonames captured from `/app/lib` **and** `/lib`;
`/app/lib` alone omits `ld-linux.so.3`/`libc.so.6` and the check reports that as an
input problem, not a build one).

## Staging and reboot

- Target proved empty (`NO /app/sd/FwPkt`) before staging; 107.4 G free.
- Tree streamed with `tar czf - … | ssh 'tar xzf - -C /app/sd && sync'` (the skill's
  verified remote equivalent). Layout confirmed non-nested: `FwVer camera
  firmwareInfo gimbal`.
- All six payload MD5s recomputed **on the device** and matched `firmwareInfo`
  byte-for-byte before rebooting.
- Reboot via `/sbin/reboot` (not 812). Pre-reboot uptime 82806 s; device returned
  at uptime 45 s, so the reset was real rather than a silent no-op.

## Post-install verification — PASS

`scripts/verify_installed_build.py` → `INSTALLED BUILD IDENTITY: PASS`.

- `/app/FwVer` = `FwVer:6.0.0.54.69;date:2026.10.23;`
- `git_commit=731d7fbd5b5c590490f2783dd549762fc5dc3b9d`,
  `build_id=6.0.0.54.69-o-v17d-darkframe-budget-20261023` — both match the row, and
  `build_id` is what distinguishes this from `.68` (issue #58).
- `/app/lib/stage2` restored by the flash; running process maps
  `libpolaris_stage2.so`, `libgphoto2.so.6`, `libgphoto2_port.so.12`,
  `pgphoto.stage2ondisk`; port 8080 listening; installed `ptp2.so` = `22a7851c`.
- **Crash loop resolved**: `LD_PRELOAD errors since boot: 0`. Before the flash,
  `/app/Clog.txt` was repeating `object '/app/lib/stage2/libpolaris_stage2.so' …
  cannot be preloaded` and `exec: line 163: /app/lib/stage2/pgphoto.stage2ondisk:
  not found`.

### Cause of that crash loop — my error, recorded so it is not repeated

`restore_stock.sh PURGE=1` deleted `/app/lib/stage2`, treating it as staging residue.
It is not: the flashed firmware **ships** that directory, and its `/app/bin/pgphoto`
is a wrapper whose entire job is `LD_PRELOAD=$D/libpolaris_stage2.so` and
`exec $D/pgphoto.stage2ondisk`. Removing it left the installed driver unable to
start, which is the same starvation pattern as the 2026-09-07 post-mortem. Recovery
was the sanctioned flash, not an SSH copy-back — rule #2 of the update-flow skill
prohibits editing that path over SSH even with identical bytes.

## Live qualification — GREEN after two mis-specified attempts

Both failures were **operator error on my side**, not firmware regressions. Recorded
in full because both mistakes are easy to repeat.

### Attempt 1 — `--canary --expected-files 1` → FAIL (wrong body)

`TX 1&291&2&state:0;#` produced no reply; `TimeoutError` after 15 s, no `SP_*`
written. The probe at 16:29 reported `pentax k-3 mark iii`; the capture at 16:36 ran
against `pentax k-1 mark ii photoFormat=1`. The body had been swapped between probe
and shutter, so the run was against an unsettled, unintended target. SSH then
returned `Connection refused` and `wait-for-rig.py` reported `AP_UP_SSHD_CLOSED`
(port 8080 still accepting TCP — driver alive, sshd held by Benro Connect).

### Attempt 2 — `--two-shot --expected-files 2` → FAIL (wrong contract)

Per the gate's usage example. SHOT1 behaved correctly and then was judged FAIL:

```
SHOT1 CAPTURE state=4 lifecycle=[1, 4]
SHOT1 FILE /app/sd/normal/SP_0405.dng
SHOT1 CAPTURE state=0 lifecycle=[1, 4, 0]
SHOT1 ... FAIL states=[1, 4, 0] files=['.../SP_0405.dng'] idle=True stale=None
           term=timeout:timed out
```

`shot_satisfied()` requires `len(new_files) == expected_files` **per exposure**, so
asking for two outputs from one shutter press can only ever reach the 180 s deadline.
My first reading — "harness bug, one shutter yields one file" — was **wrong**:
RAW+JPEG legitimately yields two files per exposure, so demanding 2 is correct *when
the camera is in that mode*. The real error was supplying a RAW+JPEG contract while
the K-3 III was in RAW mode.

### Which value is authoritative — none of the inferred ones

`photoFormat` is **not** usable to derive the count, and the repo says so explicitly:

- `scripts/canary-probe.py:882` — `--shot requires --expected-files 1 or 2;
  photoFormat is not authoritative`
- `docs/CURRENT-STATE.md:710` — *"do not infer RAW-only vs RAW+JPEG from
  `photoFormat:2`"*

The value is live rather than retained across bodies: the K-1 II read
`photoFormat=1` and the K-3 III reads `photoFormat=2`, minutes apart on the same rig.
But the K-3 III was in **RAW** mode while reading 2, so `physical-matrix.py:38`
(`format: 2 = RAW+JPEG`, from #180) is an unvalidated claim that does not hold here.
The enum's meaning remains unresolved and must be confirmed from a source independent
of the field itself.

Observed output settles the contract for this rig regardless: `/app/sd/normal` holds
302 `.dng` + 248 `.jpg` on one shared `SP_NNNN` sequence, with exactly **one** paired
stem (`SP_0085`) across all 550 files — i.e. no RAW+JPEG pairing. Recent captures are
single files per shutter (`SP_0404..0407`, all `.dng`). So the current mode is
**1 file per exposure**.

### Attempt 3 — `--two-shot --expected-files 1` → GREEN

```
OUTPUT contract=explicit expected_files=1 photoFormat_hint=2
SHOT1 FILE /app/sd/normal/SP_0406.dng
SHOT2 FILE /app/sd/normal/SP_0407.dng
PASS: two-shot gate (two distinct files, fail-closed)
=== Pre-release gate summary: 14 passed, 0 failed, 0 skipped ===
```

Two consecutive captures, two distinct files, no stale candidate, camera returned to
idle between shutters — which is the behaviour the dark-frame budget governs.

Verdict: **installed, identity-verified, and qualified for RAW (1 file/exposure).**
Not yet qualified for RAW+JPEG: that contract needs the camera confirmed in that mode
and a run with `--expected-files 2`, which should then produce two files per shutter.
Note `photoFormat_hint=2` was present throughout and did **not** mean two outputs.

## Reproduce

```bash
cd ~/Documents/VSCodeProjects/BenroPolarisPatcher
export PATH="$PWD/tools/host-bin:$PATH"          # ssh/scp/docker -> host namespace
python3 scripts/wait-for-rig.py --timeout 180    # READY model=... state=1
# Confirm the body and its file format BEFORE choosing the contract.
# photoFormat is not authoritative; ask, or verify by shooting once and counting files.
bash tests/run_prerelease_gate.sh \
  --build out/o-v17d-darkframe-budget-20261023/FwPkt \
  --libgphoto2-src ~/Documents/VSCodeProjects/LibGphoto2/libgphoto2 \
  --device-libs out/device-lib-baseline.txt \
  --two-shot --expected-files 1 --expected-sp-prefix /app/sd/normal/SP_
```

`--expected-files` is the **per-exposure** obligation: RAW → 1, RAW+JPEG → 2. It is
independent of `--shot-count` (consecutive shutters). Re-check the attached body
immediately before any capture run — a swap between probe and shutter invalidates it.

Rollback: stage the stock extracted `FwPkt/` the same way and reboot.
