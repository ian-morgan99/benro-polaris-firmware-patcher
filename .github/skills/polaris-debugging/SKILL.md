---
name: polaris-debugging
description: "Debugging guide for junior agents working on the Benro Polaris gimbal camera stack. USE FOR: SSH access, device identity and routing checks, pgphoto/gphoto2 camera-path tests, log collection, Bluetooth wake and Wi-Fi connection, and defect ownership. DO NOT USE FOR: building or flashing FwPkt.zip, or editing libgphoto2 source."
---

# Polaris debugging guide (junior agents)

This is the operational playbook for debugging the Benro Polaris gimbal and its
camera stack. It distils what actually worked across the agent sessions (see
`docs/evidence/`, `OpenPolaris/docs/evidence/`, and the 2026-09-07 patcher#36–39
investigations). Read it top to bottom once; then use the quick reference at the
end.

## 1. Getting the SSH connection

Constants (memorise these):

| | |
|---|---|
| Gimbal SSH | `root@192.168.0.1` (OpenSSH 7.8p1, `PermitRootLogin yes`) |
| Gimbal AP SSID | `polaris_d13e86` (2.4 GHz, open in known firmwares) |
| Gimbal Wi-Fi MAC | `48:E7:DA:D4:B5:73` (BT MAC is `...B5:72`, combo chip) |
| Gimbal control port | TCP `9090` (ASCII wire protocol `1&<code>&<subtype>&<payload>#`) |
| Gimbal lighttpd | TCP `80` |

How SSH access exists on the device:

- Stock firmware already runs sshd (`/etc/init.d/rcS` ends with
  `/usr/local/bin/sshd`). What it does **not** have is any key in
  `/root/.ssh`, so stock access is by root password.
- The patcher ships `container/gen_ssh_hook.py`, which generates an
  `/app/network_telnetd.sh` boot hook (a file the stock `bootapp` already
  sources) that installs your public key into `/root/.ssh/authorized_keys` at
  boot. That hook is part of a FwPkt build — it is **not** something you add by
  hand over SSH (see §6, no direct code changes).
- Accepted key types: `ssh-ed25519`, `ssh-rsa`, `rsa-sha2-*`, ecdsa, sk-*
  (no `ssh-dss` — sshd 7.8 rejects it).

Connection procedure:

```bash
# 0. Make sure the gimbal is awake and its AP is up (see §5 for BT wake).
# 1. Join the gimbal's own AP — NOT your home network:
nmcli -t -f BSSID,SSID device wifi list | grep -i '48:E7:DA'   # confirm AP visible
nmcli device wifi connect polaris_d13e86 --ask                # open SSID; --ask only confirms
# 2. Verify you are on the gimbal, not the router (see §2), then:
ssh root@192.168.0.1 'cat /app/FwVer'                          # must print FwVer:...
```

If association fails with a stored profile, the Polaris rotates its PSK on
reflash/factory-reset: `nmcli connection delete "polaris_d13e86"` and re-add.

## 2. Making sure you are looking at the Polaris, not the router

**This is the trap that has burned sessions.** The home cable router
(Hitron CGNV4-FX4) also answers on `192.168.0.1` on the wired side. When the
gimbal's AP drops, `ping 192.168.0.1` and even `nc 192.168.0.1 9090` can reach
the **router**, not the gimbal. Pingability is NOT proof of identity.

Do all three checks before trusting any result:

```bash
# (a) You must be associated with a real polaris_* AP, BSSID prefix 48:E7:DA:
nmcli -t -f BSSID,SSID device wifi list | grep -i '48:E7:DA'

# (b) The route to the gimbal must go out your wireless interface:
ip route get 192.168.0.1        # expect "dev wlp8s0" (or your wifi dev), NOT eth/br0

# (c) The host must be the gimbal itself — the router has no /app:
ssh root@192.168.0.1 'cat /app/FwVer; ls /app/bin/polestar_app /app/bin/pgphoto'
# expect: FwVer:4.0.0.32;date:... and both files present
```

`scripts/resilient-monitor.sh` implements this correctly (requires a real
`polaris_*` association, not just pingability). Copy that logic into any custom
monitoring you write. If (a)–(c) fail, you are talking to the router: every
log line, port probe, and "device state" you read is garbage — re-associate and
start over.

## 3. Testing the device with pgphoto / gphoto2 on-device

Background you need: `/app/bin/pgphoto` is Benro's camera-control daemon. In a
patched build it is a small `sh` wrapper that sets `CAMLIBS`/`IOLIBS`/
`LD_LIBRARY_PATH`, `LD_PRELOAD`s the Stage-2 loader, and execs
`/app/lib/stage2/pgphoto.stage2ondisk`. The running daemon **owns TCP 8080**
(preview) and holds the USB camera. If it is running while you test directly,
the two compete for the camera and results are meaningless.

The reliable on-device test path (proven in the patcher#36 investigation —
"direct CLI works, packaged runtime doesn't" was exactly how the root cause was
found) is the **direct gphoto2 CLI with the Stage-2 library paths**:

