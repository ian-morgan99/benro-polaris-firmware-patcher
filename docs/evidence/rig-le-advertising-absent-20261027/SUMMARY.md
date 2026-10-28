# BLE wake is impossible — the rig never advertises LE (host radio is fine)

Date: 2026-10-27. Investigated live against an **awake, SSH-verified** rig
(`FwVer:6.0.0.54.76;date:2026.10.27;`).

> **Correction notice.** An earlier revision of this file concluded the host
> radio was "deaf" (`acl:0`, zero devices on both transports). That conclusion
> was **wrong** and came from two measurement bugs in my own tooling, not from
> any host fault. Both are recorded below because they are easy to repeat.

## The real finding

The rig does not advertise BLE at all, even when fully awake. The documented
wake pulse (`bluetoothctl connect 48:E7:DA:D4:B5:72`) therefore can never be
delivered from Linux — there is nothing to connect to.

### Evidence

Rig confirmed awake over SSH on `wlp8s0`:

```
FwVer:6.0.0.54.76;date:2026.10.27;
hci0: BD Address 48:E7:DA:D4:B5:72   UP RUNNING PSCAN ISCAN
```

Host radio proven able to receive, by clearing the BlueZ cache and rescanning:

```
$ bluetoothctl remove 48:E7:DA:D4:B5:72
$ bluetoothctl --timeout 35 scan on
[NEW] Device 59:B7:EC:B5:78:B2 59-B7-EC-B5-78-B2      <-- host radio DOES receive
   rig MAC absent                                      <-- rig advertises nothing
```

The rig's own log explains it, on **every** boot (5 of the last 5 Mlogs):

```
SP_BlueSetAdvertiseState[2949]: advertise on
Failed to register advertising object
SP_BlueSetAdvertiseState[2949]: advertise on
SP_SetBleState[81]: ble slave on
```

`advertise_on=2 reg_fail=1` in each: the first registration attempt fails and a
second is issued immediately. `SP_EVENT_BT_CONNECT` still appears later in the
same log, so BR/EDR carries connections despite the LE registration failure —
which is why a phone app connects while a Linux BLE client finds nothing.

Classic discovery also failed both ways this session: PC `hcitool scan --flush`
did not report the rig, and with the PC `Discoverable: yes` the rig's
`hcitool scan` did not report the PC. LE is the documented wake path, so that is
what matters here.

## The measurement bugs behind the false "deaf radio" claim

All four are now pinned by `tests/test_bt_wake_radio_liveness.py`.

**1. Wrong grep pattern.** `bluetoothctl` prints `[NEW] Device <MAC> <name>`,
not `New Device <MAC>`. Every scan in this repo grepped for the latter, so it
could never match and a healthy radio always looked empty.

**2. ANSI colour codes from the portal PTY.** `flatpak-spawn --host` allocates a
PTY, so `bluetoothctl` colourises output even when piped:

```
$ flatpak-spawn --host bluetoothctl --timeout 25 scan on | cat -A
[^[[0;92mNEW^[[0m] Device 5A:7A:CA:C1:3E:33 5A-7A-CA-C1-3E-33$
```

The literal `[` and `]` are separated by escape sequences, so even a corrected
`\[NEW\]` pattern matches nothing. Strip first:

```bash
sed -r 's/\x1b\[[0-9;]*[a-zA-Z]//g'
```

**3. `acl:0` was misread as proof of deafness.** It is not. LE advertisements
arrive as HCI events, not ACL packets, so an adapter that only ever scans
legitimately shows `acl:0`. The rig's `acl:96` merely reflects connections it
had carried. RX byte growth during a scan is likewise unusable: `hciconfig`'s RX
counter includes command-complete responses to our own commands, which arrive
with no RF traffic at all.

**4. `[NEW]` fires once per device.** BlueZ emits it only when a device is first
added to its model, so repeat scans of the same room return zero on a working
radio. Three back-to-back scans here gave `1, 0, 0`.

Consequence: **an empty scan proves nothing in either direction** — not that a
radio is dead, and not that the rig is asleep. `polaris-bt-probe.sh` returns
`LIVENESS_UNKNOWN` rather than inventing a `RADIO_DEAF` verdict, and
`polaris-preflight.sh` decides `ASLEEP` from AP absence via the Wi-Fi scan, which
does not depend on the Bluetooth stack.

## Host facts that remain true (but are not faults)

| field | value |
|---|---|
| USB ids | `0489:e10a` (Foxconn/Hon Hai) |
| BD address | `4C:23:38:C8:7B:70` |
| Manufacturer | Qualcomm (29) |
| kernel | `CONFIG_BT_HCIBTUSB_QCA` unset; `btqca` not loaded |
| firmware | `/lib/firmware/qca/`: 23 `nvm_usb_*` files, no `.htf` RAM patch |

The QCA RAM-patch gap is real and unexplained, but it has **not** been shown to
break reception — the adapter demonstrably receives LE advertisements. Recorded
so the observation is not lost; it is not a blocker.

## Ruled out

* **USB runtime PM.** `power/control=on`, `runtime_status=active`, `usage=1`.
* **rfkill.** `Soft blocked: no / Hard blocked: no`.
* **Sandbox isolation.** Host tools are reachable via `flatpak-spawn --host`;
  inside the Flatpak `/dev/hci0` is absent and `AF_BLUETOOTH` returns `Errno 97`.
  Those are sandbox restrictions, not host faults, and must never be cited as
  evidence about the radio.

## Consequences for this repo

* **BLE wake cannot be validated from any Linux host** until the rig's LE
  advertising registration succeeds. This is a firmware defect, not a host or
  tooling problem.
* Prior evidence recording "host has no BT adapter" or "no BLE advertisement
  seen" (`o-v17a-offline-validation-20261012` §8 and the `o-v17a-*` wake
  blockers) was one of: sandbox isolation, the wrong grep pattern, or the rig
  genuinely not advertising. None were a dead radio.
* `scripts/polaris-bt-probe.sh` centralises route resolution, ANSI stripping and
  the correct `[NEW] Device` pattern; the new test file pins all four bugs with
  stub binaries, so they cannot silently return.

Raw output: `raw/host-bt-state.txt`, `raw/scan-and-rig-advertising.txt`.
