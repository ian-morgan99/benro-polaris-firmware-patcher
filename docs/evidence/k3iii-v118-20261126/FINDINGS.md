# K-3 III on v118 — camera never reaches the host (blocked at USB link level)

Rig `d13e86`, firmware `astro-v118-stage2-gate-wedge-fix-20261126` (`6.0.0.54.118`), kit stamp matching,
uptime ~2727 s at first check (so the rig rebooted since the K-1 II session). Connection: **direct USB-C
cable, no hub**. Camera: Pentax K-3 III. Captured 2026-11-26.

## Answer to "is the camera connecting at all?" — No

Not at any layer. Live view cannot work because there is no camera for it to stream from; that is the whole
explanation, not a Stage-2 or preview-ownership defect.

| Layer | Result |
|---|---|
| `lsusb` | only `1a40:0101` (USB2.0 hub) and two xHCI root hubs. Pentax/Ricoh count = **0** |
| sysfs `/sys/bus/usb/devices/` | `1-0:1.0 1-1 1-1:1.0 2-0:1.0` — no child on either bus |
| Bus 002 (SuperSpeed / USB-C side) | **no children at all** |
| Port `1-1.2` (where the K-1 II lived) | empty |
| Protocol `284` / `286` (model, presence) | both return empty |
| Kernel log since boot | **zero** USB attach/disconnect events beyond the earlier K-1 II pair |
| All 40 log files on the rig | **no `k-3` string anywhere** — this body has never enumerated here |

The supervisor's own verdict is consistent and correct:

```text
[camera-usb] 1-1.2|25fb:0183|1:3 has not re-enumerated for 30 polls (poll 685);
             pgphoto has no device to bind and will not recover
```

That is it reporting the K-1 II's absence, which is true.

## Two claims I made and were wrong about — both refuted by reading our own code

**1. "The supervisor latches to the old camera, so a swapped-in K-3 III would never be accepted."** Wrong.
`container/ondisk/camera_usb_supervisor.sh`:

- `camera_vendor()` accepts vendor `25fb` **generically** — any Ricoh/Pentax product, not a pinned one.
- The issue #126 comment says the opposite of what I asserted: *"a body replacement (different product) or
  disappearance (empty) also changes it → fresh-session / rebind path."*
- `already_bound_k3iii()` already knows `25fb:0189`, i.e. the K-3 III's product ID is anticipated.

I inferred a defect from a log line without reading the code that produced it. The `camera_absent` message
is correct behaviour, and there is no latch bug.

**2. "USB autosuspend is hiding the camera."** Wrong. `autosuspend=2` with every hub on `control=auto` looked
convincing, so I wrote `on` to `usb1/power/control` and `1-1/power/control`. The hub went
`runtime=suspended → active` and **still enumerated nothing**. Autosuspend was a red herring.

## CABLE HYPOTHESIS REFUTED — the body and cable are both fine

The same body on the **same new cable** into this workstation enumerates immediately:

```text
Bus 001 Device 005: ID 25fb:0189 Pentax Ricoh Imaging Co., Ltd PENTAX K-3 Mark III
/sys/bus/usb/devices/1-4  ->  480M, interface class 06 (still-image), driver=[none]  (normal for PTP)
gphoto2 --auto-detect     ->  USB PTP Class Camera   usb:001,005
```

So my "charge-only cable / no data pair" conclusion was **wrong**. The cable carries data, the body presents
a PTP interface, and it negotiates **480 M high-speed** — exactly the speed the K-1 II used on the rig. That
also means SuperSpeed negotiation is irrelevant here; bus 002 being empty on the rig is not the cause.

## Driver support CONFIRMED — my earlier reading was wrong too

I said the driver might not know `0x0189`. It does. I had grepped `camlibs/pentax/library.c`; the PTP table
is in `camlibs/ptp2/library.c`:

```c
{"Pentax:K-3 Mark III (MTP mode)",      0x25fb, 0x0189, 0},
```

plus explicit handling in `camlibs/ptp2/pentax-utils.c` (`model_no == PENTAX_MODEL_K3_MARK_III && usb_product
== 0x0189`), and `camlibs/pentax/pslr_model.c:1010` carries `{ 0x13254, "K-3III", ... }`. The K-1 II row at
`0x0183` is my own earlier note documenting the MSC/PTP PID-pair convention. So nothing about the driver
explains the failure, and USB mode is not an enumeration blocker either — the body presents `0x0189` with a
still-image interface regardless of host.

## Rig-side state after the cable was ruled out

- `echo 1-1 > .../usb/unbind` then `bind` **succeeded** (unlike the earlier `reset`, which was permission
  denied) and still enumerated nothing.
