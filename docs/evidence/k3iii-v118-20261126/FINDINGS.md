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

## Why the new cable is the leading explanation

A data-capable cable plus a powered-on body produces a kernel line — `new high-speed USB device number N` —
**even if enumeration then fails**. Seeing literally nothing, before and after a replug, means the host never
detects a data pair at all. That is the signature of a charge-only cable or a bad contact, not a driver or
firmware problem.

Supporting detail: the K-1 II enumerated on `1-1.2` as **high-speed (USB 2.0)** and bus 002 (SuperSpeed) has
never had a child. So this link negotiates at USB 2.0 regardless of body — a SuperSpeed failure would not by
itself block enumeration, which points further at the cable's data pair rather than speed negotiation.

## Driver support — checked, and I will not over-claim it

`camlibs/pentax/library.c` (pin `f48a05e08`) ends its abilities list at:

```c
strcpy (a.model, "Pentax:K1II");
a.usb_vendor  = 0x25fb;
a.usb_product = 0x0182; // in MSC mode, which is used by usbscsi
```

Neither `0x0183` (what the K-1 II actually reported) nor `0x0189` appears in that file. **This does not mean
the driver cannot handle the K-3 III** — the K-1 II works while its own reported ID `0x0183` is absent from
that table, so ID matching there is evidently not the only path (note the comment says `0x0182` is the MSC
-mode ID). I cannot conclude anything about K-3 III driver support from this alone, and it is moot until the
body enumerates. Re-check once it attaches: if it enumerates but pgphoto refuses to bind, that table becomes
the first place to look.

## What to do — isolate cable vs rig in under a minute

A local watcher is running on the workstation (`/tmp/local-usb-watch.log`, 20 min) and a kernel watcher on
the rig (`/tmp/usb-watch.log`). Either test is decisive:

1. **Plug the K-3 III into this workstation with the same new cable.** If nothing appears locally, the cable
   (or body settings) is the fault — not the Polaris.
2. **Swap to a cable known to carry data** — ideally the one that worked with the K-1 II — and retest on the
   rig.
3. **Check the body**: USB mode must be PTP/Mass-storage-as-configured, not charge-only; some bodies default
   to charging over USB-C. Also try the other physical port on the rig if it has one.

Then confirm with:

```bash
ssh root@192.168.0.1 'ls /sys/bus/usb/devices/ | grep -av "^usb"; lsusb | grep -ai pentax'
```

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
