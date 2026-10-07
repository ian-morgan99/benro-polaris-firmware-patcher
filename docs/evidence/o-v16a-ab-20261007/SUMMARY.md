# .60 install + capture-guard A/B — 2026-10-07

## What was installed
`.60` (`o-v16a-captureguard-20261006`) installed via the sanctioned flow: tar-stream
of the registered `FwPkt/` tree to `/app/sd`, 6/6 on-device MD5+size matches against
the on-card `firmwareInfo`, `/sbin/reboot` 10:09 UTC. Post-install verification:

- `/app/FwVer` = `6.0.0.54.60`; code 780 `sw:6.0.0.54.60` (matches registry).
- `/app/openpolaris-libgphoto2-provenance.txt`: `git_commit=f3a8ffebf…`,
  `patcher_commit=0e6edd0…`, `build_id=6.0.0.54.60-o-v16a-captureguard-20261006`
  — exact match to the provenance row.
- Guard string present in `/app/lib/stage2/libpolaris_stage2.so`; NOT enabled in the
  shipped wrapper (default off, as registered).

## Camera
K-3 III (`25fb:0189`) attached 11:45 local, `286` reports model + `state:1`.
Body is in **RAW+JPEG** — every shot writes 2 files, so the batches ran with
`--expected-files 2` (the RAW-only `--expected-files 1` assertion does not apply to
this card/body state; see polaris-debugging §0).

## A/B results (canary-probe.py --shot, expected-sw 6.0.0.54.60)
| Batch | Guard | Shots | Result |
|---|---|---|---|
| `guard-off-shots.log` | OFF (wrapper default) | 5 | 5/5 files complete, no crash |
| `guard-on-shots.log` | ON (`STAGE2_CAPTURE_GUARD=1` in `/app/bin/pgphoto`, daemon restarted, env verified in `/proc/<pid>/environ`) | 5 | 5/5 files complete, no crash |
| `guard-on-rapid.log` | ON, back-to-back (~1 s apart, no settle) | 6 | 6/6 files complete, no crash; pgphoto PID unchanged (24565), uptime continuous |

Transcripts: `guard-off-shots.log`, `guard-on-shots.log`, `guard-on-rapid.log` (this dir).

## What this proves and what it does not
- **Proves:** `.60` is a functional drop-in for `.59` — camera path, capture, and
  file-write obligation all pass with the guard compiled in and enabled. No
  regression from the guard in 11 guard-ON captures.
- **Does not prove:** that the guard prevents the #176 crash. The crash is
  intermittent (first occurrence after a fresh connect); 16 sequential captures did
  not reproduce it in either arm, and the guard's refuse-path never fired (no
  `capture-guard` log lines — no re-init overlapped a capture in this pattern).
  The original crash needed the app's own reconnect/re-init timing, not a scripted
  sequential canary.
- **Next evidence that would matter:** normal bench use through Benro Connect
  (app-driven connect/shoot/disconnect cycles) on `.60` with the guard ON, watching
  for the `sync_transfer_cb` crash record. The crash handler from `4a8359f` will
  log it if it happens.

## Device state left behind
`STAGE2_CAPTURE_GUARD=1` remains set in `/app/bin/pgphoto` (line 22, added by sed
on the device). This is a runtime toggle outside the FwPkt build; if a future
install re-extracts the wrapper it disappears with it. Deliberate decision for the
operator: keep it for field use (guard ON is the intended behaviour), or revert
with `sed -i '/STAGE2_CAPTURE_GUARD/d' /app/bin/pgphoto` + daemon restart.
