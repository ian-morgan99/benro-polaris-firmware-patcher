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

## Third defect: parameter SET is rejected on the K-1 II (`ret:-2110`)

Found while trying to put the body on B for a bulb test. The supported path
(`canary-probe.py --shot --bulb-seconds 5`) reads the shutter list correctly, then
fails to select a slot:

```
SHUTTER_OPTIONS current=15 options=[... '1/8000', '00-00']   # 56 slots, bulb = 55
FAIL RuntimeError: shutter selection lacked explicit ret:0: s:8;ret:-2110;
SHUTTER restore_failed secondary=... s:15;ret:-112;
```

Reads work (the list is complete and current), but the write is refused. This is
**not** the gate and **not** new: `-2110` is documented in
`docs/K1II-SHUTTER-HANDOVER.md`, last touched 2026-11-23, before the gate existed,
and it is not a code our loader or patches emit (only the admission unit test uses
it as a stand-in native return). The handover already records shutter changes,
ISO restores and EV writes all returning `-2110` on this body, with the original
value persisting afterwards.

Consequence for the bulb report: the app's bulb request cannot work while the body
is not on B, and the head cannot put it on B. So "bulb fails" has at least two
independent causes -- the rejected SET, plus the bulb path never producing the
expected file even when the exposure is held for the full duration.

This also explains the `RD:0;V:;R:;` empty answers seen under load: the handover
records exactly that response for code 267 alongside a `-2110` write, so it is a
pre-existing K-1 II session-state issue rather than saturation caused by the gate.

## Net position

Resolved on real hardware by the gate fix: parameter reads at app load, plain
capture, and the `updateViewFinder ret:-1` refusal. Still open, each needing its
own investigation: live-view frame delivery, bulb file production, and K-1 II
parameter SET (`-2110`).

## -2110 located: a pgphoto-internal "no local table entry" sentinel

`-2110` is not a libgphoto2 or PTP code. It appears in no gphoto2 header and nowhere
in the Pentax camlib source (the only matches under `out/.libgphoto2-v109` are the FSF
postal address, "Boston, MA 02110-1301"). It is defined inside pgphoto itself.

Disassembly of the deployed binary (`pgphoto.stage2ondisk`, md5 `79d4454f…`) finds the
constant built by `movw/movt` at two sites:

```
0001e2f8 <getLocalCameraParamInfo>:
  1e318: cmp r3, #3        ; configType <= 3      -> accepted, index = configType
  1e324: cmp r3, #7        ; configType == 7      -> accepted
  1e330: cmp r3, #8        ; configType == 8      -> accepted, index remapped to 4
  1e338: movw r3, #0xf7c2 / movt r3, #0xffff      ; otherwise -> -2110

0001e470 <getCameraConfig>:
  1e4d4: movw r3, #0xf7c2 / movt r3, #0xffff
  1e4dc: cmp r2, r3        ; test whether a callee reported -2110
  1e4e0: bne  1e538
```

So pgphoto keeps a **fixed local table of config types** -- indices 0..3, 7 and 8,
indexed by a stride of 2260 bytes from a base at +0x10c0 -- and returns -2110 when a
request has no entry. `getCameraConfig` then tests for that sentinel explicitly.

This matches the handover's observation that after a `-2110` the original value always
persists: the request is refused before any PTP set-property is issued, so the body is
never asked to change. It also explains why reads succeed while writes fail -- reads
have a driver path, writes consult the local table first.

What this does **not** yet establish: which configType the shutter SET uses and whether
its table entry is simply unpopulated for the K-1 II. The handover records
`configType 3 value:3 ret -2110`, but per the disassembly above configType 3 takes the
accepted branch of `getLocalCameraParamInfo`, so that particular rejection comes from a
different check -- most likely an empty or model-mismatched table entry rather than the
range test. Confirming which requires runtime tracing of the SET arguments, which is
the next step: the loader already shims `setCameraConfig`
(`native_set_camera_config`, container/stage2_loader.c:308), so logging key, value and
return there answers "does the request reach libgphoto2 at all" in one build and reboot.

## The empty reads: first concurrent pass after boot, not load, not one fixed code

