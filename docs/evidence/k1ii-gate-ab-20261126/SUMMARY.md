# K-1 II live qualification — v117 gate fix, correctly attributed

Date: 2026-11-26. Device `192.168.0.1`, FwVer `6.0.0.54.117;date:2026.11.25`,
K-1 II on USB as `25fb:0183`, recognised as
`model:pentax k-1 mark ii;state:1;storage:2;photoFormat:1`.

Two loaders were compared by hot-swapping `/app/lib/stage2/libpolaris_stage2.so`
and **rebooting between measurements**:

| label | md5 | origin |
|---|---|---|
| ORIGINAL (as shipped v117) | `765e9528b8d2dddaeb0d25f6ed54e977` | on-device backup, byte-identical to a container rebuild of the pre-fix source |
| FIXED | `44fb2150ab04c164859c65ec932a8a58` | rebuilt from `main` with the gate fix + `held_ms` diagnostic fix |

Both were built inside `polaris-patcher:latest`
(`arm-linux-gnueabi-gcc (Debian 6.3.0-18)`). The pre-fix source rebuilt there is
byte-identical to the deployed binary, which proves the slot table and build
recipe are exactly right and a rebuild is a genuine drop-in.

## Why rebooting is mandatory, and the invalid result it exposed

pgphoto binds the USB camera during boot-time session setup. Killing and
relaunching it by hand leaves the process running but **unbound**: code 286
answers `model:none;state:-2`, and every config read then blocks until its
deadline. That looks exactly like the admission-gate wedge.

An earlier A/B run reported ORIGINAL failing 240/240 reads while FIXED passed
240/240. **That result is retracted.** It measured an uninitialised head, not a
gate difference. `scripts/gate-ab.sh` now reboots between swaps, and
`scripts/stress-config-gate.py` refuses to report a verdict when the handshake
shows an unbound session.

A second attribution error was caught the same way: capture, bulb and live-view
tests were first run while `gate-ab.sh` had last installed **ORIGINAL**, so those
results described v117, not the fix. They were re-run on a clean FIXED boot; the
numbers below are from that boot.

## Results on FIXED, clean boot, camera bound (usb_fds=1, 7 threads)

| symptom | result | evidence |
|---|---|---|
| parameters at app-like load | **PASS** | 2 clients x 15 rounds x 5 codes = 150 reads: `ok=150 sentinel=0 empty=0 timeouts=0`, refusals delta 0, p50 0.05 s, p95 0.24 s |
| parameters at 8-way hammering | pre-existing saturation | `ok=232 empty=8`, identical on ORIGINAL; the 8 are `RD:0;V:;R:;` (empty), **not** the `-1` sentinel |
| plain capture | **PASS** | `--shot --expected-files 1` -> lifecycle `[1,4,0]`, real file `/app/sd/normal/SP_0009.jpg`, 350 940 bytes |
| live view | **frames do not flow** | code 291 open `state:1;ret:0`, close `state:0;ret:0`, but 0 frames over 9090 in 10 s; port 8080 is MJPG-Streamer answering `501 Not Implemented` |
| bulb | **FAIL** | app request `264 state:1;bulb:5;c:-1;` -> `state:-1` after 142.8 s, expected `/app/sd/normal/SP_0010.jpg` never written |

So the gate fix resolves parameter reads and plain capture on real hardware. It
does **not** resolve live view or bulb; those are separate defects.

## What the one refusal under load actually was

With the corrected diagnostics:

```
admission refused: site=100540 kind=2 owner_site=100540 last_owner_kind=2
generation=1 camera_present=1 budget=500 tid=1088 owner_tid=2043 depth=1
held_ms=4219 stolen=0
```

A different thread (`owner_tid` 2043 vs `tid` 1088) holding a real SET for 4.2 s
against a ~1 s budget (500 polls x 2 ms). Legitimate contention, correctly
reported: not a leak, not a self-deadlock (`depth=1`, `owner_site != site`), and
no lease takeover was needed (`stolen=0`). This is why the lease stays long —
unnamed CONTROL owners such as capture hold across an exposure, so a short lease
would let two requests drive the camera at once.

## Separate defects, not the gate

**Bulb.** `capture_image_with_Bulb[3321]: blub timeout` then
`captureBulbImage ret -1`. The deployed binary already carries the issue #230
poll-budget patch — disassembled at `capture_image_with_Bulb+0x594`:

```
102060:  e3023710   movw r3, #10000     ; 10 000 x 10 ms = ~100 s file poll
```

5 s exposure + ~100 s poll matches the observed 142.8 s, yet `SP_0010.jpg` is
never written. So this is not #230's "file arrives late" case: on the K-1 II the
bulb file never arrives at all. Plain capture works in the same session, so the
difference is specific to the bulb path.

**Live view.** Preview opens and closes with `ret:0` — the gate no longer refuses
it, which was the field symptom (`updateViewFinder enable:1 ret:-1`). But no
frames reach a 9090 client. Frame delivery for the K-1 II is unresolved and needs
its own investigation; the direct-PC report in `CURRENT-STATE.md` shows five valid
preview frames from the same body, so the gap is on the packaged
pgphoto/Stage-2/session path, not libgphoto2.

## Tooling added

* `scripts/stress-config-gate.py` — concurrent read load with latency percentiles,
  refusal delta and raw-frame capture. Read-only by construction (subtype 2,
  payload `-100`); never sends a SET frame or fires the shutter. Requires the head
  handshake (284/820/823/286) and reports `camera session not initialised` rather
  than a gate verdict when 286 shows an unbound body.
* `scripts/stage2-hotswap.sh` — push / rollback / status for the loader, backing up
  once so rollback can always restore the shipped binary.
* `scripts/gate-ab.sh` — install a loader, reboot, wait for a bound camera, then
  stress. This is the only trustworthy way to A/B the gate.
