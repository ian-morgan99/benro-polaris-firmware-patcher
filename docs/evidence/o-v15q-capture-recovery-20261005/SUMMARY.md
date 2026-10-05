# o-v15q capture recovery and Bulb duration defect — 2026-10-05

Device: Polaris `6.0.0.54.54` (build `o-v15q`), K-3 III `25fb:0189` present.
Host re-associated to `polaris_d13e86` at 07:03 UTC; the device had also
power-cycled independently (uptime 282 s at first contact).

## 1. Manual capture works on a clean boot — #172 is not a code regression

`canary-probe.py --shot --expected-files 1` on the freshly booted device:

```
CAMERA manufacturer:ricoh imaging company, ltd.;model:pentax k-3 mark iii;state:1;...
DONE states=[1, 4] files=['/app/sd/normal/SP_0177.dng', '/app/sd/normal/SP_0177.jpg']
```

Repeated 11 times back to back (SP_0177 … SP_0187), then again later
(SP_0196). Every shot returned the full `state:1 → 4 → 0` lifecycle with both
files. No degradation across the run.

Device health after the soak (uptime 557 s):

```
MemAvailable: 1442308 kB
pgphoto pid=1008 fd=11 threads=7      # no fd or thread growth
```

So `o-v15q` **is** capture-qualified for Manual on a clean boot. The first
confirmed files since Oct 2 now exist.

## 2. #172 root cause: an orphaned camera-side transfer candidate

The refusal reason we had never captured is present in the rotated logs on the
SD card (`/app/sd/system/log/Clog_NNNNNN.log`):

```
[pentax-recovery] capture=1 path=pre-shutter reason=transfer-candidate-available
  ptp=0x2001 size=576 field32=0x00000001 field36=0x00000001 field104=0x00000000
  accepted=0 action=recover-output-with-ownership;preserve-candidate;
  recover-output-with-ownership; never-delete-or-shoot-over-it
```

Aggregated across the retained rotated logs (verbatim lines in
`refusal-reasons.txt`):

| path | reason | count |
| --- | --- | --- |
| `recovery-probe` | `transfer-candidate-available` | 15 |
| `pre-shutter` | `transfer-candidate-available` | 4 |
| `publication` | `output-obligation-unresolved` | 1 |
| `pre-shutter` | `output-obligation-unresolved` | 1 |
| `cleanup` | `candidate-preserved` | 1 |

`field36` is the Pentax pending-transfer-candidate field. It reads `0x00000001`
while `field104` (activity) is `0x00000000`: the camera is idle but still holds
one un-transferred image from an earlier session. `ptp=0x2001` is `PTP_RC_OK`,
so the readiness read itself succeeded — the guard is reporting real camera
state, not a transport fault.

This is exactly the `pending-candidate` row of
`docs/PENTAX-CAPTURE-RECOVERY.md`:

> A prior image has no proven request-generation owner. Preserve it; recover or
> transfer through a generation-aware owner path. Until that path exists, leave
> capture blocked.

The guard is therefore **correct**, and the failure is the absence of an owner
path that can drain an orphaned candidate. It also explains every observation
from the physical test:

* it appears only after a session has left a candidate behind, so a reboot
  "fixes" it (a fresh PTP session drops the candidate) — matching that capture
  worked again immediately after the device rebooted;
* it is refused before `InitiateCapture`, hence the 0.3 s `state:1 → -1005`
  with no file;