Three characterisations were attempted here; the first two were wrong and are recorded
as such so the next reader does not repeat them.

1. "Pre-existing saturation under 8-way hammering" -- wrong. No load threshold exists;
   see the sweep below.
2. A retraction claiming they never reproduce -- also wrong. They do reproduce: three
   fresh boots, first concurrent pass gave 8, 11 and 9 empties. The retraction was based
   on passes run after the boot had already been exercised, which is exactly when they do
   not occur.
3. "Confined to code 265 (ISO)" -- also wrong, and it is corrected here rather than left
   in place. All 14 recorded non-ok samples happened to be ISO, but that is a sampling
   artifact: the harness records only the first eight non-ok frames and queries ISO first.
   A discriminator on a fresh boot, one connection per code, each connection's first read
   being that code:

   ```
   FRESH BOOT, one connection per code, first read = that code:
     iso       ok=0 EMPTY=2
     wb        ok=2 EMPTY=0
     ev        ok=2 EMPTY=0
     shutter   ok=2 EMPTY=0
     aperture  ok=0 EMPTY=2
   ```

   Aperture empties too, so it is not ISO-only. But re-running the same concurrent test on
   a boot that had already been exercised gave `iso=2ok/0empty aperture=2ok/0empty`, and a
   sequential single-connection pass gave 6 ok for every code. So the codes affected are
   not fixed either.

What the evidence actually supports, stated at the confidence it warrants:

* The empties occur on the **first concurrent pass after a fresh boot** -- three boots,
  three reproductions (8, 11, 9 of 240). They do not recur on later passes of the same
  boot, and they do not appear sequentially on a single connection.
* Which codes are affected varies between runs (ISO in every recorded sample, aperture in
  the discriminator). It is therefore a transient window affecting some subset of config
  reads, not a per-parameter fault.
* It is not load saturation: 1/2/4/8 clients x 20 rounds on an exercised boot produced
  100/200/400/800 reads with zero empties.

Combined with the SET trace, the user-visible chain is: a config read answers
`RD:0;V:;R:;` in that early window -> the head issues `setCameraConfig key=3 value=""`
-> pgphoto rejects the empty string with -2110 -> Benro Connect shows the parameter as not
applying. One upstream defect, not a broken write path.

Load sweep that disproved the saturation theory (run on an already-exercised boot):

| condition | reads | empty |
|---|---|---|
| 1 client x 20 rounds | 100 | 0 |
| 2 clients x 20 rounds | 200 | 0 |
| 4 clients x 20 rounds | 400 | 0 |
| 8 clients x 20 rounds | 800 | 0 |
| idle, sequential, clean boot | 50 | 0 |
| boot race, +14s to +41s after ssh returns | 55 | 0 |

Those passes were run on a boot that had already been stressed at least once, which is
why they came back clean; the same 8-client load on a boot's *first* pass produced 8-11
empties three times out of three. The boot-race test that saw none read sequentially from
+14 s to +41 s with a single connection, so it neither confirms nor rules out a boot window
-- the reproducing condition is concurrency on a freshly booted head.

What remains solid, because it was proven directly rather than inferred:

* An empty config value produces `-2110`. `setCameraConfig key=3 value="" ret=-2110`
  versus `key=3 value="15" ret=0`, same boot, same thread. The request reaches the core
  and succeeds when non-empty; pgphoto rejects the empty string itself.
* Therefore "parameters do not stick" reduces to one upstream defect -- an intermittent
  empty config read -- not a broken write path.

What is genuinely unresolved: what makes config reads answer `RD:0;V:;R:;` during the
first concurrent pass after boot, and why it clears afterwards. The scope is narrow -- one
boot window, reproducible on demand by rebooting then issuing concurrent reads -- so the
next step is read-boundary instrumentation (log the native get/set return per code) rather
than more load or more sampling. Recording it as open rather than dressing up a guess.

Also corrected here: `stress-config-gate.py` counted admission refusals as bad outcomes,
so a run with `ok=240 empty=0` still printed "GATE DEFECTIVE (4 bad outcome(s))". A refusal
under concurrent load is the gate correctly turning a reader away while a real SET holds the
camera -- expected behaviour, not a defect. Refusals are now reported separately from read
failures.