```bash
ssh root@192.168.0.1 '
  # 1. Stop the daemon so it does not compete for the camera:
  PID=$(cat /var/run/openpolaris-pgphoto.pid 2>/dev/null)
  [ -n "$PID" ] && kill -TERM "$PID" 2>/dev/null
  i=0; while [ -n "$PID" ] && [ -d "/proc/$PID" ] && [ "$i" -lt 10 ]; do
    sleep 1; i=$((i+1))
  done

  # 2. Run the direct CLI against the same libgphoto2 stack the device ships:
  D=/app/lib/stage2
  LD_LIBRARY_PATH=$D:/app/lib \
  CAMLIBS=$D/libgphoto2/2.5.34 \
  IOLIBS=$D/libgphoto2_port/0.12.2 \
  /app/bin/gphoto2 --auto-detect 2>&1 | head

  # 3. Prove the camera actually works:
  LD_LIBRARY_PATH=$D:/app/lib \
  CAMLIBS=$D/libgphoto2/2.5.34 \
  IOLIBS=$D/libgphoto2_port/0.12.2 \
  /app/bin/gphoto2 --capture-preview --filename=/tmp/preview.jpg 2>&1 | tail -3

  # 4. Restart the daemon and confirm it comes back healthy:
  /app/restart_gphoto; sleep 5
  tail -20 /app/Clog.txt
'
```

`/app/stop_gphoto` does not exist on the tested 4.0.0.32 image family. Use the
PID-file + exact-process TERM sequence above; avoid broad `pkill` in a
qualification run. The watchdog may relaunch pgphoto after roughly 30 seconds,
so keep the direct test bounded and always restore service with the packaged
`/app/restart_gphoto` helper.

Interpreting results (the source/runtime ownership rule from `AGENTS.md`):

- **Direct CLI FAILS** with camera attached → candidate libgphoto2 defect
  (file in the libgphoto2 fork repo).
- **Direct CLI PASSES, packaged pgphoto/Stage-2 path FAILS** → patcher /
  pgphoto / Stage-2 / loader / path / session issue (patcher repo).
- **Both pass but OpenPolaris still fails** → OpenPolaris client/protocol issue.

Compare the first divergent lower-level PTP operation, not just final GP error
numbers. Do not "fix" a Polaris-only symptom by editing libgphoto2 without a
direct reproducer.

Useful daemon-side checks:

```bash
ssh root@192.168.0.1 '
  lsusb | grep 25fb                      # camera USB ID (Pentax = 25fb:xxxx)
  ps | grep -E "pgphoto|polestar"        # is the daemon alive? which binary?
  cat /proc/$(pgrep -f pgphoto.stage2ondisk)/maps | grep libgphoto2   # WHICH core is loaded (see §7)
  tr "\0" "\n" < /proc/$(pgrep -f pgphoto.stage2ondisk)/environ | grep -E "CAMLIBS|IOLIBS"
'
```

Known-good signatures: `sp_Gphoto_Init ret 0` in Clog (not `-2`), camera info
code `286` reporting `state:1`, and no `No iolibs found in
'../lib/libgphoto2_port/0.12.0'` line.

Common `sp_Gphoto_Init ret` failure codes seen on-device:

| ret | Meaning | First thing to check |
|---|---|---|
| `-105` | "Could not detect any camera" / `list count = 0` — camera present on USB but not enumerated by the camlib (K-1 II under o-v5b, patcher #50) | Is the camera actually on the bus (`lsusb \| grep 25fb`)? Which mode is it in? Does a direct CLI at this SHA detect it? |
| `-53` | "Could not claim the USB device" — another process (usually pgphoto) holds the interface | Stop the daemon first (§3); check `fuser /dev/bus/usb/*` |
| `-2` | iolibs lookup failed (`No iolibs found in '../lib/libgphoto2_port/0.12.0'`) — #38 dual-path defect class | §7 checks: do the two core MD5s match? Which core is loaded? |
| `-5` | init error (seen once on K-1 II; also reported as `state:-5` after a physical disconnect) | Re-check USB attach + retry; if persistent, compare against direct CLI |

### §3a. Gotchas that cost real time (learned 2026-09-09, K-3 III sweep)

**The CLI can fail at *load* with a port-lib relocation error — this is #51,
not your bug.** If the direct CLI dies before doing anything:

```
/app/bin/gphoto2: relocation error: /app/lib/libgphoto2.so.6: symbol
gp_port_init_localedir, version LIBGPHOTO2_5_0 not defined in file
libgphoto2_port.so.12 with link time reference
```

Cause: the #38 fix replaced the stock **core** but (as of o-v5b) not the stock
**port**, so the CLI's `RPATH=/app/lib` pairs a fresh 2.5.34 core with the old
2.5.27 port. Workaround — force the matched stage2 port:

```bash
LD_PRELOAD=/app/lib/stage2/libgphoto2_port.so.12 \
CAMLIBS=/app/lib/stage2/libgphoto2/2.5.34 \
IOLIBS=/app/lib/stage2/libgphoto2_port/0.12.2 \
/app/bin/gphoto2 --auto-detect
```

Scope `LD_PRELOAD` to the `gphoto2` invocation only (e.g. `env LD_PRELOAD=…
gphoto2 … >> log 2>&1`) — if it leaks into `tee`/`grep` in a pipeline they fail
with `libltdl.so.7: cannot open shared object file`. Track the permanent fix in
patcher issue **#51**. The fix is present from `o-v6-lockfix`: both stock and
Stage-2 core/port pairs must have matching hashes.

**The watchdog restarts pgphoto every ~30 s.** After you stop it for a direct-CLI
test, you have a short window before `polestar_app` relaunches it and reclaims
the USB camera (symptom: your CLI suddenly gets "Could not claim the USB
device" / `-53`). Do the whole test in one SSH session right after the stop,
or expect to repeat. The ~30 s cadence is also what users see as the camera
"trying to connect but failing" when init keeps erroring.

**`scp` from this device often fails with `Connection closed`** (no SFTP
subsystem). Prefer a single tar-stream:
`ssh … 'cd dir && tar czf - files' | tar xzf -`. For many files,
stream them with `===FILE:name===` markers in one connection and split locally —
faster than N separate SSH sessions.

**Camera state codes you will see in Mlog/Clog:** `code[286]` = camera info
(`manufacturer:…;model:…;state:N;storage:N;photoFormat:N`; `state:1` healthy,
`-5`/`0` gone), `code[284]` = mode/state heartbeat, `code[279]` = SD event,
`val[-100]` on 266/284/286 = keepalive/no-data. A clean camera death shows a
kernel uevent (`NetlinkUeventTask … remove@…usb1/1-1.x`) + `usb_disconnect`
followed by 286 flipping to `manufacturer:none;model:none` — that is a physical
unplug/battery-flat, not a protocol fault.

## §3b. Direct-on-PC baseline test (the decisive ownership experiment)

Before routing any camera defect, AGENTS.md requires the **direct exact-SHA +
directly-attached-camera** result. Do it on the host PC with the fork's own
harness — no gphoto2 CLI build needed:

```bash
cd /home/ian/Documents/VSCodeProjects/LibGphoto2/libgphoto2
git log --oneline -1          # MUST equal the device's git_commit (provenance file)
ninja -C _build examples/pentax-safe-preview   # builds in seconds if libs are current

export LD_LIBRARY_PATH="$PWD/_build/libgphoto2:$PWD/_build/libgphoto2_port/libgphoto2_port" \
       CAMLIBS="$PWD/_build/camlibs/ptp2" \
       IOLIBS="$PWD/_build/libgphoto2_port/libusb1:$PWD/_build/libgphoto2_port/usbscsi"
lsusb | grep 25fb            # get the bus,device (e.g. usb:001,039)

./_build/examples/pentax-safe-preview "Pentax K-1 Mark II (PTP mode)" usb:BUS,DEV 5
# or: "Pentax K-3 Mark III (MTP mode)" for the K-3 III
```

Use the public ability names printed by `gphoto2 --list-cameras`: they contain
`Pentax K-...`, not the internal table spelling `Pentax:K-...`. With multiple
bodies attached, a failed exact-model lookup is fatal; never fall back to
autodetection. Confirm the harness prints the expected model, VID:PID and port.

For a final control qualification, build and run the constrained harnesses one
at a time:

```bash
ninja -C _build examples/pentax-safe-preview \
  examples/pentax-safe-focus examples/pentax-safe-shutter-roundtrip
./_build/examples/pentax-safe-focus "$MODEL" "$PORT" near-lv
./_build/examples/pentax-safe-focus "$MODEL" "$PORT" far-lv
./_build/examples/pentax-safe-shutter-roundtrip "$MODEL" "$PORT"
```

Focus is PASS only when PC-LV yields a valid JPEG before the one bounded drive,
the model-specific opcode is accepted, another valid JPEG arrives afterwards,
and cleanup succeeds. Record physical lens direction separately; protocol
acceptance cannot prove visible motion. Shutter is PASS only when the harness
derives the live baseline, selects a non-Bulb exposure no longer than 1/30 s,
verifies it through `pentaxconditions`, and restores the exact baseline. Do not
use a harness that assumes a particular starting shutter value.

Interpretation (this is what decides repo ownership):

| Result | Ownership |
|---|---|
| Harness FAILS (init / no frames) with camera attached to PC | candidate **libgphoto2** defect → file in `ian-morgan99/libgphoto2` |
| Harness PASSES but Polaris fails | **Polaris-local** (pgphoto/Stage-2/session/loader) → this repo |
| Both pass, app still misbehaves | **OpenPolaris** client/protocol issue |

Known-good baseline (2026-09-10, K-1 II @ 990281d72): init OK, then ~9
NoUpdateImage warmup attempts, then `get-frame returned 0x2001 (8023 bytes)` and
`frame=1..5 valid_jpeg=yes`. Remember: **in this fork `PTP_RC_OK == 0x2001`** —
a "0x2001" in a log line is *success*, not an error.

Preview-specific gotcha (see #36/#55): the camera needs several seconds after
start-PC-LV before its first frame. At deployed libgphoto2 `990281d72`, a
terminal/cancelled preview failure (including exhausted `0xa008` retries) calls
`pentax_restore_live_view(params, 0)` unconditionally. The
**`pentaxpclvkeep`** widget preserves PC-LV across successful preview calls only;
it does not preserve PC-LV on this failure path. Therefore setting the widget in
pgphoto cannot by itself fix the observed `0xa008` churn. Preserving PC-LV while
NoUpdateImage is transient requires an explicit, bounded libgphoto2 error-path
change plus direct and Polaris hardware qualification. Independently, the
Polaris outer request loop must back off/cancel after repeated failed requests
so it cannot starve the Wi-Fi radio.

## 4. Reading and downloading log files

Where logs live on the device:

| Path | What it is |
|---|---|
| `/app/Clog.txt` | gphoto/camera-stack log (the one `restart_gphoto` appends to) |
| `/app/Mlog.txt` | main polestar_app log |
| `/app/yocto/run/customer/Mlog/Mlog_<n>.log` | rotating Mlog history (NOT in `/var/log`) |
| **`/app/sd/system/log/Clog_*.log`, `Mlog_*`, `error_*`, `access_*`** | the SD card mounted at `/app/sd` — the persistent record. This is where the numbered Clog/Mlog files actually live on a running device (verified 2026-09-09). If you pull the SD to the PC it appears as `/system/log/`. |

Notes: Mlog/Clog can contain binary bytes — use `grep -a` when grepping them.
The numbered logs rotate per boot/session; identify today's by mtime (`ls -lt
/app/sd/system/log | head`).

Reading:

```bash
ssh root@192.168.0.1 'tail -50 /app/Clog.txt'
ssh root@192.168.0.1 'tail -50 /app/Mlog.txt'
# grep the rotating history for a symptom:
ssh root@192.168.0.1 "grep -l 'No iolibs' /app/yocto/run/customer/Mlog/Mlog_* | tail -3"
```

Downloading (always archive into `docs/evidence/<topic>-<date>/` in the repo
you are working in, with an INDEX or timestamped filenames). **Prefer the SD log
dir** — it is the persistent record and survives reboots:

```bash
mkdir -p docs/evidence/polaris-logs-$(date +%F)
# scp often fails on this device (no SFTP); use cat or a tar stream instead:
ssh root@192.168.0.1 'cat /app/Clog.txt' > docs/evidence/polaris-logs-$(date +%F)/Clog.txt
ssh root@192.168.0.1 'cd /app/sd/system/log && tar czf - Clog_*.log Mlog_*.log error_*.log' \
  | tar xzf - -C docs/evidence/polaris-logs-$(date +%F)/
```

If the device is wedged (no SSH, no AP), pull the SD card and read
`/system/log/` from the PC — that is how the 2026-09-07 brick was diagnosed.
Capture it **before** re-staging anything: it is the only record of what the
wedged boot was doing.

## 5. Starting the device with Bluetooth, connecting wirelessly (incl. sandbox)

The SoC, Wi-Fi AP, and BLE radio sleep together. A **bare GATT connect is the
wake pulse**. Start the saved Wi-Fi-profile activation first, overlap it with a
retained GATT connection, and release GATT only after NetworkManager reports
that Wi-Fi is active. It does not pair, discover the vendor service, or write a
characteristic. Disconnecting GATT before starting Wi-Fi can miss the short
wake window even though the connect itself succeeded.
BT cannot wake a hard-off SoC: confirm at least one LED first (blue = idle-wake;
no LEDs = charge or power-button it).

Canonical handoff (run the Wi-Fi activation and BLE connect concurrently):

```bash
POLARIS_BT="48:E7:DA:D4:B5:72"
nmcli --wait 60 connection up polaris_d13e86 &
NM_PID=$!
while kill -0 "$NM_PID" 2>/dev/null; do
  timeout 12 bluetoothctl connect "$POLARIS_BT" || true
done
wait "$NM_PID"
bluetoothctl disconnect "$POLARIS_BT" || true
```

The `connect` itself is the wake; the retained connection keeps the wake window
open while NetworkManager associates. `ServicesResolved: yes` is useful
evidence, but do not wait for it before beginning Wi-Fi activation. Then:

1. The `polaris_d13e86` AP appears on 2.4 GHz (poll
   `nmcli -t -f BSSID,SSID device wifi list | grep -i 48:E7:DA`).
2. SSH `22`, lighttpd `80`, and `polestar_app` `9090` come up within seconds.

If direct connect fails because BlueZ has no cached device, run
`bluetoothctl --timeout 15 scan on` once and retry. Pair/trust may be used only
as a cache-recovery fallback; it is not part of the normal wake. If the AP is
not visible within ~60 s, re-run the concurrent association/connect handoff; after a
reflash use `WAIT_AP_SECS=300`.

One-shot wake + AP wait + join + SSH poll + first-look probe:

```bash
sudo /home/ian/Documents/VSCodeProjects/OpenPolaris/docs/evidence/gimbal-ssh-2026-08-31/wake-and-probe.sh
# tunables: WAIT_AP_SECS=300, POST_UPDATE=1 (chains post-fw-update-probe.sh)
```

**Keeping it awake during long jobs** (log pulls, big SCPs, firmware install):
the idle timer is ~5 min of no TCP traffic on 9090. Preferred keepalive is the
protocol ping:

```bash
while :; do printf '1&266&0&#' | timeout 4 nc -q1 192.168.0.1 9090 >/dev/null 2>&1; sleep 30; done &
```

Fallback (debugging the daemon itself, can't open 9090): hold the BT link open
(`timeout 25 bluetoothctl connect $POLARIS_BT` in a loop). Note "in range"
means *any* paired host — if your phone is docked nearby, the gimbal won't
sleep even when the PC's BT link drops.

**Sandbox use:** run the agent/PC side in a VM or container that has access to
a Bluetooth adapter and a 2.4 GHz Wi-Fi radio (or USB-BT dongle passed
through). The whole flow above is host-side; nothing about it requires the
physical bench except the camera USB cable. Inside the sandbox:

1. `bluetoothctl` wake pulse (§5) → wait for AP.
2. `nmcli device wifi connect polaris_d13e86 --ask`.
3. Verify identity with §2 checks (a router on the same L2 will fool you).
4. `ssh root@192.168.0.1` and proceed with §3/§4.
5. Background the 9090 keepalive for any job longer than a few minutes; kill it
   before staging an SD-card reflash (it otherwise re-triggers polestar_app
   sessions every boot and makes Mlog noisy).

## 6. No direct code changes on the device — everything via GitHub issues + firmware

**Rule (from `AGENTS.md`):** do not replace camera-stack binaries directly under
`/app` over SSH as a supported fix. SSH is **read-only diagnostic by default**.
A temporary, explicitly authorised experiment invalidates all qualification
evidence until a canonical FwPkt is reinstalled.

The only sanctioned change path:

```text
GitHub issue (repro + evidence)
 -> source change in the owning repo (see §7 routing)
 -> clean patcher build (container/)
 -> architecture/ABI/provenance gates
 -> immutable FwPkt.zip + manifest (registry row in docs/FWPKT-PROVENANCE-CONTRACT.md)
 -> SD-card install via on-boot watcher (fwpkt-update-flow skill)
 -> cold reboot
 -> runtime-loader proof
 -> physical camera regression matrix
```

Why: the 2026-09-07 incident — an agent session edited `/app/bin/` and
`/app/lib/` over SSH, tried to revert, and left the device wedged
(`pgphoto` gone, `FATAL early call to gp_port_new @slot=...`, watchdog crash
loop starving the radios). Only the SD-card Mlog survived. The recovery was the
sanctioned flow; the bypass itself was the cause.

Practical consequences for you:

- Over SSH: read (`cat`, `ls`, `stat`, `tail`, `ps`, `/proc/...`), run the
  direct CLI tests of §3, pull logs. That's it.
- Want to change a binary, env file, or script on the device? File an issue in
  the owning repo, fix it there, rebuild the FwPkt, flash via SD card.
- If you *must* do a one-off on-device experiment (explicitly authorised),
  record exactly what you changed and when; the next canonical FwPkt install
  resets the evidence baseline.

### Proven remote SD staging flow (2026-09-09)

When the Polaris is reachable but its camera daemon is wedged, the complete
pre-extracted package can be staged remotely to the mounted SD card without
touching NAND directly. This successfully installed registry artifact
`o-v6-lockfix` and was substantially faster and smoother than moving the card.

Use it only when all of these preconditions pass:

1. Device identity is proven by Polaris BSSID, `wlp8s0` route, and `/app/FwVer`.
2. The exact ZIP already has a provenance-registry row and its local hashes have
   just been recomputed.
3. `find /app/sd -maxdepth 3 -type f` proves there is no old/partial `FwPkt`
   tree. Never merge two packages.
4. The gimbal has stable power. Stop any 9090 keepalive before rebooting.

Stage the whole extracted tree and verify the bytes on the card:

```bash
BUILD=/absolute/path/to/registered-build
tar czf - -C "$BUILD" FwPkt |
  ssh root@192.168.0.1 'tar xzf - -C /app/sd && sync'

ssh root@192.168.0.1 '
  cd /app/sd/FwPkt &&
  md5sum camera/config camera/uImage camera/rootfs.ubifs camera/appfs.ubifs \
    gimbal/polaris403_*.bin gimbal/polaris413_*.bin &&
  cat firmwareInfo
'
```

Every printed MD5 must match `firmwareInfo` and the registry appfs MD5. Abort
before reboot on any mismatch. With no physical card reseat available, the
verified 2026-09-09 trigger was:

```bash
ssh root@192.168.0.1 'sync; /sbin/reboot'
```

This invokes the normal boot-time watcher against `/app/sd/FwPkt/`; it is not a
direct NAND write. The `812` TCP helper did not reboot this unit in that session,
so verify an actual SSH drop and uptime reset rather than trusting a sent frame.

During the install the wired router may answer at the same address. Accept the
device only after the real `48:E7:DA:D4:B5:73` AP returns and
`ip route get 192.168.0.1` again names `wlp8s0`. Then prove installation using
embedded source provenance, component hashes, one pgphoto owner, one 8080
listener, `/proc/<pid>/maps`, and a physical camera operation. On the successful
v6 run, the full outage was about one minute and live view returned a valid JPEG.

**Second successful run (2026-09-10): `o-v7-preview-shims`.** Same flow, end to
end: staged via `tar czf - | ssh … 'tar xzf - -C /app/sd && sync'`, all six
on-card MD5s matched `firmwareInfo` + the registry row (zip `9e2addfc…`, appfs
`66cb2604…`), triggered with `sync; /sbin/reboot`. Back in ~5 min. Post-boot
proof: `/app/openpolaris-libgphoto2-provenance.txt` = `git_commit=38780d88b`,
single pgphoto owner, and the **#38/#51 dual-path check passed on this build** —
`md5sum /app/lib/stage2/libgphoto2.so.6 /app/lib/libgphoto2.so.6` matched
(`6ae6c633…`) with `/proc/<pgphoto>/maps` showing the stage-2 core loaded (the
o-v6 mismatch is gone). OpenPolaris issue #73 documents this route for adoption
by the app's firmware-upload process.

**Field-test caveat from that run (K-3 III, o-v7):** first capture after a
preview session succeeded; the *second* was refused by the camlib's stale
transfer-candidate guard (`A previous capture's transfer candidate (1) is still
pending` → `GP_ERROR_CAMERA_BUSY`, 9090 state `-110`) — see patcher #37. Also:
the Stage-2 loader logged **no** `[stage2] keep-lv:` line for the K-3 III, so
Shim #4's model gate needs verification (suspect: `gp_camera_get_abilities` at
init time returns a different/empty model string than expected). Do not assume
the preview shims are active on-device until that log line appears.

**Do not misdiagnose the v7 live-view/control failure (2026-09-10 K-1 II).** A
12-second HTTP 8080 capture contained two `Content-Length` parts and two complete
JPEG SOI/EOI pairs (25,930 bytes total), so this is not an empty-boundary
failure. It is an unusably slow/interfering stream: Clog showed successful
12--13 KB Pentax frames (~9 attempts, ~275 ms) interleaved with
`waitCameraIdle busy` and failed config/control calls. Shortly afterward the
Polaris AP, SSH, 9090, and Bluetooth connection all disappeared together. The
AP later recovered without a reboot: uptime continued and the original
polestar/pgphoto PIDs were still alive. Persistent monitor snapshots contained
Broadcom driver failures `No more free tdata_psh_info!!` and
`Out of tdata_disc_grp`, establishing Wi-Fi transmit bookkeeping/pool exhaustion
as the immediate outage mechanism, not an OS or camera crash. Live view is a
load trigger; do not claim it is the sole cause without a one-client A/B run.
Preserve the SD and monitor logs before rebooting.

The unstripped stock `pgphoto` makes the busy message precise. Function
`waitCameraIdle` is at `0x000fd32c` (`gpManager.c:2087`). It polls
`gp_params.status` at struct offset `0xab0` every 2 ms; DWARF names the enum
values `CAMSTATUSIDLE=0` and `CAMSTATUSBUSY=1`. It does **not** read Pentax
GetAllConditions state directly. Therefore `waitCameraIdle busy` proves Benro's
application-global scheduler is occupied; it does not prove that Pentax
condition `state=3` was classified as camera busy. Correlate the status holder,
concurrent 8080/9090 clients, and the first process/radio failure before choosing
a fix. Run qualification with one deliberate preview client: close other app,
desktop, emulator, and ad-hoc HTTP clients or record them explicitly.

**K-3 III focus prerequisite (direct HW, exact v7 source SHA).** Image
Transmitter 2 only enables Near/Far inside PC live view. At libgphoto2
`38780d88`, off-LV minimum Near/Far returned `0xa00c`; in a same-session harness
that first obtained a valid JPEG and retained PC-LV, minimum Near (`+23`) and Far
(`-23`) each returned `0x2001` on the first `0x9017`, with zero retries and
successful d035/keep cleanup. Four surrounding preview frames remained valid.
Do not alter the opcode, direction sign, displacement, or retry count to fix an
off-LV failure. The downstream sequence must be: start and prove PC-LV -> issue
one bounded focus command -> prove another frame -> explicitly stop/restore LV.
Protocol acceptance is not physical direction observation; record those as
separate gates.

## 7. Which GitHub repo owns which defect (logging logic)

Route every issue to the layer that **first diverges** — never to the layer
where the symptom is most visible:

| Repo | Owns | File issues here when… |
|---|---|---|
| `ian-morgan99/libgphoto2` (fork) | core / port / camlib / iolib source | The **direct** CLI at the exact libgphoto2 SHA fails with a directly-attached camera. A Polaris-only symptom is NOT enough — you need a direct reproducer first. |
| `ian-morgan99/benro-polaris-firmware-patcher` (this repo) | Stage-2 / pgphoto wrapper / loader (`libpolaris_stage2.so`) / firmware packaging / FwPkt build & provenance | Direct CLI passes but the packaged pgphoto/Stage-2 path fails; iolibs/camlib lookup problems; `/app/bin/` content; wrapper env; FwPkt layout/MD5 issues. |
| `ian-morgan99/OpenPolaris` | client / 9090 protocol / UI / state / BT wake orchestration | Both device paths pass but the app misbehaves; protocol framing, liveview, capture commands (264/286/291), wake logic. |
| `BenroHardwareValidator/benro-polaris-test-harness` | deterministic regression fixtures only | Once a defect is evidenced, it may be modelled here — but the harness never owns the underlying defect and a harness PASS is never proof of physical camera support. |

Evidence discipline: keep direct-libgphoto2 evidence separate from Polaris
runtime evidence and OpenPolaris E2E evidence. Every FwPkt zip gets a registry
row (zip MD5+SHA-256, appfs MD5, libgphoto2 commit SHA, patcher commit) in
`docs/FWPKT-PROVENANCE-CONTRACT.md` **before** handoff; a zip without a row is
unprovenanced and must not be staged.

### The #38 dual-path issue — what it was and how to avoid it

Issue #38 (`docs/ISSUE-38-39-FIXES-2026-09-07.md`, design doc in
`OpenPolaris/docs/evidence/2026-09-07/patcher-38-fix-design/`) was the
**two-libgphoto2-paths** defect:

- **Path a (trampolined):** `pgphoto.stage2ondisk` loads
  `/app/lib/stage2/libgphoto2.so.6` by absolute path → worked.
- **Path b (stock):** a child process loaded the **stock**
  `/app/lib/libgphoto2.so.6` (2.5.27) via relative lookup, which searched for
  iolibs at `../lib/libgphoto2_port/0.12.0/iolibs/iolibs/` relative to CWD
  `/root` → `No iolibs found`, `sp_Gphoto_Init ret -2`, `state:-2`.

The early misdiagnosis (a "stripped stub" port lib) cost a session; the real
fix was making **both paths load the same fresh 2.5.34 core**: `container/patch.sh`
now also replaces the stock `/app/lib/libgphoto2.so.6` with the freshly built
core, so path b resolves iolibs correctly too.

Avoiding it in future builds — check all of these:

1. **Build gate:** the patcher build must include the stock-core replacement
   step (search `container/patch.sh` for `STOCK_CORE`). A build that only
   populates `/app/lib/stage2/` reproduces #38.
2. **Post-flash check on device** — both cores must be byte-identical:

   ```bash
   ssh root@192.168.0.1 'md5sum /app/lib/stage2/libgphoto2.so.6 /app/lib/libgphoto2.so.6'
   # the two hashes MUST match; a mismatch = dual-path defect present
   ```

3. **Runtime check** — see which core the live daemon actually loaded:

   ```bash
   ssh root@192.168.0.1 'grep libgphoto2 /proc/$(pgrep -f pgphoto.stage2ondisk)/maps'
   # expect only /app/lib/stage2/libgphoto2.so.6; if /app/lib/libgphoto2.so.6
   # appears, the stock path is active — verify its iolibs resolve (or the
   # cores match per check 2).
   ```

4. **Symptom signature:** `No iolibs found in '../lib/libgphoto2_port/0.12.0'`
   + `sp_Gphoto_Init ret -2` + `manufacturer:none;model:none;state:-2` in
   Clog = this defect class until proven otherwise.
5. **Companion gate (#39):** the post-repack content assertion in
   `container/patch.sh` (re-extracts the finished appfs and asserts
   `/app/bin/pgphoto` exists, is executable, contains the wrapper markers, and
   the Stage-2 set is present) must have run — a zip that passes MD5 checks
   but is missing `/app/bin/pgphoto` is the #39 failure mode.

### Persistent launch-lock failure (issue #34, fixed in v6)

The original mkdir launch lock had no owner metadata. If the wrapper was killed
after acquiring it, the directory remained; on this firmware `/var/run`
persists across an OS reboot. Every watchdog launch then exited successfully
without starting pgphoto. The identifying state is: camera present in `lsusb`,
polestar/9090 alive, no pgphoto process, no 8080 listener, and Clog repeating
`another pgphoto launch is already in progress`.

Do not delete the lock by hand and treat that as qualification. Archive the
lock/PID/backoff state, install registered `o-v6-lockfix` or later, and prove
one pgphoto owner plus one 8080 listener. The v6 wrapper records its PID inside
the lock, preserves live-owner locks, and reclaims dead/unknown-owner locks.

### Preview proof (avoid the HTTP-200 false positive)

`291@state:1;ret:0`, `292@state:1`, and HTTP 200 prove only control and HTTP
setup. A passing preview needs a positive multipart `Content-Length`, JPEG SOI
bytes `ff d8`, a complete decodable JPEG, and repeated frames/cadence. A bare
`--boundarydonotcross\r\n` remains a FAIL.

Without curl, inspect the first part using:

```bash
printf 'GET /?action=stream HTTP/1.1\r\nHost: 192.168.0.1:8080\r\nConnection: close\r\n\r\n' |
  timeout 8 nc 192.168.0.1 8080 | head -c 4096 | xxd
```

The first successful post-v6 K-3 III probe returned `Content-Length: 78417`
followed by `ff d8`. That proves a real frame, but a longer capture is still
required for cadence/performance qualification.

For raw 9090 qualification, use the command's real subtype and keep one socket
open long enough to receive asynchronous pushes. Proven examples are camera
info `1&286&4&#`, live-view get `1&292&2&#`, live-view set
`1&291&2&state:1;#`, focus adjust `1&311&1&mode:1;adj:-1;#`, and capture
`1&264&4&state:1;bulb:0;c:-1;#`. A frame sent with the wrong subtype can be
silently ignored; an empty short-lived `nc` result is therefore NOT TESTED,
not a failure.

Do not qualify focus from `311@ret:0` alone. The 2026-09-11 v9d K-3 III run
returned success for both directions while the operator observed no lens
movement and Clog contained no model-aware `0x9017` dispatch line. Focus needs
physical movement/direction or an equivalent lower-level dispatch trace plus
post-command JPEG proof. Likewise, do not suggest a longer client wait when
capture has already emitted terminal `state:-1005`: inspect Clog for the
underlying result. In that run it was `GP_ERROR_CAMERA_BUSY (-110)` because a
previous transfer candidate was still pending; waiting in the UI cannot clear
that camera-side lifecycle state.

## Quick reference

| Task | Command / rule |
|---|---|
| SSH in | join `polaris_d13e86` → `ssh root@192.168.0.1` (key via patcher boot hook, or root password) |
| Prove it's the gimbal | `nmcli … \| grep 48:E7:DA` + `ip route get 192.168.0.1` → wifi dev + `cat /app/FwVer`; use embedded provenance/hashes, not FwVer, to identify the patcher build |
| Test camera on-device | stop daemon → direct `gphoto2` with `CAMLIBS/IOLIBS/LD_LIBRARY_PATH` from `/app/lib/stage2` → restart daemon, tail Clog. Watchdog reclaims USB in ~30 s — do it in one session |
| Direct-on-PC baseline (ownership) | Fork repo: build the constrained harnesses; pin core, `CAMLIBS=_build/camlibs/ptp2`, and both USB I/O module paths exactly as in §3b; use the public exact-model name and explicit port. PASS means Polaris-local; FAIL means candidate libgphoto2 defect. |
| CLI dies at load (`relocation error … LIBGPHOTO2_5_0`) | #51: `LD_PRELOAD=/app/lib/stage2/libgphoto2_port.so.12` (scope to the gphoto2 call only) until the port replacement ships |
| Read logs | `/app/Clog.txt`, `/app/Mlog.txt`; **persistent numbered logs at `/app/sd/system/log/`** (`grep -a` — they can be binary); wedged device → pull SD, read `/system/log/` on PC |
| Download logs | `scp` often fails (no SFTP) → prefer `ssh 'tar czf - …' \| tar xzf -`; archive into `docs/evidence/<topic>-<date>/` |
| Wake device | `bluetoothctl connect 48:E7:DA:D4:B5:72` (gimbal powered on, LED lit) → AP appears → join → SSH |
| Keep awake | 9090 ping loop (`1&266&0&#` every 30 s); BT-keepalive as fallback |
| Change the device | GitHub issue in owning repo → FwPkt build → SD-card install. Never edit `/app` over SSH as a fix |
| Pre-release gate (mandatory) | `./tests/run_prerelease_gate.sh [--build out/<cand>/FwPkt] [--canary [--two-shot]]` — fail-closed; RED = do not stage/install; SKIPs are prerequisite gaps, record them. Every verified-working behaviour must have a coded test wired into this gate (see AGENTS.md "Pre-release gate") |
| Canary after install | Camera ON: `--canary` (probe + one shot, lifecycle completion + 773 file event) or `--two-shot` for the two-distinct-files standard. Camera OFF at deployment: live gates SKIP — candidate is "installed, canary pending", never qualified; run the canary as soon as the camera is attached |
| Dual-path (#38/#51) check | Stage-2 and stock hashes must match for both `libgphoto2.so.6` and `libgphoto2_port.so.12`; grep `/proc/PID/maps` for active paths |

## 7. K-1 II deployment hazards (learned 2026-09-11/12, o-v9f → o-v9h)

**Boot-with-preview-ON radio starvation (#55/#64).** With a Pentax camera
attached and the app's preview ON at power-on, pgphoto hammers PTP back-to-back;
the sustained traffic starves the Broadcom Wi-Fi driver and SSH/Wi-Fi drop while
BT keeps advertising (flapping every ~40 s). The device often recovers on its
own within minutes — poll `uptime` rather than assuming a hard wedge. o-v9h
(`6.0.0.54.1`) bounds the *preview* loop (any non-zero `gp_camera_capture_preview`
result now counts toward the 3-failure/30 s cooldown). **Known residual gap:**
the K-1 II's 5 s `get_single_config failed: -2` config-poll loop (#59) is a
second unbounded PTP source not yet bounded — expect flapping until that is fixed.

**Verify the backoff actually engaged before trusting it.** Grep Clog for
`[stage2] preview-backoff: N consecutive failures (last ret=...)`. Only the
init-time `slot -> shim` line means the wrapper is installed, NOT that it fired.

**Camera must be on the USB bus before any camera-path test.** `lsusb | grep
25fb` empty = "no camera" — check power + cable seat first; a fitted-but-off or
loose K-1 II produces a pgphoto restart loop (repeated `[stage2] init` blocks in
Clog) with no PTP traffic at all.

**Provenance now carries `build_id`.** Since o-v9h,
`/app/openpolaris-libgphoto2-provenance.txt` ends with `build_id=6.0.0.54.N`.
Always verify BOTH `git_commit=` and `build_id=` against the registry row before
qualification — patcher-only builds share a libgphoto2 commit (o-v9g vs o-v9h
both `90736a1ac`), which is how 5 h of K-1 II testing ran on the wrong build
(2026-09-11, issue #58).

**Reboot trigger reliability.** `scripts/reboot-via-812.sh` (the app's "Reboot"
wire command) is flaky — it can send the frame without rebooting (observed
2026-09-12: uptime kept counting). Use `ssh root@192.168.0.1 'sync; /sbin/reboot'`
as the reliable trigger; if using 812, require a real SSH drop + uptime reset
within 30 s or fall back.

## Cross-references

- Patcher issue **#51** — #38 core-only replacement leaves the stock port stale,
  breaking the CLI path (`LIBGPHOTO2_5_0` relocation error); workaround in §3a.
- `.github/skills/fwpkt-update-flow/SKILL.md` — the only sanctioned firmware
  install path + BT wake/keepalive detail.
- `AGENTS.md` — ownership rules, no-runtime-mutation rule, provenance contract.
- `docs/ISSUE-38-39-FIXES-2026-09-07.md` — the dual-path fix and post-repack assertion.
- `OpenPolaris/docs/evidence/2026-09-07/patcher-36-investigation/FINDINGS.md` —
  the 12-step direct-CLI-vs-runtime reproduction method used here in §3.
- `OpenPolaris/docs/evidence/gimbal-ssh-2026-08-31/wake-and-probe.sh` — one-shot
  wake + probe script.
- `scripts/resilient-monitor.sh`, `scripts/reboot-via-812.sh` — gimbal-vs-router
  monitor and clean reboot.
- `docs/FWPKT-PROVENANCE-CONTRACT.md` — the zip registry every handoff must hit.
- `tests/run_prerelease_gate.sh` + AGENTS.md "Pre-release gate" — the mandatory coded regression gate (offline harness, pytest invariants, FwPkt structural + firmwareInfo manifest gates, live canary/two-shot). Fail-closed; its output is the release evidence.
