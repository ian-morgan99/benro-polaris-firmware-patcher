# Orion StarShoot All-in-One — "not recognised at all" (2026-10-23, `6.0.0.54.69`)

User plugged in an Orion StarShoot All-in-One; nothing recognised it.

This is exactly the device of **issue #158** — `docs/ORION-STARSHOOT-ADAPTER-CONTRACT.md`
is titled *"#158 Orion StarShoot All-in-One (16c0:29a0) — Adapter Contract"*. So the
report is a re-confirmation of known unimplemented scope, not a new defect.

## Not observed on the host this time

The device was already unplugged when I probed. Enumeration at probe time
(`device-state.txt`):

```
8  1a40:0101 USB2.0 HUB
1  1d6b:0002 xHCI Host Controller
1  1d6b:0003 xHCI Host Controller
/dev/video*      -> none
/dev/ttyUSB*, /dev/ttyACM* -> none
```

No `16c0:29a0`. My continuous capture (3 s polling) contains **zero** sightings of
`16c0`/`29a0` across all of today's logs, so whether the kernel enumerated it during
your session is unverified. Historical evidence from 2026-09-29 does show it enumerating
(`lsusb = Bus 001 Device 022: ID 16c0:29a0`, with a reconnect cycle on port `1-1.2` —
the same port the iPolar used).

## Why non-recognition is expected — verified on the shipped artifact, not from docs

I did not take the 2026-09-29 plan's word for it. Checked the current tree and the
**shipped `.69` binary**:

| check | result |
|---|---|
| `container/stage2_starshoot_adapter.c` / `.h` | present (5,209 / 1,512 bytes) |
| references in `stage2_loader.c`, `stage2_policy.c/h` | **zero** — no `adapter_init()`, no policy |
| `container/patch.sh:457-462` | compile-check only (`-c -o starshoot_adapter.o`) |
| `strings` on shipped `libpolaris_stage2.so` for `starshoot\|star_shoot\|qhy5` | **0 matches** |

So the adapter is compiled but never linked or called. Nothing in `.69` can see a
StarShoot. **Unimplemented scope, not a regression.**

## Correction: the libusb prerequisites *are* present

I first reported libusb as absent because `ls /usr/lib/libusb* /lib/libusb*` found
nothing. That was wrong — the libraries ship under `/app`:

| check | result |
|---|---|
| `/app/lib/libusb-1.0.so`, `.a` | **present** |
| `/dev/bus/usb/` | present, with bus dirs `001` and `008` (the devfs path libusb 1.0 uses) |

That answers adapter-contract open item #3 in the affirmative: the libusb backend has
both its library and its device path on this device. It is not the blocker.

## The actual blocker

Per the contract, item #2 is the blocking prerequisite and is still open: **identify the
QHY5L-II / INDI command protocol and SDK version for `16c0:29a0`**
(`docs/ISSUE-158-QHY5L-II-PROTOCOL.md`). Without the protocol, linking the adapter
changes nothing observable — which is why the plan's step 8 insists on not claiming PASS
on linkage alone.

Also worth noting from contract line 38: a PID change `16c0:29a0` → `16c0:29a1` is
anticipated, and item #1 says the family *"spans UVC + vendor-protocol variants"*. So if
your All-in-One presents a different PID than `29a0`, that matters — capture it.

## What to record next time it's attached

```bash
export PATH="$PWD/tools/host-bin:$PATH"
ssh root@192.168.0.1 'for d in /sys/bus/usb/devices/*/idProduct; do v=$(dirname $d); \
  echo "$(cat $v/idVendor):$(cat $v/idProduct) $(cat $v/product 2>/dev/null)"; done; \
  echo "--- class ---"; for f in /sys/bus/usb/devices/*/bDeviceClass; do cat $f; done | sort -u; \
  echo "[end]"'
```

Expected: `16c0:29a0` (or `29a1`) with device class `ff` (vendor-specific). Class `ef`/
`0e` instead would mean a UVC variant, which is a different code path entirely. Note that
no kernel driver will claim a class-`ff` device, so it appearing in the list *without* any
`/dev` node is normal and is not itself a failure.

## Related

- **#158** — this device; adapter unlinked, protocol unidentified (blocking).
- **#159** — iPolar, separate device/protocol/linkage. Do not combine the steps.
- **#213** — log retention; no Mlog/Clog evidence of this session survives.

## Artifacts

- `out/starshooter-20261023/device-state.txt` — enumeration after unplugging (no StarShoot)
