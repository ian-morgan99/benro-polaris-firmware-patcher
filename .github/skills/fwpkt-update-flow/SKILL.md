---
name: fwpkt-update-flow
description: Enforce the only sanctioned way to install firmware on the Benro Polaris gimbal — via the pre-extracted FwPkt/ tree on the SD card (the on-boot watcher path). USE FOR: any agent or human planning to flash, recover, or modify firmware on the device; staging a FwPkt.zip; reasoning about on-boot upgrades. DO NOT USE FOR: building/patching FwPkt.zip locally on the PC (use container/ instead), debugging polestar_app binary internals, or anything unrelated to firmware installation.
---

# Polaris firmware update flow — HARD RULE

> **HARD RULE.** The Polaris gimbal accepts firmware only via the **pre-extracted
> `FwPkt/` directory tree at the root of the SD card**. There is no sanctioned
> alternative. If a recovery, fix, or test requires changing what's in NAND, it
> must be packaged as a `FwPkt.zip` whose `firmwareInfo` per-file MD5 entries
> match the actual bytes, **extracted to `/FwPkt/` at the SD root**, and
> installed by the on-boot watcher. Anything else — direct edits to `/app/...`
> over SSH, dropping only the `.zip` at the root, hot-patching `/app/bin/` —
> is **prohibited**, full stop. This rule exists because the alternative path
> reliably bricks the device (see "Why this rule exists" below).

## Why this rule exists

A 2026-09-07 incident (see `STATE.md` and the post-mortem in
`docs/evidence/fwpkt-install/sd-card-logs-2026-09-07/`) demonstrated the
failure mode of bypassing this rule. A separate agent session had SSH access
to the gimbal and made direct changes to NAND (`/app/bin/`, `/app/lib/` etc.)
in pursuit of an SD-backup / patch-related change, then attempted to revert.
The revert left the device wedged: `/app/bin/pgphoto` was gone (or
unreachable from the loader), `libpolaris_stage2.so` reported
`FATAL early call to gp_port_new @slot=0x300000f0 before fill`, `pgphoto`
exited immediately, and `checkGphotoTask` looped restarting it — saturating
CPU and starving everything else, including the radios. The device stopped
broadcasting its AP and stopped responding to BT. Only the SD card on the
gimbal kept writing Mlogs, which is how we recovered it at all.

The recovery was the canonical flow described below: SD-card extracted
`FwPkt/` tree, power-cycle, on-boot watcher, U-Boot reflash. No bypass
worked, and the bypass itself was the cause.

## The sanctioned flow

### 1. Pre-extract the zip to `/FwPkt/` at the SD root

The Polaris' on-boot watcher (`SP_EVENT_SD_SCAN` at polestar_app 0x3f8fc)
walks `/app/sd/FwPkt/{gimbal,camera}/`. It does **not** look for a zip at
`/app/sd/FwPkt.zip` — that path is silently ignored. The 2026-09-06 Benro
download page revision finally instructs end-users to do this; the firmware
has always read it.

Correct layout:

```
SD card root
└── FwPkt/                       ← the folder that was inside the zip
    ├── firmwareInfo             ← per-file MD5 manifest (NOT zip-level)
    ├── camera/
    │   ├── appfs.ubifs
    │   ├── config
    │   ├── rootfs.ubifs
    │   └── uImage
    └── gimbal/
        ├── polaris403_<ver>.bin
        └── polaris413_<ver>.bin
```

Wrong layouts (silently rejected, no diagnostic):

- ❌ `FwPkt.zip` alone at SD root.
- ❌ Files flattened to SD root (`/appfs.ubifs`, `/camera/`, etc. directly).
- ❌ Nested `FwPkt/FwPkt/...` from extracting into a subdirectory instead of the card root.

### 2. Verify `firmwareInfo` MD5s match the actual bytes before staging

The on-board `crcInfo` (called by `getFwInfo.sh`, called by `polestar_app`)
string-compares every `KEY size:...` and `KEY MD5:...` line in `firmwareInfo`
against a fresh recomputation. Any mismatch is silently fatal — the updater
reboots without writing NAND and the user sees nothing change.