* it is per-camera state, not per-process, so restarting pgphoto does not clear
  it (and, per #146, restarting pgphoto drops the camera off USB instead).

**Not yet proven:** which operation orphaned the candidate. The `publication →
output-obligation-unresolved` line immediately preceding it in
`Clog_000240.log` is the prime suspect: a RAW+JPEG capture that published one
member and left the companion as a candidate.

## 3. New defect: the Bulb duration is ignored (all durations expose 2 s)

`bulb:N` on code 264 returns a successful lifecycle and two files for every
value, but the camera exposes the same 2 s every time. Read from the JPEG EXIF
of the files the tests produced:

| request | wall clock | camera `ExposureTime` |
| --- | --- | --- |
| `bulb:3` (SP_0188, SP_0191, SP_0193) | 8.4 s | **2.0 s** |
| `bulb:8` (SP_0192, SP_0194) | 10.3 s | **2.0 s** |
| `bulb:20` (SP_0195) | 9.5 s | **2.0 s** |

A real 20 s exposure cannot complete in 9.5 s of wall clock, so the duration is
genuinely not being applied — this is not a reporting artefact.

The camera's shutter setting at the time was index 42, which command 268
reports as `00-02` — i.e. 2 s. The exposure follows the camera's shutter
setting, not `bulb:N`:

```
268@RD:0;V:42;R:1/8000,...,00-25,00-30,
```

This is consistent with the library design: `PENTAX_CAPTURE_TIMED` deliberately
issues release mode 0 and comments that "the camera owns the configured exposure
duration". Nothing in the Polaris path ever configures that duration, so
`bulb:N` is accepted, echoed as success, and silently discarded. **A Bulb shot
that reports success at the wrong exposure is worse than one that fails.**

## 4. New defect: command 277 never answers, so the shutter cannot be set

> **SUPERSEDED (2026-10-05).** 277 is `camera_set_aperture`, not a shutter
> setter; the real command is **261 with `s:<index>;`**, which does reply
> (`RX 261@s:44;ret:0;`). "277 never replies" was our client bug, not a
> firmware defect. See `docs/evidence/bulb-root-cause-20261005/SUMMARY.md`.
> The observation in this section is kept as recorded at the time.

The canary cannot even reach the Bulb path, because command 268 exposes no
Bulb entry (its list stops at `00-30`):

```
FAIL RuntimeError: could not identify exactly one Bulb option in command 268 R
list: matches=[] options=[... '00-25', '00-30']
```

Bypassing discovery and setting the shutter directly, command 277 produces no
reply at all and the setting does not change:

```
BEFORE_V 42 00-02
SENDING_277 idx=44
TX 1&277&2&shutter:44;#
GOT 525 Tempa509ca361a0000235a ;      # unrelated telemetry
NO_MORE TimeoutError
AFTER_V 42 00-02                        # unchanged
```

No `277@` response exists anywhere in the retained evidence, and no
`BULB shutter_index=` success line exists either — so the canary's Bulb path
has never actually run, and the "explicit command-277 `ret:0`" requirement in
`docs/CURRENT-STATE.md` has never been satisfied on hardware.

## 5. Why we could not see any of this: the log we were reading is a lie

`/app/Clog.txt` is rotated by the stock firmware by **truncating the same
inode** while pgphoto keeps writing at its old offset:

```
path_inode=460 size=85848 fd_inode=460 fd_pos=115212
path_inode=460 size=91104 fd_inode=460 fd_pos=115212
path_inode=460 size=1752  fd_inode=460 fd_pos=115212
```

The parent's next write lands at 115 KB in a 1 KB file, so its output goes into
a sparse hole and is cut away by the next rotation. Grepping `/app/Clog.txt`
for `pentax` returns 0 even though the capture path demonstrably emits it
(`fd_pos` advanced 87223 → 115212 across one successful shot). The real
diagnostics are only in `/app/sd/system/log/Clog_NNNNNN.log`.

Every previous conclusion drawn from `/app/Clog.txt` — including "the loader
re-initialises in-process" — must be re-checked against the SD copies.

## 6. #160 churn, quantified

Loader initialisations per retained rotated log:

| file | loader blocks | size |
| --- | --- | --- |
| `Clog_000240.log` | 214 | 400 KB |
| `Clog_000241.log` | 86 | 91 KB |
| `Clog_000242.log` | 15 743 | 23.8 MB |
| `Clog_000243.log` | 6 315 | 5.7 MB |
| `Clog_000244.log` | **48 150** | 42.2 MB |
| `Clog_000246.log` | 3 993 | 4.5 MB |

48 150 loader blocks in one rotation window. This confirms the earlier
correction: they are short-lived child processes inheriting `LD_PRELOAD`, not
in-process re-init, and the volume is far larger than previously estimated.

### The child is now named: the USB supervisor's own polling loop

A 1 Hz `/proc` scan misses sub-second children, so a high-rate probe during a
capture was used instead. It found the spawner immediately — it is the USB
supervisor (pid 425), not pgphoto:

```
pid=1925 ppid=425 comm=(sleep)
pid=1952 ppid=425 comm=(camera_usb_supe)
pid=1970 ppid=425 comm=(sleep)
pid=2034 ppid=425 comm=(camera_usb_supe)
...
```

Direct count: **10 distinct supervisor children in a 10 s window** (a floor,
given 1 Hz sampling). The chain is:

1. `pgphoto.wrapper.in:11` exports `LD_PRELOAD=$D/libpolaris_stage2.so`.
2. `pgphoto.wrapper.in:155` starts the supervisor from that same shell, so it
   inherits the preload — confirmed in `/proc/425/environ`.
3. The supervisor polls every `POLL_SECS=1` (`camera_usb_supervisor.sh:10`,
   `:150`) and forks `tr`/`cat`/`awk`/`ls`/`sleep` each poll. Those inherit it
   too — confirmed: `CHILD pid=4965 comm=sleep preload=1`.
4. `stage2_ondisk_init()` is an ELF `constructor` (`stage2_loader.c:1444`) that
   prints its 13-line banner unconditionally.

So a shell `sleep` prints the full loader banner once per second, forever. That
is the entire "re-init storm" — not libgphoto2 re-initialising, and not a
per-request capture child. At 13 lines per child this is ~780 lines/min,
consistent with 48 150 banners in one window.

Fix applied here: the wrapper now launches the supervisor with `LD_PRELOAD`
unset in a subshell, so pgphoto keeps the interposition and the supervisor does
not. `container/test_pgphoto_wrapper_lock.sh` asserts both halves (pgphoto still
receives the preload, the supervisor reports `UNSET`); it fails with exit 1 on
the pre-fix wrapper and passes on the fixed one.

Deliberately not done: gating the constructor banner itself. It is the
crash-diagnostics path, and the flood has one cause that is now removed at
source. If a future build reintroduces a preloaded short-lived process, the
banner will flood again — that is the point at which a debug gate would earn its
keep.

## 7. Process observations

* `camera_usb_supervisor.sh` runs as pid 425, reparented to init (ppid 1) — it
  is alive, but detached from pgphoto, so a pgphoto restart cannot reap or
  restart it.
* pgphoto (pid 1008) holds one unreaped **zombie** child, pid 1023, also named
  `camera_usb_supe`, created at uptime 62 s. A second supervisor instance was
  spawned and left unreaped.
* No other child processes appear across 16 one-second `/proc` samples taken
  while driving API load, so the loader blocks are not long-lived children of
  pgphoto or `polestar_app`.

## 8. Next steps

1. **#172** — implement the orphaned-candidate owner path (drain `field36`
   through the existing generation-aware recovery instead of blocking forever).
   Until then, the operator-level workaround is a camera power cycle, not a
   pgphoto restart.
2. **Bulb** — decide the owning layer for the duration: either set the camera
   shutter to the requested duration before `InitiateCapture`, or reject
   `bulb:N` explicitly instead of returning success at 2 s.
3. **277** — find why the shutter-set command never replies; nothing can
   change the exposure while it is silent.
4. **Logging** — stop reading `/app/Clog.txt`; use the SD rotated logs, or give
   pgphoto its own append-only log that the stock rotator does not truncate.
5. Re-verify the 11-shot Manual result on the next boot to confirm the
   clean-boot baseline is repeatable rather than a one-off.
