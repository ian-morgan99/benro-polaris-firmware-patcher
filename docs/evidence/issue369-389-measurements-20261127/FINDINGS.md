# #369 / #389 — measured on the shipped v118 artifacts (o-v15r, K-1 II)

Date 2026-11-27, ~08:27–08:34 UTC. Interventions permitted pre-v200 per maintainer
direction; every intervention was restored and health re-verified afterwards.

**What was measured, and how.** Stopped `camera_usb_supervisor.sh` with SIGSTOP (so it
could not restart pgphoto mid-run), stopped pgphoto to release the USB device, then ran
`/app/bin/gphoto2 --debug` against **our** driver via
`LD_LIBRARY_PATH=/app/lib/stage2`, `CAMLIBS=/app/lib/stage2/libgphoto2/2.5.34`,
`IOLIBS=/app/lib/stage2/libgphoto2_port/0.12.2`. Counted `Sending PTP_OC 0x…` lines and
used the debug stream's own relative timestamps for durations. Restored with SIGCONT plus
`/app/restart_gphoto` on an `EXIT` trap, so restore runs even on failure.

Artifacts under test (unchanged, read before and after):
`libpolaris_stage2.so ec18c164…`, `stage2/libgphoto2.so.6 cefa7b39…`, provenance
`git_commit=f48a05e0`, `patcher_commit=858edfd87`, `build_id=astro-v118-stage2-gate-wedge-fix-20261126`.

Raw debug streams: [`raw/ptp-evidence.tgz`](raw/ptp-evidence.tgz),
sha256 `01360b90bd83324bebec443e0133216b0e5385fd46fbcd8fdf8864c5379bbf49` (verified equal on
both ends of the transfer). Three runs: `ptpcount-20261127-082745`, `fresh-20261127-083056`,
`vendor-20261127-083214`.

**Caveat that bounds every conclusion below.** These are CLI calls into our driver, not pgphoto
calls. The driver-side behaviour is the same code path pgphoto reaches through the slot
trampoline, so op counts and per-op timings transfer. What does **not** transfer is pgphoto's
*call pattern* — how many reads it issues, in what key format, and whether it reuses a session.
That is measured separately from Clog (100 section-qualified lookups/boot, 50 distinct keys).

---

## 1. Headline: the leaf read is already cheap in ops; 91 % of its wall time is two vendor-mode round-trips

`--get-config iso`, three independent fresh sessions:

| Session | Duration | PTP ops |
|---|---|---|
| 1 | 2.240 s | 13 |
| 2 | 2.187 s | 13 |
| 3 | 2.188 s | 13 |

Op breakdown (identical every session):

```
3 x 0x1007 Get object handles      2 x 0x9001 vendor mode (enable + disable)
2 x 0x1001 Get device info          1 x 0x900f GetAllConditions
1 x 0x1014 Get device prop desc     1 x 0x1015 Get device prop value
1 x 0x1004 Get storage IDs          1 x 0x1002 Open session, 1 x 0x1003 Close session
```

**One descriptor, one value.** The `MODE_SINGLE_GET` leaf filter at config.c:15831/15893 works
exactly as the maintainer's source reading predicted. There is no 30-descriptor walk on a leaf
read. #389's original "62 ops per single-widget read" is refuted directly, not by control flow
alone but by counting.

Where the 2.25 s goes — from the debug timestamps in session 1:

```
0.089760  send 0x900f (GetAllConditions)
0.090194  0x900f FAILED: PTP Unknown Vendor Code (0x2017)
0.090220  pentax_reconcile_reused_session [library.c:11845]: GetAllConditions unreadable; marking...
0.090249  send 0x9001 (vendor mode enable)
0.090445  gp_port_read: Reading 1024 bytes from port...
1.618770  gp_port_read: Read 20 = 0x14 out of 1024 bytes      <-- blocked 1.528 s
1.618966  send 0x1001 ...walk continues, all sub-millisecond...
1.732451  send 0x9001 (vendor mode disable)
1.732774  gp_port_read: Reading 1024 bytes from port...
2.236070  gp_port_read: Read 20 = 0x14 out of 1024 bytes      <-- blocked 0.504 s
2.236210  send 0x1003 (Close session)
```