Use `container/validate_fw_package.py` to validate before staging, or do it
manually:

```bash
cd /path/to/extracted/FwPkt
for f in camera/appfs.ubifs camera/rootfs.ubifs camera/uImage camera/config \
         gimbal/polaris403_*.bin gimbal/polaris413_*.bin; do
  size=$(stat -c %s "$f")
  md5=$(md5sum "$f" | awk '{print $1}')
  base=$(basename "$f")
  echo "$base size:$size;$base MD5:$md5;"
done
```

Every line must match the corresponding line in `firmwareInfo` byte-for-byte.

### 3. Reseat the SD card and clean power-cycle

- Pull the SD card from the PC.
- Insert it in the gimbal's SD slot.
- Press and hold the gimbal's power button until it shuts down cleanly
  (don't unplug — let polestar_app finish).
- Count to 30.
- Press the power button again.

The on-boot watcher (`SP_EVENT_SD_SCAN`) fires when `SP_EVENT_SD_MOUNTED`
arrives, calls `SP_UpgradeCheckFw`, hands off to U-Boot for NAND write if the
MD5s differ from the installed firmware. **This step takes 5–10 minutes.**
The gimbal will reboot itself when U-Boot finishes.

#### Verified remote equivalent when the mounted SD is reachable

On 2026-09-09, `o-v6-lockfix` was installed successfully without physically
moving the card. This is allowed because it still uses the complete extracted
`/app/sd/FwPkt/` tree and the normal boot-time watcher; it does not modify NAND
over SSH.

After proving device identity, an empty target, registry provenance, and stable
power, stream the whole tree to the SD mount:

```bash
tar czf - -C /absolute/path/to/registered-build FwPkt |
  ssh root@192.168.0.1 'tar xzf - -C /app/sd && sync'
```

Recompute every camera/gimbal payload MD5 on `/app/sd/FwPkt` and compare it to
the on-card `firmwareInfo` before rebooting. Do not merge with or overwrite an
unknown partial tree. Stop keepalives, then trigger the normal boot watcher with
`ssh root@192.168.0.1 'sync; /sbin/reboot'`. In that session the TCP `812`
helper sent a frame but did not reboot, so require a real SSH drop and uptime
reset. During reconnect, reject the Hitron route and wait for the Polaris BSSID
plus `wlp8s0` route before checking source provenance, component hashes,
process/listener ownership, and physical camera behavior.

### 4. Verify recovery

After the reboot:

- The `polaris_d13e86` AP reappears at signal 40+ on the 2.4 GHz radio.
- SSH to `root@192.168.0.1` succeeds.
- `/app/FwVer` shows the new version.
- `/app/bin/polestar_app` and `/app/bin/pgphoto` exist and have the expected
  sizes.

If any of those are wrong, do **not** attempt a second bypass. Re-stage the
SD card with a known-good `FwPkt.zip` and repeat from step 1.

### Provenance gate (before you stage ANY zip — cross-repo, cross-agent)

Before staging a zip on the SD card, it must have a row in
`docs/FWPKT-PROVENANCE-CONTRACT.md`. This binds every repo (`BenroPolarisPatcher`,
`OpenPolaris`, the libgphoto2 fork) and every agent session:

1. **You built it** → add its registry row *now* (zip MD5 + SHA-256, payload appfs
   MD5 from `firmwareInfo`, libgphoto2 commit SHA, patcher commit/branch).
   Recompute the hashes from the actual file; do not copy them from a doc.
2. **You received it** (from another agent, human, repo, or machine) → verify all
   four handoff values against its registry row before staging:

   ```bash
   md5sum FwPkt.zip                 # == registry "zip MD5"
   sha256sum FwPkt.zip             # == registry "zip SHA-256"
   unzip -p FwPkt.zip FwPkt/firmwareInfo | grep appfs   # appfs MD5 == registry
   ```

3. **No matching row** → the zip is *unprovenanced*. Do not stage it; reconcile
   first (add the row, or get the sender's four values). A hand-zipped tree with a
   correct payload still needs its outer hash recorded — that is exactly the gap
   behind the 2026-09-07/08 v3 incident.

**Where to fetch zips.** Every zip this project builds is uploaded to the
**private** `ian-morgan99/PrivateResearch` repo under
`firmware-packets/<registry-id>/FwPkt.zip` (see the `fwpkt-private-upload`
skill). If a registry row's location points there, clone/fetch that folder and
verify all four handoff values against the row before staging. The public repos
never contain the zip bytes — only the row.

## Things that are NOT allowed

The following are explicitly prohibited because they have either bricked the
device in the past or are known to leave it in an unrecoverable state:

1. **Editing `/app/bin/polestar_app` or `/app/bin/pgphoto` over SSH.** Even
     a "small" patch. The on-boot watcher compares the entire NAND appfs
     MD5 against `firmwareInfo`, so any in-place edit is invisible to the
   watcher, leaves NAND inconsistent with what `/app/FwVer` reports, and
   will be silently rejected on the next boot.

2. **Editing `/app/lib/stage2/libpolaris_stage2.so` over SSH.** Same
   reason as. (1). The patcher loader sits in `/app/lib/stage2/` and is
   in a different MD5 bucket from `/app/bin/polestar_app`.

3. **Editing `/app/conf/*`, `/app/FwVer`, `/app/yocto/...` over SSH.**
   These are factory-validated; in-place edits don't propagate to NAND's
   reference MD5 set.

4. **Dropping only `FwPkt.zip` on the SD card without pre-extracting.**
   The watcher ignores it.

5. **Pre-extracting into a subdirectory** (e.g. `/FwPkt/FwPkt/...`).
   Doubles the prefix, watcher finds nothing.

6. **Replacing only some files in `/FwPkt/camera/` or `/FwPkt/gimbal/`.**
   The watcher's per-file MD5 compare means a partial replacement is
   silently rejected.

7. **Manual NAND writes** (`flash_erase`, `nandwrite`, etc.) — no agent
   should ever need to do this; U-Boot handles NAND writes during the
   sanctioned flow.

If you find yourself wanting to do any of these, **stop and write a
`FwPkt.zip` instead**. The patcher (`container/`) supports building one
locally. If a real change is needed that the patcher cannot express, file
an issue rather than working around the rule.

## What about non-firmware changes?

- **Patcher source / scripts** in `container/`: edit freely on the PC.
  These don't touch the device.
- **Documentation** (`README.md`, `docs/`, `CHANGELOG.md`): edit freely.
- **Local builds** under `builds/`: edit freely on the PC; only stage via
  the sanctioned flow above.
- **Test cards / SD snapshots** under `docs/evidence/`: read-only on the PC.
- **NAND or `/app/...` on the device**: see above. No direct edits. Ever.

## If the rule was just violated by a previous session

Recovery is possible, but only via the sanctioned flow:

1. Pull the SD card, mount it read-only on the PC.
2. Capture `/system/log/` to `docs/evidence/fwpkt-install/on-card-logs-<date>/`
   before doing anything else — the SD card is the only persistent record
   of what the wedged boot was doing.
3. Stage a known-good `FwPkt.zip` (typically `firmware/FwPkt.zip`, the
   stock Aug-22 build) as the pre-extracted `/FwPkt/` tree on the SD root.
4. Reseat, clean power-cycle, wait 5–10 min.
5. Once SSH returns, diff `/app/bin/polestar_app` against
   `firmware/FwPkt.zip`'s extracted copy to see exactly what the bypass
   session changed. Update `STATE.md` with the post-mortem.
6. Do **not** attempt a second bypass to "fix what the first bypass did"
   without first filing an issue and getting explicit user approval.

---

## Waking the gimbal and keeping it alive

> **Why this is in here.** The Benro Polaris' SoC, Wi-Fi AP, and BLE radio
> sleep together. When the AP drops, BT discovery goes with it, so the
> usual "scan → connect" path doesn't help if the gimbal is asleep. The
> same goes for keeping it awake during long operations (firmware install,
> log pulls, big SCPs): without a keepalive pulse, the gimbal will
> de-sleep mid-task and drop your SSH session. This section is the
> canonical reference for both.

### Constants you will need

| | |
|---|---|
| Gimbal BT MAC | `48:E7:DA:D4:B5:72` (combo chip; Wi-Fi MAC is `48:E7:DA:D4:B5:73`) |
| Gimbal AP SSID | `polaris_d13e86` (2.4 GHz, open) |
| Gimbal SSH | `root@192.168.0.1` |
| Gimbal control port | TCP `9090` |
| Gimbal lighttpd | TCP `80` |

### Wake from deep sleep with a bare BT connect

The OpenPolaris project discovered (see
`OpenPolaris/shared/src/jvmMain/kotlin/dev/openpolaris/core/net/BluetoothProbe.kt`,
`wake()` at line120, comment "Benro Polaris wakes on a bare GATT connect")
that a bare `bluetoothctl connect <MAC>` is the wake pulse once the gimbal
is **powered on** (LED blue = idle-wake state; if no LEDs, charge or
power-button the gimbal first — BT cannot wake it from a hard-off).

Canonical wake sequence in a single piped `bluetoothctl` session:

```bash
POLARIS_BT="48:E7:DA:D4:B5:72"
timeout 30 bluetoothctl <<EOF
power on
scan on
pair ${POLARIS_BT}
trust ${POLARIS_BT}
connect ${POLARIS_BT}
quit
EOF
```

The `connect` itself is the wake. The connection settles in ~2s. After the
connect:

1. The `polaris_d13e86` AP appears on the 2.4 GHz radio (poll
   `nmcli -t -f BSSID,SSID device wifi list` for `48:E7:DA:*`).
2. SSH on `22`, lighttpd on `80`, and `polestar_app` on `9090` come up
   within a few seconds of the AP being visible.

If the AP does not appear within ~60s, the gimbal is either still
booting, in a deeper sleep state, or not actually powered on. Re-run
the BT connect (a second pulse often works after the first one
partially wakes it). `WAIT_AP_SECS=300` is a safe override for slow
post-reflash boots.

If the BT MAC is not yet known to bluez (e.g. fresh install, bluez
restarted), run `bluetoothctl --timeout 15 scan on` first to discover it.

### One-shot wake + probe

The OpenPolaris project ships a script that does wake + AP wait + nmcli
join + SSH poll + first-look probe in one shot:

```bash
sudo /home/ian/Documents/VSCodeProjects/OpenPolaris/docs/evidence/gimbal-ssh-2026-08-31/wake-and-probe.sh
```

Tunables:

- `WAIT_AP_SECS=300` — extend the AP-wait window (useful right after a
  reflash, when the gimbal takes longer to bring hostapd up).
- `POST_UPDATE=1` — chain into `post-fw-update-probe.sh` after SSH is
  up, to capture FwVer diff vs baseline + `/app/sd/FwPkt/` extracted
  dir + upgrade-marker Mlog tail + port 9090 listener. Don't set this
  if you're just doing a generic first-look after a clean boot.

The script writes evidence to
`OpenPolaris/docs/evidence/gimbal-ssh-2026-08-31/probes-<timestamp>/`,
including `01-first-look.txt` (the on-device probe output) and a few
pulled files (`/proc/version`, `/proc/mtd`, the latest Mlog).

### Keeping the gimbal awake

The gimbal re-sleeps when its BT-paired host (the phone or, in our case,
this PC) leaves range, OR when polestar_app's own idle timer expires
(the default idle is short — measured at ~5 minutes of no TCP traffic on
9090). For any operation longer than a few minutes, run a keepalive
loop on the PC.

Two keepalive mechanisms, pick one:

#### A. Protocol-level keepalive (preferred for long jobs)

Speak the polaris wire protocol from the PC so the gimbal sees an active
host. The protocol is ASCII over TCP port 9090, format
`1&<code>&<subtype>&<payload>#`. Code `266` (status ping) is the cheapest
keepalive — `polestar_app` replies with a status frame and resets its
idle timer.

```bash
keepalive_9090() {
  while :; do
    printf '1&266&0&#' | timeout 4 nc -q1 192.168.0.1 9090 >/dev/null 2>&1
    sleep 30
  done
}
```

Background it for the duration of the long job:

```bash
keepalive_9090 &
KPID=$!
# ... do the long job ...
kill "$KPID" 2>/dev/null
```

This is more reliable than BT-keepalive because it doesn't depend on
the BT radio staying awake, and it works even if the PC and the gimbal
are on different physical radios (e.g. gimbal on BT, PC on wired
ethernet — `192.168.0.1` is reachable through the gimbal's own NAT).

#### B. BT-keepalive (fallback if you can't speak the protocol)

If you need the gimbal awake but cannot open TCP 9090 (e.g. you're
debugging the daemon itself), hold the BT connection open. bluez treats
an active GATT connection as a paired host, which keeps the gimbal's
sleep policy from de-sleeping the SoC.

```bash
keepalive_bt() {
  while :; do
    timeout 25 bluetoothctl connect 48:E7:DA:D4:B5:72 >/dev/null 2>&1
    sleep 20
  done
}
```

`BT-keepalive` has two failure modes:

1. If the BT-paired phone is **not in range** but the PC's BT is, the
   gimbal still considers "a paired host" to be present and won't
   sleep. That's the mode you want.
2. If the PC's BT goes out of range too, the gimbal sleeps and you
   cannot wake it via BT until you power-cycle it (or press the
   physical button).

Use BT-keepalive when you're physically close to the gimbal and the PC
but the long operation is purely passive (e.g. tailing Mlog).
Prefer 9090-keepalive otherwise.

### What "in range" actually means

This trips people up. "Range" for the polaris sleep policy is "BT
link alive to **any** paired host", not "BT link alive to the host I
care about". If your phone and the PC are both paired to the gimbal
but the phone is on the dock in the kitchen, and the PC is at the
desk, the gimbal still considers itself "hosted" because the PC's BT
link is alive.

Consequence: **if you lose the BT link from the PC, but the phone is
still in range, the gimbal will not sleep**. And vice versa. This is
why the BT-keepalive works even though `polaris_d13e86` SSID is hidden
and the BT pairing was done by the iPhone app originally.

### Forcing a sleep (rarely needed)

If you need the gimbal to actually go to sleep — for example, to test
that a wake pulse still works, or because you want to put it away —
there is no clean "sleep" command. The cleanest ways are:

- Disconnect every BT-paired host from the gimbal (turn off the
  phone's BT, drop the PC's BT link) and wait ~5 minutes for the
  idle timer to expire.
- Power it off via the iPhone app's "Reboot" (`812`) command or
  `scripts/reboot-via-812.sh`, and don't press the power button again.
  After ~30s the SoC powers down completely.

Do **not** unplug power from a running gimbal mid-task. It can leave
NAND in a half-written state and silently corrupt the appfs (the
`space_fixup` UBIFS flag the patcher preserves is partly about
mitigating this, but it's not a guarantee).

### Common mistakes

- **Pressing the BT-wake pulse before the gimbal is powered on.** The
  pulse does nothing against a hard-off SoC. Confirm at least one LED
  (blue = idle-wake, green = AP+BT active, blue+green = booted and
  AP+BT both up) before trying to BT-wake.
- **Running `nmcli connection up polaris_d13e86` while the AP is not
  yet broadcasting.** nmcli will hang on `configuring` for the
  association timeout (~20s), then give up. Always check
  `nmcli -t -f BSSID,SSID device wifi list | grep -i 48:E7:DA`
  first.
- **Assuming the saved PSK in `nmcli` is correct.** The polaris
  rotates its PSK on certain events (firmware reflash, factory reset).
  If association fails with a stored profile, `nmcli connection delete
  "polaris_d13e86"` and re-add with `nmcli device wifi connect
  polaris_d13e86 --ask` — the SSID is open in known firmwares, so
  `--ask` only confirms. If you have a PSK, pass `--password`.
- **Hoping `nc 192.168.0.1 9090` will reach the gimbal over the
  wired home router.** When the polaris AP drops, `192.168.0.1` on
  the wired side resolves to the Hitron CGNV4-FX4 cable router, not
  the gimbal. The `scripts/resilient-monitor.sh` script handles this
  correctly (it requires a *real* `polaris_*` association, not just
  pingability); copy that logic into any custom monitoring you write.
- **Re-flashing while a long-running 9090-keepalive is active.** The
  keepalive will re-trigger a fresh session with polestar_app every
  boot. Either kill the keepalive before staging the SD card, or
  expect noisy Mlog `SP_EVENT_APP_CONNECT` entries during the install.

### Cross-references

- `OpenPolaris/docs/evidence/gimbal-ssh-2026-08-31/wake-and-probe.sh` —
  the canonical one-shot wake + first-look probe.
- `OpenPolaris/shared/src/jvmMain/kotlin/dev/openpolaris/core/net/BluetoothProbe.kt`
  — `wake()` at line 120, source of the BT-wake approach.
- `OpenPolaris/shared/src/jvmMain/kotlin/dev/openpolaris/core/net/BridgeOrchestrator.kt`
  — `wakeOverBluetooth()` at line 86.
- `scripts/resilient-monitor.sh` — continuous read-only monitor that
  does the "is the gimbal actually ours" check correctly (uses the AP
  association, not just pingability, to distinguish the gimbal from
  the home router).
- `scripts/reboot-via-812.sh` — clean reboot trigger (the same `812`
  wire command the iPhone app uses).
- `STATE.md` § "Live device" + § "Sleeping-when-phone-leaves" — the
  day-to-day operational notes.

---

## Quick reference

| Action | Allowed? |
|---|---|
| Edit `container/` patcher source on PC | ✅ |
| Build a `FwPkt.zip` on PC via `patch-polaris.sh` | ✅ |
| Validate a built `FwPkt.zip` with `validate_fw_package.py` | ✅ |
| Pre-extract `FwPkt.zip` → `/FwPkt/` on SD root, verify MD5s, reseat | ✅ (only if it has a provenance-registry row) |
| Stage a zip with no `docs/FWPKT-PROVENANCE-CONTRACT.md` registry row | ❌ |
| Edit `/app/bin/*` on the device over SSH | ❌ |
| Edit `/app/lib/stage2/*` on the device over SSH | ❌ |
| Drop `FwPkt.zip` alone on SD root | ❌ |
| Pre-extract into `/FwPkt/FwPkt/...` (double prefix) | ❌ |
| Partial replacement of files in `/FwPkt/camera/` or `/gimbal/` | ❌ |
| Manual `flash_erase` / `nandwrite` from device shell | ❌ |

## See also

- `docs/evidence/fwpkt-install/ROOT-CAUSE-2026-09-01.md` — the silent-reject
  root-cause analysis that established why this layout is the only one the
  on-boot watcher reads.
- `docs/silent-fwpkt-reject-postmortem.md` — the original 2026-08-27 silent
  reject, traced to a stale `firmwareInfo` after a layered repack. The same
  failure mode applies to any zip whose MD5 entries don't match the bytes.
- `docs/fwpkt-zip-layout-and-smb-delivery.md` — the zip-prefix contract and
  the per-file MD5 validation rules.
- `docs/FWPKT-PROVENANCE-CONTRACT.md` — cross-repo/cross-agent registry: which
  FwPkt bytes are which, by commit links + hashes; the handoff rule that binds
  every repo and agent session.
- `STATE.md` — the live investigation state; updated whenever a session
  violates this rule or recovers from one.

### For BT-wake and keepalive (this skill's second half)

- `OpenPolaris/docs/evidence/gimbal-ssh-2026-08-31/wake-and-probe.sh` —
  canonical one-shot wake + first-look probe (BT wake → AP wait → nmcli
  join → SSH poll → first-look evidence).
- `OpenPolaris/shared/src/jvmMain/kotlin/dev/openpolaris/core/net/BluetoothProbe.kt` —
  `wake()` at line 120, the source of the BT-wake approach.
- `OpenPolaris/shared/src/jvmMain/kotlin/dev/openpolaris/core/net/BridgeOrchestrator.kt` —
  `wakeOverBluetooth()` at line 86.
- `scripts/resilient-monitor.sh` — continuous read-only monitor that uses
  AP association (not just pingability) to distinguish the gimbal from
  the home router.
- `scripts/reboot-via-812.sh` — clean reboot trigger.
- `STATE.md` § "Sleeping-when-phone-leaves" — day-to-day operational notes.
