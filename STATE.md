# Investigation state — Benro Polaris FwPkt.zip install

> **Purpose.** A new agent session can `cat STATE.md` and be caught up
> on the current investigation in under a minute. Update whenever a
> hypothesis is closed, a finding is added, or the device state changes.
>
> **Status legend.** `DONE` · `WIP` · `BLOCKED` · `OPEN`.
>
> **Authoritative source of truth.** When this conflicts with other
> docs, this wins, because it's the most recent state. See
> [§ Cross-session drift](#cross-session-drift) below.

## TL;DR for a fresh agent

- **Problem:** custom `FwPkt.zip` packages need to install on the Benro
  Polaris gimbal. The standard "drop zip on SD card and reboot" flow
  is the autonomous path. The iPhone-app 810+USB-UART path is a
  separate, secondary path that requires a USB-serial gadget which
  this device does not have.
- **Path A (autonomous, primary):** place FwPkt.zip at `/app/sd/`
  → restart polestar_app (or reboot) → on-boot watcher detects zip
  → runs `SP_UpgradeCheckFw` → if MD5s differ, hands off to U-Boot
  for NAND reflash. **Confirmed working in the 18:50 pre-probe
  capture** (polestar_app restart fired the watcher; it said "no need
  upgrade" only because the stock zip was already on the SD card).
- **Path B (iPhone app, secondary):** iPhone sends `810` over TCP 9090
  → `SP_TtyUsbUartInit` opens `/dev/ttyUSB2` or `/dev/ttyUSB3` → FwPkt
  streams over USB-serial. **Blocked:** no USB-serial gadget on this
  device, Mlog shows `usb uart open failed` every 500 ms. The iPhone
  app physically plugs into USB-OTG, not over WiFi.
- **Two-version model (side issue, not the install blocker):** the
  iPhone shows "6.0.0.54" because `SP_GetDeviceVer` (code 780) returns
  a hardcoded `sw:6.0.0.54` immediate from `polestar_app`, not the
  value from `/app/FwVer`. This affects the iPhone UI but **does not
  block the autonomous install** — the install runs without the
  iPhone being involved. See
  [§ Two-version model](#-smoking-gun-2026-08-31-1935--the-two-version-model-read-this-first).
- **Hypothesis (H1, CLOSED):** wrong watch path — there is no
  FwPkt watcher in userspace; polestar_app IS the daemon. The
  install path is `/app/sd/FwPkt*` and it is correct.
- **Hypothesis (H2, CLOSED):** daemon not running — polestar_app
  (PID 248) is the daemon and is running.
- **Hypothesis (H4, NEW, prioritised):** the upgrade is triggered by
  a physical button → input event → userspace handler that calls
  the same code path the iPhone would. We can drive the same path
  over SSH by either: (a) sending the input event synthetically,
  (b) calling the handler's binary directly, (c) finding the
  dbus signal that polestar_app's `rcv upgrade start` handler
  listens for and emitting it locally. Note: this is the same
  810 trigger, just from a different source.
- **USB UART gate (reopened — applies to OMS upgrade too):** the
  `SP_TtyUsbUartInit` function in polestar_app opens `/dev/ttyUSB2`
  or `/dev/ttyUSB3` on receipt of 810. This is the OMS upgrade
  path (camera/main firmware), not the Quectel cellular path.
  The Quectel gate is closed; the OMS USB-UART gate is the
  current blocker.
- **Device state (live):** **UNKNOWN / DARK as of 2026-09-05** —
  `812` trigger was fired against the padded FwPkt.zip, no updater
  decision seen in Mlog, device then went dark through repeated
  unreachable periods and two manual restarts. Do not assume
  awake/SSH-responsive without re-verifying. See
  [Live device](#live-device) and
  [§ Session log 2026-09-04/05](#session-log-2026-09-0405--812-trigger-fired-inconclusive-then-device-instability).

## Live device

| | |
|---|---|
| Last known SSH | `ssh root@192.168.0.1` (works only when polaris AP is up) |
| Last known AP | `polaris_d13e86` (2.4 GHz, hidden SSID no, open) |
| Last known BT MAC | `48:E7:DA:D4:B5:72` (combo chip; WiFi MAC is `48:E7:DA:D4:B5:73`) |
| Wake method | bare `bluetoothctl connect 48:E7:DA:D4:B5:72` from a single piped session — the connect IS the wake pulse |
| Last known Mlog | `/app/yocto/run/customer/Mlog/Mlog_<date>.log` (NOT in `/var/log`) |
| Last reboot attempt | today, 16:0x UTC — AP appeared briefly, sshd never bound, dropped before SSH connect |
| Current state | **UNKNOWN / DARK as of 2026-09-05, ~1hr+ AP absence.** See [§ Session log 2026-09-04/05](#session-log-2026-09-0405--812-trigger-fired-inconclusive-then-device-instability) below — the `812` trigger was fired against the padded zip, produced no updater decision in Mlog, and the device subsequently went through repeated unreachable periods and two user-initiated manual restarts. As of the last check the Polaris AP (`polaris_d13e86`) was not broadcasting. `scripts/resilient-monitor.sh` is running in the background (read-only; auto-detects reconnect, snapshots boot/uptime/FwVer, continuously captures Mlog — see logs under `docs/evidence/fwpkt-install/resilient-monitor-*.log`) so the reconnect moment won't be missed. Do not assume the AWAKE state below still holds without re-verifying, and do **not** send another trigger until boot history is reviewed. |
| Prior known-good state (2026-08-31, superseded) | SSH responsive (port 22 open, lighttpd on 80, control daemon on 9090). polestar_app running as PID 248. `/app/sd/FwPkt.zip` (stock, 68.6MB) still staged. Watcher at `/tmp/polaris-watch/watch.sh` active. **Gimbal will re-sleep if the BT-paired phone leaves range** — see [§ Sleeping-when-phone-leaves](#sleeping-when-phone-leaves-do-not-blame-sshd). |

**If the device is awake:**

```bash
sudo /home/ian/Documents/VSCodeProjects/OpenPolaris/docs/evidence/gimbal-ssh-2026-08-31/wake-and-probe.sh
```

That script does: BT wake → wait for AP → nmcli join → SSH poll →
uname/ps/lsmod/Mlog dump → evidence pull. All in one go.

## Hypotheses

### H1 — Wrong watch path (WIP)

The install daemon may only watch **one** of these four FwPkt.zip
mount paths, and the one we're dropping the zip into isn't it:

- `/app/sd`
- `/app/sdcard`
- `/mnt/sd1`
- `/firmware`

Verified across `find / -name FwPkt.zip` in three boot states (clean,
SD-inserted, after-patch). Next step: enumerate which one the install
daemon reads from. The `polestar_app` ELF at
`/tmp/ubiextract/padded/958962934/ubifs/bin/polestar_app` has DWARF
symbols — `nm | grep -iE "fw|pkt|upgrade|sd|mount|watch"` should name
the watcher.

### H2 — Daemon not running (OPEN)

`ps aux | grep -i install` on a live device — has never been done in
this investigation. If empty, the install path is dead and the SD
zip can never be picked up.

### H3 — 810 trigger required ✅ **CONFIRMED 2026-08-31 22:00**

Observed: the phone app sends a TCP `1&810&0&#` (SYS_FW_UPGRADE) to
the polaris that arms the FwPkt watcher. The file being present
is not enough — the polaris only opens the USB UART and watches for
the FwPkt.zip stream *after* receiving 810.

**Live evidence (2026-08-31 22:00:58):** sending
`echo '1&810&0&#' | nc -w1 192.168.0.1 9090` (via SSH) immediately
produced this in Mlog:

```
SP_TtyUsbUartInit[298]:usb uart open failed
SP_TtyUsbUartInit[298]:usb uart open failed
SP_TtyUsbUartInit[298]:usb uart open failed
... (every 500ms)
```

**The 810 message arms the upgrade state machine.** The state
machine immediately tries to open `/dev/ttyUSB2` (and `/dev/ttyUSB3`)
to receive the FwPkt.zip byte stream. There is no USB-serial module
loaded on the device, so the open fails — but the state machine
*is* running. This is the H3 hypothesis confirmed: 810 is the
trigger, and the FwPkt.zip must arrive over USB UART (not TCP).

**The wire format is ASCII over TCP, port 9090**, format
`1&<code>&<subtype>&<payload>#` (no magic header, no length prefix).
See `OpenPolaris/shared/src/commonMain/kotlin/dev/openpolaris/core/protocol/CommandBuilder.kt`.

**Implication for our custom FwPkt:** the upgrade can only happen
over the wired USB UART path. Three options to get a custom build
installed:

1. **iPhone app + USB cable** (the documented path) — plug iPhone
   in with the original USB cable, launch Benro app, tap upgrade.
   The padded build at `/app/sd/FwPkt.zip` is already staged.
2. **Fake `/dev/ttyUSB2` via pty loopback** — `mknod` + `socat` to
   create a pty, then push the FwPkt.zip through it. UNTESTED —
   wire format over USB UART is unknown (likely XMODEM-1K or
   custom Benro protocol, needs decompile of `SP_TtyUsbUartInit`).
3. **Call `SP_OmsUpgradeFromSd()` directly** — requires either
   a cross-compiled ARM binary or ptrace injection; both are
   high-risk and have no precedent in this investigation.

**Stock FwPkt silent reject (the original puzzle):** the
"no need upgrade" branch fires when the per-key MD5s in
`FwPkt/firmwareInfo` match the currently-installed firmware's
MD5s. The padded custom build has a deliberate `appfs` MD5
mismatch (`4bd9131b...` vs stock `47f2ae68...`) — so if the
file *reaches* the verifier, it WILL be accepted for upgrade.
The silent reject we observed earlier was stock on stock, not
padded.

Evidence: see `OpenPolaris/docs/evidence/firmware-update-2026-08-31/01-pre-probe-state.txt`
line 97, and the live Mlog capture in checkpoint
`021-discovered-two-version-model-i.md`.

## Sleeping-when-phone-leaves (do not blame sshd) — DEMOTED

**Important non-bug, but no longer a blocker for the upgrade
workflow:** the polaris goes to deep sleep when the Bluetooth-paired
phone leaves range. From our side this looks identical to a crashed
device:

- AP `polaris_d13e86` disappears from `nmcli device wifi list`
- Port 22 / 9090 stop responding (sshd doesn't die, the whole SoC
  is suspended)
- `bluetoothctl devices` returns empty
- `ip route get 192.168.0.1` falls through to the home router
  (Hitron CGNV4-FX4 on `enp11s0`)

**We mistakenly thought sshd crashed during a 24MB binary transfer.
It didn't — the user had taken their phone out of range with the dog
at the same time. The two events were coincidental.**

The watcher at `/tmp/polaris-watch/watch.sh` logs the wifi signal
strength drop (`iwlist wlp8s0 scan | grep polaris` going from
signal 45 down to 35, then disappearing entirely over ~2 minutes —
that is the gimbal powering down). The BT keepalive script at
`/tmp/bt-keepalive.sh` only retries when `wlp8s0` state is `UP`, so
it can't wake the device from this state by itself.

### Why this is less important now

The Benro upgrade flow is documented as "two presses" — a physical
button gesture that runs the upgrade **autonomously** on the device,
without the iPhone. The iPhone is a status viewer, not a gate. So
we do not need to keep the phone in range just to make the upgrade
work.

We do still want the device to stay awake during the upgrade
itself (which takes minutes). Two ways to handle that:

1. **OpenPolaris keepalive** — speak the polaris host wire protocol
   from the laptop so the gimbal sees a connected host and does not
   sleep. This was the recommended mitigation before the
   clarification; it is still the most robust.
2. **Wake-on-BT and stay in range with the phone** — easy but
   fragile; we have already lost work to a dog walk.

When starting a long-running operation, **prefer the OpenPolaris
keepalive** over relying on phone proximity.

### Closed hypotheses

- **Cellular gate (Quectel `SP_TtyUsbUartInit` on `/dev/ttyUSB2`)**
  applies to the 4G-cellular-modem firmware upgrade path, not the
  SD-card FwPkt.zip path. See
  `OpenPolaris/docs/evidence/gimbal-ssh-2026-08-31/.../11-USB-UART-gate.txt`.
  Do NOT confuse the two.
- **Hitron router at 192.168.0.1** — when the polaris AP drops, the
  host's default route falls through to the home Wi-Fi, and
  `192.168.0.1` resolves to the Hitron CGNV4-FX4 cable router. NOT
  the polaris. `ip route get 192.168.0.1` is the truth.

## Important files

### In this repo

- [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md) — patcher mechanics.
- [docs/fwpkt-zip-layout-and-smb-delivery.md](docs/fwpkt-zip-layout-and-smb-delivery.md) — zip layout, MB mount, delivery.
- [docs/pentax-patcher-gate-bug.md](docs/pentax-patcher-gate-bug.md) — Pentax camera gate findings.
- [docs/silent-fwpkt-reject-postmortem.md](docs/silent-fwpkt-reject-postmortem.md) — original silent-reject post-mortem.
- [docs/critical-review-2026-08-28.md](docs/critical-review-2026-08-28.md) — recent critical review.
- [docs/TESTED.md](docs/TESTED.md) — what's been tested.
- [docs/CROSS-PROJECT.md](docs/CROSS-PROJECT.md) — coordination with OpenPolaris.
- [patch-polaris.sh](patch-polaris.sh) — the actual patcher script.
- [firmware/FwPkt.zip](firmware/FwPkt.zip) — the stock FwPkt we patch from.

### In OpenPolaris repo (per CROSS-PROJECT.md)

- `OpenPolaris/docs/PROTOCOL.md` — protocol codes.
- `OpenPolaris/docs/FIRMWARE-ANALYSIS-ALPACA.md` — static firmware analysis.
- `OpenPolaris/docs/evidence/gimbal-ssh-2026-08-31/HANDOVER-2026-08-31.md` — current investigation handover.
- `OpenPolaris/docs/evidence/gimbal-ssh-2026-08-31/wake-and-probe.sh` — automated wake+probe script.
- `OpenPolaris/shared/src/jvmMain/kotlin/dev/openpolaris/core/net/BluetoothProbe.kt` — `wake()` at line 120, source of the BT-wake approach.
- `OpenPolaris/shared/src/jvmMain/kotlin/dev/openpolaris/core/net/BridgeOrchestrator.kt` — `wakeOverBluetooth()` at line 86.

### In `/tmp` (not committed)

- `/tmp/ubiextract/padded/958962934/ubifs/bin/polestar_app` — 24.9MB ARM ELF with DWARF, 85616 symbols. Use `nm`, `objdump`, `readelf`.
- `/tmp/wake-evidence-20260831-144025/` — evidence dumps from prior session.
- `/tmp/polaris-watch/watch.sh` — running background watcher (pid 662084 as of 16:09 UTC).
- `/tmp/polaris-watch/seen.log` and `connect.log` — watcher logs.

### In session checkpoints (`.copilot/session-state/d72a8373-.../checkpoints/`)

- `001-resuming-fwpkt-install-investi.md` — resume context.
- `002-discovered-810-ret-1-rejection.md` — H3 evidence.
- `003-discovered-4g-cellular-modem-g.md` — Quectel cellular-gate analysis (closed hypothesis).
- `004-discovered-exdevfwpkt-alternat.md` — ExDevFwPkt alternate path.
- `005-discovered-dev-ttyama3-gimbal.md` — `/dev/ttyAMA3` gimbal self-upgrade.
- `006-discovered-dev-ttyama3-gimbal.md` — duplicate.
- `007-discovered-dwarf-symbols-and-b.md` — DWARF discovery and BT-wake method.
- `008-session-d72a8373.md` — current session: Hitron cleaned, watcher running.

## Cross-session drift

The user has explicitly raised: "We do keep drifting across sessions.
Can we make sure we consolidate findings and code across agent
sessions?". Two failure modes observed:

1. **Path drift.** This project lives at
   `/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/`. The
   OpenPolaris project is at
   `/home/ian/Documents/VSCodeProjects/OpenPolaris/`. The user's
   original message said "It might be in the openpolaris project, but
   should have been here." — they want the handover doc accessible
   from both. The handover at `OpenPolaris/docs/evidence/...` is the
   canonical copy. If you write something new, write it in the right
   repo and reference it from here.

2. **Investigation-state drift.** Hypotheses, evidence, and
   findings live across: this file, the handover doc, the session
   checkpoints, `/tmp/ubiextract/`, and the OpenPolaris repo. A
   fresh agent does not have all of these in context. The
   `Hypotheses` section above and the `Important files` index are
   the recovery path. **When you finish a hypothesis or add a
   finding, update both this file and the relevant checkpoint.**

3. **Sandbox quirks.** The bash tool blocks `kill` with `$!` PID —
   use a numeric PID. It blocks substring `kill` in some contexts.
   `bluetoothctl --timeout N` is the right way to bound a call.
   Use `create` for new files, `edit` only modifies existing ones.
   `nmcli` shows remembered-network entries even when no AP is
   broadcasting; the awk filter `$3 ~ [1-9]` (signal > 0) avoids
   ghost rows.

## 🚨 Smoking gun 2026-08-31 19:35 — the two-version model (READ THIS FIRST)

**This finding is the reason the whole FwVer-patch approach is
insufficient.** Source: checkpoint 021 + live Mlog capture in
[docs/evidence/polaris-ssh-2026-08-31/](/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/docs/evidence/polaris-ssh-2026-08-31/).

### The two distinct version fields

The polaris reports **two different versions** to the iPhone app, on
**two different protocol codes**, and the iPhone shows the wrong one
for the upgrade-check use case.

| Code | Source | Value | What it is |
|---|---|---|---|
| **808** | `/app/FwVer` (file in appfs) | `FwVer:4.0.0.32;date:2025.05.09;` | **Firmware version** — patchable by repacking `appfs.ubifs` |
| **780** | `SP_GetDeviceVer()` in polestar_app | `hw:1.1.1.2;sw:6.0.0.54;exAxis:;sv:1;ov: ;` | **Device/software version** — the one the iPhone **actually shows** |

**The iPhone Benro app shows `6.0.0.54` (the device version, code 780)
and uses that for the upgrade-available check.** It does NOT use the
firmware version from code 808 for the upgrade prompt.

→ **Implication:** editing only `/app/FwVer` in the FwPkt (the
`repack_appfs.sh` step that bumps `4.0.0.32 → 4.0.0.33`) will not
make the iPhone offer an upgrade. We need to also change the
`6.0.0.54` value that `SP_GetDeviceVer` returns.

### Where `6.0.0.54` comes from in the binary

The literal string `6.0.0.54` is **NOT in `/app/bin/polestar_app`
anywhere.** It is constructed at runtime by `SP_GetDeviceVer` from
hardcoded immediates (most likely `sprintf(buf, "%d.%d.%d.%d", 6, 0,
0, 54)` or a struct initializer). Two key format strings exist:

- `sw:%s;` at offset **10826904** — used to render the dotted-decimal
- `sw:%d;` at offset **10799920** — used in a different code path
  (likely cellular/ExDev)
- The full message format `hw:%s;sw:%s;exAxis:%s;sv:%d;ov:%s;` is at
  offset **10869964**
- The variant `hw:%s;sw:%s;exAxis:%s;sv:%d;ov: ;` (literal space
  before semicolon) is at offset **10870000** — this is the one
  actually returned, because the Mlog shows `ov: ;` with the space
- `SP_GetDeviceVer` string at offsets **10870848**, **20415316**,
  **24825532** (3 occurrences — symbol table, debug string, code
  reference)

The literal `4.0.0.32` IS in the binary (multiple `mFwVer[%s]`
references), so `SP_GetDeviceVer` definitely reads the firmware
version file but **transforms it** before returning the device
version. The transformation is not yet decoded.

### How to make the iPhone offer an upgrade (the experiment)

Two unverified hypotheses on what the iPhone does with the version:

- **H-spoof-upgrade:** patch `6.0.0.54 → 6.0.0.55` in polestar_app
  (change the immediate `54` in the version struct to `55`). If the
  iPhone compares device-versions and a FwPkt.zip with `sw:6.0.0.56`
  (or higher) is staged, the iPhone offers an upgrade.
- **H-spoof-downgrade:** patch `6.0.0.54 → 6.0.0.55` AND stage a
  FwPkt whose `/app/FwVer` says `4.0.0.32` (unchanged) but whose
  `firmwareInfo` claims a different device version. Reverse the
  direction: edit the FwPkt's `firmwareInfo` to claim
  `sw:6.0.0.53` so the polaris looks newer than the FwPkt, but the
  iPhone would offer a downgrade — likely no, this would block.

The cheap experiment order:

1. **Backup first:** `cp /app/bin/polestar_app /app/sd/polestar_app.stock`
2. **Patch the binary:** find the `mov rN, #54` immediate near the
   `10826904` (`sw:%s;`) string reference, change `54` to `55`.
   Patching a single ARM instruction is a 4-byte edit at a known
   offset (still TBD — needs the disassembly of `SP_GetDeviceVer`).
3. **Restart:** `pkill polestar_app; cd /app/bin && LD_LIBRARY_PATH=/app/lib ./polestar_app &`
4. **Test:** `ssh root@192.168.0.1 "grep -aoE 'sw:[0-9.]+' /app/Mlog.txt | tail -3"`
5. **iPhone:** open Benro app, check version display, then check for
   upgrades button.
6. **Recovery:** `cp /app/sd/polestar_app.stock /app/bin/polestar_app`
   and restart.

**Bricking risk:** medium-low. polestar_app restart is safe (PPid=1,
so it won't take init down with it). The risk is the binary becoming
un-runnable if the patch hits the wrong instruction — recovery is the
backup copy.

### Why the FwVer-only patch is dead

`repack_appfs.sh` currently bumps `/app/FwVer` (code 808) from
`4.0.0.32` to `4.0.0.33`. The iPhone does not look at code 808 to
decide whether to offer an upgrade. It looks at code 780. The FwVer
bump is therefore **decorative** until we also patch the device
version.

We could keep the FwVer bump for hygiene (so logs make sense, so
downstream tools can see a version), but it does not contribute to
making the upgrade work.

## 🚨 Smoking gun 2026-08-31 17:16 — what we learned this session

Source: [docs/evidence/polaris-ssh-2026-08-31/smoking-gun-2026-08-31-1716.txt](docs/evidence/polaris-ssh-2026-08-31/smoking-gun-2026-08-31-1716.txt)

### The user's correction (DO NOT IGNORE)

The user correctly called out: **"We did [write the FwPkt.zip]. If this is a lie, what else is?"**
The mtime of `/app/sd/FwPkt.zip` is `Aug 31 2026` = today. The zip's
inner file dates are 08-22 to 08-29. **Something today put this file
on the SD card.** Earlier in this session I conflated "I didn't `scp`
it over SSH during the read-only probe" with "we didn't put it
there." That was wrong and misleading. The honest read: the file
was placed by the prior agent's pipeline, a local sync, or an
earlier scp — we (collectively) caused it to be there today.

### The actual install path (or absence of one)

`/etc/udev/firmware.sh` is the **kernel `firmware_loader` helper**,
NOT a Benro installer. Full contents:

```sh
#!/bin/sh -e
FIRMWARE_DIRS="/lib/firmware /usr/local/lib/firmware"
...
if [ ! -e /sys$DEVPATH/loading ]; then
    err "udev firmware loader misses sysfs directory"
    exit 1
fi
for DIR in $FIRMWARE_DIRS; do
    [ -e "$DIR/$FIRMWARE" ] || continue
    echo 1 > /sys$DEVPATH/loading
    cat "$DIR/$FIRMWARE" > /sys$DEVPATH/data
    echo 0 > /sys$DEVPATH/loading
    exit 0
done
echo -1 > /sys$DEVPATH/loading
err "Cannot find  firmware file '$FIRMWARE'"
exit 1
```

`/etc/udev/rules.d/50-firmware.rules`:
```
SUBSYSTEM=="firmware", ACTION=="add", RUN+="/etc/udev/firmware.sh"
```

→ **There is NO udev rule that watches `/app/sd/FwPkt.zip` or the
firmware subsystem for SD-card drops. The FwPkt installer is not
triggered by udev.**

The install path must therefore be:
- Inside `polestar_app` (inotify, polling, or webdav handler), OR
- Triggered by an external event (810 UDP, BT command, lighttpd PUT).

### Files modified after `/app/FwVer` (May 9 2025) — the smoking gun list

```
/app/bin/polestar_app                   ← the main binary
/app/lib/lighttpd/webdav.db             ← webdav DB
/app/run/lighttpd.pid
/app/dbus/pid
/app/wifi/hostapd.conf
/app/access.log
/app/bluetooth/var/lib/bluetooth/48:E7:DA:D4:B5:72/settings
/app/bluetooth/var/lib/bluetooth/48:E7:DA:D4:B5:72/cache/...
/app/komod/hi3559v200_*.ko              ← kernel modules
```

→ `/app/bin/polestar_app` is the only binary on the box that
processes files. It was modified after the firmware was built.

### Benro app NPE on Android (correlated finding)

The Android app crashing with `null pointer exception` after this
session is consistent with the Benro app and the live `polestar_app`
being out of sync, OR with phone-side state going stale from the
repeated BT pairing dance. The phone NPE is almost certainly **a
phone-side bug**, not a polaris firmware issue. Nothing on the
polaris was modified by this session's read-only probe.

### H1 status update (CLOSED — wrong path was a red herring)

The "FwPkt watcher monitors a different path" hypothesis is now
implausible: **there is no FwPkt watcher at all** in the visible
userspace. The install trigger lives inside `polestar_app` or comes
from outside the box entirely.

### Next probe priority (in order)

1. **Trigger the upgrade and watch logs.** The `rcv upgrade start[%d]`
   string confirms the install is gated on a kick — likely the
   phone-app "upgrade" button which sends 810 UDP or a lighttpd PUT.
   With the AP up, tail `/app/access.log` + `find /app/yocto -name Mlog* -newer /app/FwVer` while sending the kick.
2. **Read the `rcv upgrade start` handler in `polestar_app`** — find
   which port / protocol carries it (UDP 810? lighttpd PUT to a
   specific path? BT GATT characteristic?).
3. **Compare `OMS_UPGRADE_STA_CHECK_FW` PASS vs FAIL** — the FAIL
   path is the silent rejection. Find the criterion (CRC? size?
   version compare? signed manifest?).

## 🎯 Smoking gun 2026-08-31 17:19 — polestar_app upgrade state machines

Source: [docs/evidence/polaris-ssh-2026-08-31/polestar-app-strings-2026-08-31-1719.txt](docs/evidence/polaris-ssh-2026-08-31/polestar-app-strings-2026-08-31-1719.txt)

`polestar_app` (24.9MB ARM ELF) contains **three parallel upgrade
state machines** that all consume `/app/sd/FwPkt*` paths:

### ExDev upgrade (external device firmware)
- `SP_ExdevUpgradeFromSD`
- `SP_ExDevFwPktCheck` — checks `/app/sd/ExDevFwPkt.zip`
- `SP_UartRcvExdevUpgradeMsgProc` — kicks from "rcv upgrade start[%d]"
- `unzip /app/sd/ExDevFwPkt.zip -d /app/sd/`

### Gimbal upgrade (UART to gimbal MCU)
- `SP_CreateGimbalUpgradePthread`
- `SP_UartRcvGimbalUpgradeMsgProc`
- Reads from `/app/sd/FwPkt/gimbal/`
- Files named `fw403FileName` (gimbal 403) and `fw413FileName` (gimbal 413) with versions
- Failure: "gimbal upgrade no suppor uart tx" (no UART → no upgrade)

### OMS upgrade (camera/main firmware)
- `SP_CreateOmsUpgradePthread`
- `OMS_UPGRADE_STA_LOAD_FW` → `CHECK_FW PASS/FAIL` → `SEND_START` → `SEND_DATA` → `SUCCESS`
- The `CHECK_FW FAIL` state is the silent reject

### The trigger architecture (the H3 kick)
- Every upgrade thread is spawned on demand by `SP_Create*UpgradePthread`
- The trigger source is `rcv upgrade start[%d]` (parameterised) / `rcv upgrade start,McuId[%x]`
- `Rcv*MsgProc` handlers exist for each path
- Strings `dbus_watch_get_flags`, `g_io_add_watch`, `g_main_loop` → D-Bus / GLib main loop
- The kick is therefore delivered over D-Bus, lighttpd, or UDP — the actual channel is the next thing to find

### H1 / H2 / H3 collapse
- **H1 wrong-path:** closed. polestar_app uses `/app/sd/FwPkt/gimbal/`, `/app/sd/ExDevFwPkt.zip` etc — these are the canonical paths.
- **H2 daemon not running:** closed. polestar_app IS the daemon.
- **H3 needs 810 trigger:** **the only viable remaining cause of the silent reject.** The "file is there but nothing happens" pattern matches "wait for `rcv upgrade start` event that never arrives".

## Decisive next move (added 2026-09-01 — read this first, stop reconning)

The plan is settled. Path A (padded FwPkt.zip at `/app/sd/` + reboot → on-boot
watcher → MD5 mismatch → U-Boot reflash) is confirmed working end-to-end except
the final reflash. **Do not start new recon threads.** The single remaining step:

0. **(Added 2026-09-01, from the capstone thread's pivot — read this first.)**
   The other active session (Copilot chat `d72a8373`, resumed from a handover)
   spent ~30 checkpoints on polestar_app disassembly (message queues, jump
   tables, PLT resolvers, a capstone bug at checkpoint 080) and then concluded:
   **the disassembly is a dead end — blaineam's `patch-polaris.sh` already does
   the job.** It unpacks the stock FwPkt, patches **pgphoto** (not
   polestar_app), repacks; install goes through the official SD-card path.
   Our padded zip (`builds/2026-08-30-padded-appfs/FwPkt.zip`) is based on the
   2026-08-29 libgphoto2-only build, so it should already carry the pgphoto
   patch — but validate before burning a reboot:

   ```bash
   cd /home/ian/Documents/VSCodeProjects/BenroPolarisPatcher.worktrees/libgphoto2-only-fork
   ./patch-polaris.sh --fwpkt /home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/builds/2026-08-30-padded-appfs/FwPkt.zip \
     --selftest --out /tmp/fwpkt-selftest   # Docker is available on this box
   ```

   If `--selftest` passes, the zip it produces (or our padded one, if identical)
   is what goes on `/app/sd/`. This step needs no device — do it while the
   Polaris sleeps. **Do NOT resume DWARF/capstone analysis of polestar_app.**

   **Step 0 result (2026-09-01, executed in this session): padded zip CONFIRMED for `/app/sd/`.**
   - `./patch-polaris.sh --fwpkt builds/2026-08-30-padded-appfs/FwPkt.zip --selftest` fails at the pgphoto analysis step — expected, not a defect: the padded appfs already carries the full-mode stage-2 layout from the 2026-08-23 build (`/app/bin/pgphoto` is the 275-byte shell wrapper; the real ELF lives at `/app/lib/stage2/pgphoto.stage2ondisk`). Full mode would rebuild/overwrite that tree, and ptp2only mode's analyzer chokes on the wrapper.
   - Direct verification of `pgphoto.stage2ondisk` (objdump inside the polaris-patcher image) confirms **all functional patches are present**: GATE1 0x26248 / GATE2 0x29d88 / GATE3 0x29db8 all carry `e3a03000` (mov r3,#0); resetUsb @ 0x21830 prologue is the patched `mov r0,#0; bx lr`; list-files bl @ 0xfffd0 is NOP'd. The ~70-block diff vs stock+standard-patch is the full-mode on-disk trampoline (64 boundary entries) — by design, not a different patch set.
   - Provenance chain closed: padded zip = 2026-08-29 payload (= byte-for-byte repackage of `builds/2026-08-23/FwPkt.zip`) + one PEB (131,072 B) of 0xFF appended to appfs; its stage-2 tree is byte-identical to `builds/2026-08-23/stage2-ondisk/`.
   - MD5 of the padded zip = `92da888387b14dc02976b5fa22b94067` — exactly what `scripts/attempt-fwpkt-install.sh` expects. **Proceed to step 2 (the one-reboot runbook) when the device is awake.**
   - If a real qemu signal is ever wanted: `./patch-polaris.sh --fwpkt firmware/FwPkt --ptp2-only --selftest --out /tmp/fwpkt-selftest` against **stock** (qemu selftest only runs in ptp2only mode; full mode skips it).
   - **Selftest zip-publication bug fixed (commit `0a2f613`).** The stock selftest previously died after "OK: 6 entries verified" with a `UnicodeEncodeError` (em-dash U+2014 inside the python `-c` zipfile fallback, argv-decoded under the C locale) and then an `AttributeError` in `validate_fw_package.py` (`ZipInfo.is_dir()` is py3.6+, container runs debian:9/py3.5). Both fixed; re-run now completes end-to-end: R5m2 driver-load OK, 14-byte pgphoto patch verified, structurally valid FwPkt.zip produced (ptp2only build md5 `d07d804835b8c7c244b919d010e97c4e`). The padded zip for `/app/sd/` is unchanged (`92da8883...`).
   - **Correction:** `trigger_upgrade.sh` was NOT found in `/app/sd/` on the device (checked 2026-09-01 via SSH) — step 1 below can be skipped; the runbook is self-contained.

1. ~~**First, pull the undocumented loose end:** `trigger_upgrade.sh` sitting in
   `/app/sd/` on the device (558 bytes, created Aug 31 21:41) is referenced by no
   evidence file and not documented here. Pull it once and record its contents:

   ```bash
   ssh root@192.168.0.1 'cat /app/sd/trigger_upgrade.sh' \
     | tee docs/evidence/polaris-ssh-2026-08-31/trigger-upgrade-script.txt
   ```

   If it does anything beyond what `attempt-fwpkt-install.sh` already chains, fold
   that in; otherwise delete it from the device to stop future sessions re-running
   half-baked variants.~~ **RESOLVED 2026-09-01:** no such file exists on-device —
   `/app/sd/` holds only FwPkt.zip, OmsPkt.zip and the unpacked FwPkt/ tree. Skip.

2. **Run the one-reboot runbook** (pre-flight → Mlog capture → fire 812 → wait for
   cold boot → verdict):

   ```bash
   ./scripts/attempt-fwpkt-install.sh --dry-run   # pre-flight only, safe offline
   ./scripts/attempt-fwpkt-install.sh            # the full sequence
   ```

   It verifies `/app/sd/FwPkt.zip` md5 == `92da888387b14dc02976b5fa22b94067`
   (the padded build) before firing, captures Mlog to
   `docs/evidence/fwpkt-install/`, and prints a binary verdict:
   **REFLASH TRIGGERED / NO UPGRADE NEEDED / INCONCLUSIVE**.

3. **After the reboot:** if REFLASH TRIGGERED, watch for the NAND reflash to
   complete (device dark ~5–10 min), then verify `FwVer` via code 808 and the
   iPhone-reported version (code 780 — remember the two-version-model smoking gun:
   the `#54` immediate in `SP_GetDeviceVer`, not `/app/firmwareInfo`).

If a session finds itself re-deriving any of this, it has drifted back into recon
mode. The evidence is already in `docs/evidence/polaris-ssh-2026-08-31/` — read the
latest capture, then run step 2.

## Session log 2026-09-04/05 — 812 trigger fired, inconclusive, then device instability

**Confidence key:** ✅ directly observed this session · ⚠️ inferred, not proven ·
❓ open question, do not assume an answer.

### What was done

- ✅ Step 2 of the decisive-next-move runbook was executed:
  `./scripts/attempt-fwpkt-install.sh` ran its pre-flight (confirmed
  `/app/sd/FwPkt.zip` MD5 `92da888387b14dc02976b5fa22b94067`, matching the
  padded build), captured `Mlog.txt` before/after, and sent the `1&812&0&#`
  wire frame to TCP 9090.
- ✅ The only Mlog line produced by the trigger, across every capture this
  session, was:
  ```
  [12:33:20:103 ERROR-]:msg_rcv_from_app_process[65]:rcv msg from App[8]:type:0;code:812;val:
  ```
  **No `CHECK_FW`, no PASS/FAIL, no reflash/install marker ever appeared.**
  This is the single most important fact from this session: the command was
  *received* by `polestar_app`, but there is no log evidence it was *acted on*.
- ✅ Post-trigger, `/app/FwVer` still read `FwVer:4.0.0.32;date:2025.05.09;` —
  unchanged from the pre-trigger baseline. Expected either way (an appfs-only
  patch does not bump this string), so this neither confirms nor refutes
  install — it's just consistent with "nothing happened yet" or "an appfs
  swap happened without touching this file."
- ⚠️ A second, **unintentional** `812` frame was sent later in the session
  during an unrelated connectivity check that accidentally combined a raw
  TCP-9090 payload probe with the trigger payload. Flagging this so no future
  session misreads the evidence window as "one clean trigger, one clean
  response" — there were two sends, one deliberate and one accidental.

### Device instability observed after the trigger(s)

- ✅ A 6-minute background uptime poll (10 s interval) showed the device
  reachable and incrementing normally through ~210 s post-trigger, then
  **unreachable from ~220 s through the end of the 360 s window.** This
  coincided with the accidental second `812` send above, so the two events
  cannot be cleanly separated in time. ❓ Whether this dark period was a
  delayed reboot caused by the trigger, or unrelated Wi-Fi/power instability,
  is **unresolved**.
- ✅ The user then manually resumed the device via iPhone (their words: "i
  think it just timed out. i resumed it via iphone"). SSH returned
  **"Connection refused"** (not a timeout) for about 2 minutes afterward —
  i.e. the network interface answered but `sshd` was not yet listening,
  consistent with an in-progress boot/service-start sequence.
- ✅ Full connectivity briefly returned (ping OK, ports 22/80/9090 open,
  `iw dev wlp8s0 link` showed active association to the Polaris AP
  `48:e7:da:d4:b5:73`, but at a weak **-81 dBm** / **1.0 MBit/s** link).
  A subsequent SSH evidence-capture attempt failed with **"No route to
  host"** almost immediately after — consistent with a marginal/unstable
  radio link, not necessarily a device-side fault.
- ✅ The user then said "I had to restart it" (a second manual restart). A
  300-second retry loop for a read-only evidence snapshot (`date`, `uptime`,
  `FwVer`, staged-package MD5s, update-related `Mlog.txt` grep, key process
  list) never got a single successful connection in that window.
- ✅ Following that, this session confirmed via `nmcli`/`ip route` that one
  apparent "successful ping" to `192.168.0.1` was **not the Polaris** — Wi-Fi
  (`wlp8s0`) had disconnected from `polaris_d13e86` entirely, and the ping
  was actually routed over the wired LAN (`enp11s0` → `192.168.68.1`) to an
  unrelated device that happens to share the `192.168.0.1` address on a
  different subnet context. **Lesson for future sessions:** always confirm
  `nmcli device status` shows `wlp8s0` connected to `polaris_d13e86` before
  trusting a bare ping to `192.168.0.1` as Polaris evidence.
- ✅ After that correction, `polaris_d13e86` did not reappear in Wi-Fi scans
  for at least ~20 minutes of active polling (two ~5–8 minute scan loops).
  As of the last check in this session, the AP was still not broadcasting.

### What this does and does not prove

- ❌ **Does NOT prove** the FwPkt install ran or succeeded — no updater
  decision was ever logged.
- ❌ **Does NOT prove** the install failed/was rejected either — silence is
  also consistent with the trigger being ignored for an unrelated reason
  (see `docs/silent-fwpkt-reject-postmortem.md`), or with the relevant log
  lines being written to a file this session didn't capture in time.
- ⚠️ **Weakly suggests** something changed device-side around the trigger
  (the dark period, the "Connection refused" boot signature, the repeated
  need for manual restarts), but this is equally explainable by pre-existing
  Wi-Fi/hardware flakiness (the observed -81 dBm signal is poor) that has
  nothing to do with the `812` command.
- ❓ **Open, unresolved:** how many times has the device actually rebooted
  since the trigger, and were any of those reboots *caused by* the trigger?
  No boot-counter or `dmesg` boot-timestamp evidence has been captured to
  answer this. This should be the first thing pulled once SSH is available
  again — before sending any further commands.

### Explicit rule for the next session

**Do not send another `812` (or any other) trigger** until:
1. SSH access is re-established and stable (not just a momentary port-open).
2. A boot-counter / `dmesg` timestamp check has been done to establish how
   many reboots have occurred and roughly when, so any future trigger's
   effect can be measured against a known baseline.
3. The Mlog capture strategy is upgraded to *keep polling/capturing through
   a possible dark period* (this session's single-snapshot approach lost
   any log lines written during the unreachable windows).

### Extended outage continuation (same session, later) — new resilient tooling

- ✅ After the ~20-minute gap noted above, three further Wi-Fi scan loops
  were run back-to-back (~16 min, ~4 min, ~1 min effective runtimes,
  varying by loop sleep interval). **None saw `polaris_d13e86` reappear.**
  Cumulative AP-absence time reached **roughly 1 hour** with zero
  sightings — the longest gap observed in this whole investigation.
- ✅ Re-checked `gh issue list` (open + closed) during this gap: nothing
  new/actionable. Issues #1/#2/#5/#9/#10/#12 already closed; open issues
  #11/#8/#7/#6/#3 are pre-existing feature requests/questions with no new
  activity. No GitHub work is currently pending.
- ✅ Asked the user to physically check the device (power/light state);
  the user was not available to answer. Physical intervention may be
  required — passive network scanning cannot distinguish "device is off"
  from "device is on but Wi-Fi radio hasn't come back."
- ✅ **Built `scripts/resilient-monitor.sh`** to address the explicit rule
  above (point 3) proactively, so the *next* time the device comes back
  we don't lose the boot-history/Mlog evidence to another dark-period gap.
  It is 100% read-only (no writes to `/app/sd/`, no port-9090 triggers) and:
  - Correctly distinguishes real Polaris association (`nmcli` shows
    `wlp8s0` connected to a `polaris_*` profile) from the
    `192.168.0.1`-is-not-unique false positive documented above.
  - Actively calls `nmcli device wifi rescan` while down, rather than
    waiting on NetworkManager's own scan cadence (there is a saved
    `polaris_d13e86` profile with `autoconnect=yes`, so once seen it
    should auto-associate).
  - On every UP/DOWN transition, appends a timestamped line to
    `docs/evidence/fwpkt-install/resilient-monitor-timeline.log`.
  - On every UP transition, takes a cheap snapshot (`/proc/uptime`,
    a `FwVer` grep, first `dmesg` line) into the same timeline log —
    this is the boot-counter/history evidence point 2 above calls for.
  - On every UP transition, (re)starts `tail -n0 -F /app/Mlog.txt` over
    SSH, appending continuously to
    `docs/evidence/fwpkt-install/resilient-monitor-mlog.log` (never
    truncated). If SSH drops, the tail dies naturally and is restarted
    from the new EOF on the next UP transition — so Mlog evidence is
    captured continuously across dark periods instead of only at
    single snapshot points, satisfying point 3 above.
  - Still does **not** send any trigger — it is purely observational,
    per the explicit rule.
  - Launched detached in the background (`nohup ... & disown`,
    `POLL_SECS=6`) so it keeps running independently of any single
    session/shell and will capture the reconnect moment automatically.
  - **Still no send of `812` or any other trigger.** The explicit rule
    above remains in force: once this monitor shows STATE UP and a
    stable snapshot, review the boot-history evidence with the user
    before considering another trigger attempt.

## What to do right now (no device)

If the device is in deep sleep and there's nothing to probe, prefer step 0 of
the decisive-next-move section above (`patch-polaris.sh --selftest` against the
padded zip). The DWARF/capstone route below was declared a dead end by the
capstone thread on 2026-09-01 — only resume it if `--selftest` fails.

1. **DWARF analysis of `polestar_app`.** Open
   `/tmp/ubiextract/padded/958962934/ubifs/bin/polestar_app` with
   `nm`, `objdump -d`, or `readelf -wi`. Look for:
   - Symbols containing `fw`, `pkt`, `upgrade`, `mount`, `watch`.
   - Calls to `MNT_SD`, `init_fwpkt`, `SP_UpgradeCheckFw`, `TtyUsbUartInit`.
   - String at `0xa5de28` (the FwPkt.zip filename reference) and
     trace its references — what reads the file, what watches for it.
2. **Compare stock and patched FwPkt zip contents.** Already done in
   `docs/silent-fwpkt-reject-postmortem.md`. Confirm the
   post-patch SHA still mismatches the install-daemon's expected
   hash.
3. **Static check the patch-polaris.sh flow** — every step's
   exit-code handling, the SMB mount retry loop, the UBIFS
   repackaging.

## 🎯 Disasm findings 2026-09-01

Static analysis of `polestar_app` reverse-engineered the full call graph for
firmware upgrade triggers. All evidence in
`docs/evidence/polestar-disasm-2026-09-01/` (12 files + README).

**READ THESE FIRST** (in order of importance):

1. [`09-oms-callers.md`](docs/evidence/polestar-disasm-2026-09-01/09-oms-callers.md)
   — **THE** end-to-end SD-install trigger chain: kernel uevent → netlink
   → `EventMsgProc` case 4 (event 0x405) → `SP_OmsUpgradeFromSd`
   (0x77cf4) → `pthread_create` → `OmsUpgradeStatusProc` (0x75bfc).
2. [`10-capstone-operand-bug.md`](docs/evidence/polestar-disasm-2026-09-01/10-capstone-operand-bug.md)
   — Documents the capstone `ins.operands[0]` false-negative bug that
   produced the wrong "all dead code" claim in earlier analyses. Use the
   included `tools/find_callers.py` for correct call-graph extraction.
3. [`11-uncalled-list.md`](docs/evidence/polestar-disasm-2026-09-01/11-uncalled-list.md)
   — The actual 22/129 "uncalled" funcs (all are pthread entry points,
   not dead code).

**Corrected trigger-path summary (after bug fix):**

- **6 trigger paths** confirmed:
  1. UART byte **0x21** — `GimbalUartRxMsgProcTask` → `SP_GetGimbalExFwTask` → upgrade
  2. UART byte **0x61** — same dispatcher, adjacent case
  3. UART byte **0x63** — same dispatcher
  4. UART byte **0x64** — same dispatcher
  5. **SD hotplug auto-trigger** — `EventMsgProc` case 4 (event 0x405) at
     VA `0x3f8fc` (DWARF: `sp_sys.c:2657`) calls `SP_OmsUpgradeFromSd`
     (`0x77cf4`) via `bl 0x77cf4` at `0x3f950` (DWARF: `sp_sys.c:2664`).
     This in turn calls `SP_CreateOmsUpgradePthread` (0x76754) which
     uses `pthread_create` (Bionic 0x2245c) with thread function
     `OmsUpgradeStatusProc` (0x75bfc, confirmed via signed arithmetic
     on LDR pc-relative literal 0xfffff3dc at 0x768c8).
  6. **Bluetooth OMS** — `SP_OmsUpgradeMsgProc` (0x768e8) called from
     `BtRcvMsgProcTask` at 0x469c8.

- **EventMsgProc dispatch** at VA `0x3f610`–`0x40258`:
  real `addls pc, pc, r3, lsl #2` switch at `0x3f668` (encoding
  `0x908FF103`), with a 24-entry `b <vaddr>` jump table at
  `0x3f670-0x3f6cc`. Index is `(event_id - 0x401) - 1`, range
  0..0x17 (msgId 0x401..0x418). Default fallthrough `b 0x40098`
  at `0x3f66c` (executed when the addls condition `LS` is not
  satisfied, i.e. msgId < 0x401 or > 0x418).
  Case 4 (msgId 0x405) → `0x3f8fc` is the SD-insert handler that
  calls `SP_ExdevUpgradeFromSD(2)` and `SP_OmsUpgradeFromSd`
  (verified via find_callers.py). Full case-by-case map in
  [12-eventmsgproc-dispatch.md](docs/evidence/polestar-disasm-2026-09-01/12-eventmsgproc-dispatch.md).
  `SP_PostEvent` ≡ `SP_EventPub` @ 0x3f364 (PUBLISHER, not dispatcher).

- **NetlinkUeventTask** (0x322ac) listens for kernel uevents. SUBSYSTEM
  match strings at .rodata 0xa48120 include:
  - `add@/block/mmcblk0/mmcblk0p1` → triggers event 0x402 → eventually
    leads to event 0x405 → OMS SD install.
  - `add@/tty/ttyAMA1/hci0/hci0:` → Bluetooth events.
  - `add@/ttyUSB2` → 4G USB modem.

- **Threading model**: Each upgrade subsystem (`Oms`, `Exdev`,
  `Gimbal`, `Plc`, `Upgrade`) has the same pattern:
  - `SP_CreateXxxPthread @ P` calls `pthread_create(r0=&tid, r1=NULL,
    r2=FuncProc, r3=NULL)` (Bionic 0x2245c).
  - `XxxStatusProc @ F` is the thread function (top-of-function body:
    `push {fp,lr}; add fp,sp,#4; sub sp,sp,#N; ...; mov r0,#0xf; bl
    pthread_sigmask; ...`). Has zero direct BL callers because it's
    only reached via pthread_create.
  - This explains the 22/129 "uncalled" funcs from
    `11-uncalled-list.md`. They are NOT dead code.

- **Segment mapping (CRITICAL — for all string lookups):** LOAD 0 (R+X)
  covers `.text` + `.rodata` and maps `file_offset = VA - 0x10000`. LOAD 1
  (R+W) maps `file_offset = VA - 0x200000`.
- **`SP_UpgradeCheckFw`** uses `HI_system` (4 call sites at PLT `0x1a23d4`)
  to run shell commands.
- **Manual SD trigger** (no firmware patch): `umount /app/sd && sleep 1 &&
  mount -t vfat /dev/mmcblk0p1 /app/sd` re-fires the kernel uevent
  `add@/block/mmcblk0/mmcblk0p1` → `NetlinkUeventTask` → event 0x402 →
  EventMsgProc case 4 (event 0x405) → OMS install.

**Why this matters for the install path:** The corrected
`09-oms-callers.md` traces show that the SD hotplug auto-trigger
*is* wired up in the binary and *is* reachable at runtime. The
"all dead code" hypothesis was based on a false-negative bug
(see `10-capstone-operand-bug.md`) and must be retracted.

## What to do when the device wakes

```bash
sudo /home/ian/Documents/VSCodeProjects/OpenPolaris/docs/evidence/gimbal-ssh-2026-08-31/wake-and-probe.sh
```

That produces `probes-<timestamp>/` with:

- `01-ssh-up.txt` — first successful SSH.
- `02-processes.txt` — full `ps aux`.
- `03-watch-paths.txt` — the H1 watch-paths dump.
- `04-daemon.txt` — H2 daemon check.
- `05-810-trigger.txt` — H3 trigger state.
- `06-usb-drivers.txt` — `lsmod`, `/proc/modules`, `dmesg`, `lsusb`.
- `07-mlog-grep.txt` — grep for `fwpkt|firmware|crc|upgrade|SP_UpgradeCheckFw|TtyUsbUartInit` across all `Mlog_*`.
- `08-proc.txt` — `/proc/version`, `/proc/cmdline`, `/proc/mtd`, `/etc/os-release`.
- `09-fwpkt-find.txt` — `find / -name FwPkt.zip`.
- `10-mlog-latest.txt` — last `Mlog_*` file pulled.

Update the `Hypotheses` section in this file with the results.