Two gaps account for **2.032 s of 2.240 s = 90.7 %**. Every actual widget operation in between is
sub-millisecond. The body spends **~1.528 s** to answer the vendor-mode enable and **~0.504 s** to
answer the disable. Both measured send→response, not send→next-send. Reproduced across runs:
enable response read at 1.618770 / 1.621823 / 1.621470 / 1.621651 against sends at ~0.090, and
disable send 1.732451 → response 2.236070 in the `vendor-` run.

**This revives a figure I retracted on 23 November.** I had claimed `PTP_OC 0x9001` ≈ 1.534 s and
then retracted it because it came from a window where the camera was timing out. Measured now on a
responsive body, four sessions, consistent to ±0.004 s: **the enable round-trip is ~1.528–1.532 s.**
The original number was right; the retraction was over-cautious. I am restating it only because it
is now independently reproduced on healthy hardware, with raw logs retained.

## 2. Repeated reads are already free — so descriptor caching (action 3a) and coalescing (3d) are not the lever

| Pattern | Ops | Duration | Descriptors fetched |
|---|---|---|---|
| 1 leaf, fresh session | 13 | 2.25 s | 1 |
| **4× the same leaf, one session** | **13** | 2.275 s | **1** |
| 2 distinct leaves, one session | 14 | 2.253 s | 2 |
| 4 distinct leaves, one session | 16 | 2.604 s | 4 |

Four reads of `iso` in one process cost **exactly the same 13 ops as one read** — the existing
`params->dpd_cache` already serves them, and the value is not refetched either. Marginal cost of a
*distinct* property is ~1 op and ~0.1 s.

Consequence for the required actions: a capability/choice cache (3a) and request coalescing (3d)
would change nothing measurable on this path. The cache the TA asked for **already exists in the
driver and already works**. What is missing is not a cache — it is session reuse, because the
2.04 s vendor-mode cost is paid **per process**, not per read.

## 3. The failed section-qualified lookup costs zero ops; the walk is a second call by the caller (action 3b)

`--get-config /main/imgsettings/iso`: 63 ops, 8.45 s, returns the same value (`ISO Speed = 200`).
Splitting the debug stream at the failure line:

```
failure logged at dbg line 399: gp_camera_get_single_config [gphoto2-camera.c:900]:
                                '...get_single_config ( camera, name, widget, context)' failed: -2
0x1014 ops BEFORE that line:  0
0x1014 ops AFTER  that line: 30
```

`GP_ERROR_BAD_PARAMETERS = -2` (`libgphoto2_port/gphoto2/gphoto2-port-result.h:38`), so this is
config.c:16173 firing exactly as predicted. The failed lookup itself issues **no PTP traffic at
all** — the leaf filter skips everything before any op is sent. Then `_get_config` immediately
begins walking (`Getting function prop 'Drive Pentax focus near (minimum)' …`), 30 descriptors and
18 values later finishing in 8.45 s.

So the expensive part is **not** a driver-internal fallback — there is no internal retry. It is a
*second* enumeration call made by whoever asked for the section-qualified key. In this harness that
is the gphoto2 CLI; on the appliance it is pgphoto, which issues 100 such lookups per boot (50
distinct keys, measured from Clog). Action 3b therefore cannot be delivered by patching config.c:
the driver already does the cheap thing. It has to be fixed at the caller's key format, or absorbed
at our shim by rewriting a section-qualified name to its leaf before calling through.

## 4. GetAllConditions ordering — directly relevant to action 3c

`0x900f` **fails with PTP error 0x2017** when the driver probes it during
`pentax_reconcile_reused_session` at init, i.e. *before* vendor mode is enabled:

```
0.089760 send 0x900f  ->  0.090194 FAILED PTP Unknown Vendor Code (0x2017)
0.090220 reconciliation: GetAllConditions unreadable; marking session recovery-required
```

After vendor mode is on, the same opcode succeeds: in the full-walk run,
`_get_Pentax_Conditions (2): Pentax conditions response: 576 bytes` at 1.736261.

Two consequences for 3c ("one fresh GetAllConditions snapshot per logical refresh"):

1. A snapshot is only obtainable **after** `0x9001`. Any cache keyed on it must be populated post
   enable, and the driver's own init-time probe will always fail on this body/configuration — that
   failure is expected ordering, not a fault.
2. In the leaf-read path there is exactly one `0x900f` and it is the failing init probe. Leaf reads
   never obtain conditions at all. So "serve current values from one snapshot" cannot be layered
   onto the leaf path without first moving the probe after enable — which changes when
   `recovery-required` gets set, and that interacts with capture admission (#347). Not a free change.

## 5. What this changes about the required actions

| Action | Assumed premise | Measured reality | Revised disposition |
|---|---|---|---|
| 3a resolve capabilities/choices once per session generation | descriptors refetched per read | already cached; 4 identical reads = 13 ops = 1 descriptor | **Not a lever.** No measurable gain available on the leaf path |
| 3b avoid redundant full-tree fallback | driver rebuilds tree on failed lookup | failed lookup issues **0 ops**; caller makes a second full call | **Re-scoped**: fix at caller key format, or rewrite qualified→leaf in our shim. config.c needs no change |
| 3c one fresh GetAllConditions snapshot per refresh | snapshot cheap and available | `0x900f` returns 0x2017 until vendor mode is enabled; leaf path never gets conditions | **Blocked on ordering**, not on code. Must move probe post-enable, which touches #347 admission logic |
| 3d coalesce duplicate pending reads | duplicates cost ops | duplicates are free within a session | **Not a lever** |
| — the actual lever | (not in the action list) | 2.03 s of vendor-mode enable/disable **per process**, 90.7 % of leaf latency | **Session reuse.** A persistent reader pays 1.53 s once instead of per invocation |

The single highest-value change is not in the four actions: keep one camera session open and
service reads through it, so the vendor-mode round-trips are paid once at startup rather than on
every read. That is a consumer-boundary change in our loader shim (or a daemon), not a driver
change, and it does not require patching pgphoto.

## 6. Intervention record and restoration

| Time (UTC) | Action | Restore | Verified |
|---|---|---|---|
| 08:27:45 | SIGSTOP supervisor pid 276 | SIGCONT at 08:28:10 | resumed |
| 08:27:46 | TERM pgphoto pid 249 (released `/dev/bus/usb/*/*`) | `/app/restart_gphoto` | new pid 4795, device bound, `camera_connected_to_app` logged |
| 08:30:56–08:31:03 | same pattern, run 2 | trap restore | new pid 10884, device bound |
| 08:32:18–08:32:22 | same pattern, run 3 | trap restore | new pid 13735, device bound |

Final state verified: supervisor 276 running, pgphoto 13735 running, `fuser /dev/bus/usb/*/*` →
13735. No artifact was modified; nothing was deployed. All three runs left the appliance in the
state it was found, with a fresh pgphoto session bound to the same camera identity.

## 7. Reproduction of the headline numbers

A second independent run (`anom-20261127-084205`) reproduced both figures:

| Key | rc | ops | duration |
|---|---|---|---|
| `iso` (leaf) | 0 | **13** | 2.217 s |
| `/main/imgsettings/iso` (section-qualified) | 0 | **63** | 8.274 s |

An intermediate run appeared to show `ops=0` for the section-qualified key, which would have
contradicted §3. It was a bug in my own script: the key contains `/`, and I used it directly as
an output filename, so the debug file never existed and `grep -c` on a missing path returned 0.
Caught by re-measuring rather than reported. Fixed script uses fixed filenames.

## 8. The mode-change freshness test is INCONCLUSIVE — and cannot be done from software at all

This is the #316-class correctness gate for any caching change, so I attempted it three times.
All three are inconclusive, and the reason is worth recording precisely.

**Attempt 1 (`stale-20261127-083619`) — invalid, my error.** I ran
`--get-config drivemode --get-config shutterspeed --set-config drivemode=Bulb …`. The debug stream
contains **zero** `gp_camera_set_config` calls and only three `get_single_config` calls: `drivemode`
is not a valid leaf name, so the set never happened. The three shutter reads all returned 56
identical choices — which proves nothing, because no mode change occurred. My first pass also
reported "0 fractional choices", which was a broken regex: the enum plainly contains `1/6400`,
`1/8000`. Both errors were mine and are recorded rather than dropped.

**Attempt 2 (`stale2-…`) — aborted by its own precondition check.** `--list-config` returns
section-qualified keys, so my leaf-name match for a drive-mode key found none and the script exited
before touching anything. (Side observation: `--list-config` output does **not** round-trip as a
leaf name — it is already section-qualified, which is where the 100-per-boot expensive pattern
comes from.)

**Attempt 3 (`stale3-20261127-083945`) — inconclusive for a real reason.** Correct key found:
`pentaxdrivemode`, current value `single`, 23 choices. Setting it to `Bulb` fails:

```
*** Error ***  Failed to set new configuration value Bulb for configuration entry pentaxdrivemode.
*** Error (-2: 'Bad parameters') ***
```

Because `Bulb` is not a drive mode on this body. The 23 choices are
`single, interval, interval-movie, unknown-3, continuous-hi/mid/lo, self-timer-12s, self-timer-2s,
remote, remote-3s, remote-cont, mirror-up, mirror-up-remote, unknown-14, multi-exposure,
unknown-16..21, self-timer-cont` — no Bulb. On Pentax, **Bulb is an exposure mode**, and there is
no exposure-mode setter among the 52 enumerated keys (`/main/actions/bulb` is a capture *action*,
not a mode switch).

**Consequence.** The shutter-enum staleness question cannot be answered through gphoto2 at all on
this driver. Reproducing "in Bulb the shutter enum contains only `mm:ss` values" requires someone to
**turn the mode dial on the body by hand**. That is an operator action, not an access or rig problem,
and it is the concrete blocker for validating any descriptor cache against #316. Recorded as such.

What attempt 3 did establish incidentally: a session doing 3 shutter reads plus one failed set issued
**82** `0x1014` fetches — consistent with each fresh process paying a full enumeration, not with
per-read refetching.

## 9. What is still not measured

- **pgphoto's own call pattern** — whether it reuses one session or opens one per settings request.
  The 170/375 CONFIG-vs-CONFIG refusals from `deal_camera_control_handler` (commit `4f38e814`) hint
  at serialised settings requests, but that is queue time, not op count. Needs Clog with the read
  path instrumented, or a counted run while pgphoto is the caller.
- **Mode-change freshness** — see §8: needs the dial turned by hand; no software path exists.
- **K-3 III.** Only `25fb:0183` has ever appeared in `usb-watch.log` (720 sightings, no other
  Pentax ID). Cross-model confirmation is impossible until it is cabled.

## 10. Second evidence batch

[`raw/ptp-evidence2.tgz`](raw/ptp-evidence2.tgz), sha256
`55d32d625bcacc89540d14b5337c54b3a0146a8e258b88496b0d6125c6a28b1a`, hash-verified equal on both
ends. Contains the three inconclusive staleness runs and the reproduction run. Final appliance
state verified after every run: supervisor running, pgphoto running (last observed pid 994),
`fuser /dev/bus/usb/*/*` returning that pid. Drive mode left at its original value `single`.