- `dmesg` since boot: **no xHCI or USB errors at all** — only unrelated `CFG80211` WiFi noise. So the stack is
  not logging a fault; it simply never sees a connection event on that port.
- The hub (`1a40:0101`) currently has no children; the K-1 II occupied `1-1.2` about an hour earlier, so the
  port itself was working recently.

## Ranked causes remaining (rig-side)

1. **Different physical port.** The K-1 II worked on hub port `1-1.2`. If the USB-C cable went into another
   socket, that one may be dead or not routed to this controller. *Test: use the exact port the K-1 II used.*
2. **Power budget.** Everything hangs off a bus-powered hub; the K-3 III may draw more than that port will
   supply. Usually this logs an error, and none is logged, so this is lower confidence.
3. **Wedged USB stack** after the K-1 II's removal — no evidence for it (no errors), but a reboot is cheap and
   would clear it.

Do not re-open the cable, driver, autosuspend, or supervisor-latch theories; all four are now closed.

## Port ruled out too — there is only one camera socket

The operator confirms the cable is in **the exact same socket** the K-1 II used, and the Polaris has only one
camera port. So "wrong physical port" — my top-ranked cause — is eliminated. `authorized_default=1` on both
buses and `authorized=1` on the hub rule out a policy refusal. No TypeC role sysfs exists on this kernel, so
a host/peripheral role flip cannot be confirmed or excluded from sysfs.

## The Benro Connect toasts are NOT a flapping connection

Sampled all three layers simultaneously for 60 s while the app was visibly toasting:

```text
t=5s..t=60s  pgphoto_pid=250  usb_pentax=0  dmesg_lines=545  284=[EMPTY]
```

Constant on every sample. pgphoto is **not restarting** (same PID throughout, and no `restart` markers in
Mlog), the kernel sees **no** attach/disconnect churn (`dmesg_lines` never moves from 545), and USB presence
never flickers. Nothing is actually reconnecting or disconnecting.

What *is* periodic is the app's own camera poll, every ~30 s:

```text
[18:39:48] code[286],val[manufacturer:none;model:none;state:-5;stor...
[18:40:18] code[286],val[manufacturer:none;model:none;state:-5;stor...
[18:40:48] code[286],val[manufacturer:none;model:none;state:-5;stor...
[18:41:18] code[286],val[manufacturer:none;model:none;state:-5;stor...
[18:41:49] code[286],val[manufacturer:none;model:none;state:-5;stor...
```

Exactly 30 s apart, always `model:none; state:-5`. So the toasts are the app re-evaluating a steady-state
"no camera" answer on each poll and surfacing it as connect/disconnect churn. The toast cadence matches the
poll cadence. This is a **reporting artefact of an absent camera**, not evidence of an unstable link — and
it should not be chased as a Stage-2, socket, or preview bug.

Caveat: the toast logic itself lives in the mobile app, which is not in these logs, so this is inferred from
the poll cadence matching the observed toast frequency rather than directly observed.

## Correction: the `SP_ClientCtxDel` churn was largely my own probing

I previously proposed this as a new vendor socket-lifecycle race and called it "the best device-side candidate
for the client dropouts". Wrong. The pairs are from **192.168.0.4 — this workstation**, i.e. my own `nc`
probes:

```text
SOCKET_ACCEPT(201) [id=96 192.168.0.4:39950] s_u32ClientNum[4]
SOCKET_CLOSE(201)  [id=96] s_u32ClientNum[3]
ERROR SP_ClientCtxDel[392]: not find this is id[96]
```

Open and close in the same millisecond is exactly what a one-shot `printf | nc -q1` does. The 307 occurrences
in the K-1 II bundle accumulated during a session in which I was probing heavily, so that count is mostly
self-inflicted. Before filing anything on it, re-count with no probes running and see whether it still occurs
from genuine clients (phone/tablet IPs).

## Autosuspend: my first refutation was invalid; the second one is sound

My earlier claim that autosuspend was ruled out was based on a **flawed test**. I wrote `on` to
`usb1/power/control` and `1-1/power/control`, then enumerated — but with `autosuspend=2` in force the hub
reverted to `control=auto` and re-suspended within ~2 s, before my enumeration ran. Later inspection confirms
this: `usb1 control=on` persisted while `usb2` and `1-1` were back to `control=auto runtime=suspended`. So I
was enumerating a hub that had gone back to sleep, and the "still nothing" result proved nothing.

Redone properly. `/sys/module/usbcore/parameters/autosuspend` is writable at runtime (`0644 root`), so:

```text
echo -1 > /sys/module/usbcore/parameters/autosuspend   -> autosuspend now: -1
echo on   > usb1/power/control, usb2/power/control, 1-1/power/control
after 8 s: usb1 control=on runtime=active
           usb2 control=on runtime=active
           1-1  control=on runtime=active
devices:   root hubs + 1a40:0101 only; pentax: 0
```

All three stayed awake and active for the whole window, and the body still did not enumerate. **Autosuspend
is now genuinely excluded**, with valid evidence this time. Note `autosuspend=-1` is runtime-only and will not
survive a reboot.

## Decisive non-destructive test available before rebooting

Plug the **K-1 II** back into that same socket. It enumerated there about an hour ago on `1-1.2`.

- If the K-1 II **also** fails to enumerate now → the fault is rig-wide (port or USB stack), independent of
  body. Proceed to reboot.
- If the K-1 II enumerates fine → the fault is specific to this body+cable+port combination, which would be a
  surprising result worth its own investigation, and a reboot becomes less likely to help.

This costs one cable swap and no downtime, so do it before the reboot.

## A/B RESULT — decisive: the fault is specific to this body+cable+port, not rig-wide

The K-1 II was plugged into **the same socket** with **the same cable**, in the **same power state** that the
K-3 III had just failed in (`autosuspend=-1`, `usb1/usb2/1-1` all `control=on runtime=active`). It enumerated
immediately:

```text
usb 1-1.2: new high-speed USB device number 4 using xhci-hcd
usb 1-1.2: New USB device found, idVendor=25fb, idProduct=0183
usb 1-1.2: Product: PENTAX K-1 Mark II
```

and came up fully working:

```text
[camera-usb] camera_returned: 1-1.2|25fb:0183|1:4 after 3579 absent polls (poll 4235)
[camera-usb] stable identity change: none -> 1-1.2|25fb:0183|1:4; restarting pgphoto
[restart_gphoto] OK: pgphoto PID 7435 owns the port-8080 listener - restart successful
[camera-usb] pgphoto restart complete (restart 3/6)
----- gp_camera_init ret 0
code[286],val[manufacturer:ricoh imaging company, ltd.;model:pentax k-1 mark ii;state:1;storage:2;...]
```

So the port, hub, xHCI controller, power state and Stage-2 supervisor are all healthy. This also independently
confirms my retraction of the "supervisor latch" claim — a body returning after 3579 absent polls was detected,
rebound, and pgphoto restarted correctly.

**The K-3 III has never produced a single USB connect event on this rig.** `dmesg` since boot contains exactly
4 USB connect/disconnect events, all four from the K-1 II (`Product: PENTAX K-1 Mark II` twice). The K-3 III
appears nowhere.

### Revised cause ranking

| Combination | Result |
|---|---|
| K-3 III + this cable + **workstation** | enumerates, `25fb:0189`, 480M, PTP detected |
| K-1 II + this cable + **rig port** | enumerates, `25fb:0183`, high-speed, fully working |
| K-3 III + this cable + **rig port** | **no connect event at all** |

Cable is exonerated (works with both bodies on at least one host each). The rig port works. So the failure is
the specific triple combination. Leading explanation now:

1. **Bus-powered hub current budget.** `dmesg` reports `hub 1-1:1.0: 4 ports detected` and the hub is
   bus-powered. If the K-3 III asks for more current than the hub can allocate to that port, some hubs simply
   never report a connect — no error logged, which matches exactly what is seen here. I previously ranked this
   low because "a shortfall normally logs an error"; that assumption is wrong for bus-powered hubs, and with
   every other cause now eliminated it is the leading candidate. **Test: a self-powered USB hub.**
2. **USB-C role negotiation** on this socket with this body. No typec sysfs exists on this kernel so it cannot
   be inspected; a reboot would re-run negotiation from scratch and is worth trying, though the K-1 II working
   immediately after makes a wedged stack unlikely.

A reboot is now **low expected value** — the port demonstrably works right now. Try a self-powered hub before
rebooting.

## Correction: I was monitoring the wrong process

I reported "pgphoto is not restarting (same PID throughout)" while watching `pidof polestar_app`. That is the
**vendor app**, not the camera server — pgphoto is a separate process. The supervisor log shows it restarted
correctly (`restart 3/6`, new PID 7435, `gp_camera_init ret 0`). My conclusion that nothing was flapping still
holds for the *camera link* (dmesg line count frozen at 545 during the toasts), but the pgphoto-restart half of
that reasoning was based on the wrong PID and should not be relied on.

## Config-read measurement banked while a camera is attached

`probe-config-gate.py --rounds 3` against the live K-1 II on v118:

```text
265 iso                    real V=0 options=13
266 white-balance          real V=0 options=19
267 exposure-compensation  real V=15 options=32
268 shutter-speed          real V=20 options=57
275 aperture               real V=2 options=23
refusals in Clog after probe: 0 (delta 0)
VERDICT: every parameter code answered with a real value list
```

All six rounds completed within the same second (`18:51:26` for five codes in round 3) with **zero gate
refusals**. Important caveat before reading anything into this: these are **Polaris protocol codes**, which may
be served from Stage-2's cached widget tree, whereas #389 measured a raw `gp_camera_get_config` via the gphoto2
CLI on direct-PC at 7.85 s / ~62 PTP ops. Fast protocol responses here do **not** prove #389 is fixed — they
may be measuring a different code path entirely. Closing #389 still needs a direct-PC `gp_camera_get_config`
timing run, which requires the PC-to-camera USB link rather than this rig.

Closed and not to be re-opened: cable, driver support, USB mode, autosuspend, supervisor latch, wrong port,
authorization policy.

## Next actions

Ranked by expected value after the A/B result. Do **not** reboot first — the port demonstrably works right
now, so a wedged stack is the least likely remaining cause.

```bash
# 1. BEST TEST: a SELF-POWERED USB hub between the K-3 III and the Polaris socket.
#    This isolates the bus-powered current-budget hypothesis directly. If the body
#    enumerates through a self-powered hub, the cause is confirmed and the fix is
#    operational (use a powered hub), not a code change.

# 2. If still nothing through a powered hub, try a reboot to re-run USB-C role
#    negotiation from scratch, then re-verify identity before trusting anything:
ssh root@192.168.0.1 'reboot'
python3 scripts/wait-for-rig.py --wifi-iface wlp8s0 --timeout 420
./scripts/verify-installed-build.sh out/astro-v118-stage2-gate-wedge-fix-20261126

# 3. Watch for enumeration with the K-3 III plugged in:
ssh root@192.168.0.1 'lsusb | grep -ai pentax; dmesg | grep -a "new .*USB device" | tail -3'
```

Note `autosuspend=-1` is runtime-only and will revert to `2` on reboot. That does not affect these tests — the
K-1 II enumerated fine with the same power settings the K-3 III failed under.

If a self-powered hub and a reboot both fail, this is a hardware-level incompatibility between this Polaris
socket and the K-3 III, and no change in this repo will fix it. In that case test the K-3 III on a **different
Polaris** to preserve the cross-model qualification goal — prior evidence shows `25fb:0189` attaching
successfully on other rigs, so the qualification itself is still achievable elsewhere.

## Evidence

`sanitized/` and `raw/` are **local working copies only** — `.gitignore:118` is `docs/evidence/**/*.log`, so
device logs are deliberately never committed. That rule is the repo's existing mitigation for the credential
problem, and it is why nothing here needed redacting to be safe to push.

- `sanitized/` — 40 files (`Clog_000016..000035`, `Mlog_000015..000034`) from `/app/sd/system/log/`, with
  `password:` / `securityA:` values replaced by `[REDACTED-B64]`. Verified clean. Use these locally for the
  overnight run; they are not in git.
- `raw/device-logs.tgz` and `raw/*.log` — originals, containing base64 account credentials from the
  `code:790` account flow (see N1 in `../../K1II-ISSUE-PLAN-20261126.md`). Never stage them; delete when done.

**Correction to the K-1 II handoff:** its commit message says "40 log files ... captured", and only
`HANDOFF.md` was actually committed — the same `.gitignore` rule silently skipped the sanitized set, and my
`git add` reported success without adding them. The analysis in `HANDOFF.md` is complete and self-contained,
so nothing needed for the next run is missing; but the logs themselves live only on this workstation, not in
the repo. Anyone picking up the overnight run needs the local checkout or a fresh pull from the rig.

**Refinement to N1's CI guard:** `*.log` under `docs/evidence/` is already blocked, which is why the eight
credential-bearing files that *did* get committed are `.txt` and `.json` (`Mlog_000276.txt`,
`api-link-opcodes.json`, …). A guard scoped to `*.log` would miss them. It must cover every file type under
`docs/evidence/`.

## Consequences for v118 status

**Cross-model qualification is still unproven.** The `.115`–`.117` gate wedge affected every model, and only
the K-1 II has been exercised on v118. Nothing in this session tests the gate, because no camera attached —
so the K-3 III checklist in `../../K1II-ISSUE-PLAN-20261126.md` remains entirely outstanding. Do not record
v118 as cross-model qualified on the strength of this session.

Also still unverified on v118, for the same reason: bulb capture end-to-end, RAW+JPEG delivery (#362), and
whether our kit's opcode-311 focus path works independently of the vendor AF path (#359).
