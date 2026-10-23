# iOptron iPolar — "not recognised at all" (2026-10-23, `6.0.0.54.69`)

User report: plugged an iPolar into the Polaris, **nothing recognised it**.

## What I could and could not observe

The device was already unplugged when I probed, so **the kernel-side binding for this
session is unverified**. Current enumeration (saved to `device-state.txt`):

```
8  1a40:0101 USB2.0 HUB
1  1d6b:0002 xHCI Host Controller
1  1d6b:0003 xHCI Host Controller
```

No `1233:1455` (the iPolar's measured VID:PID per `docs/IPOLAR-UVC-BACKEND-PLAN.md`),
and no `/dev/video*` nodes. So I cannot say whether the kernel bound it — only that
nothing is attached now.

## Correction to my first reading

I initially reported the UVC driver as absent because `grep -c uvc /proc/modules`
returned `0`. **That was wrong** — `/proc/modules` lists only loadable modules, not
built-ins. The actual state on this kernel (`4.9.37`):

| check | result | meaning |
|---|---|---|
| `/sys/module/uvcvideo/` | present, `version 1.1.1`, params `clock/hwtimestamps/nodrop/quirks` | driver is in the kernel |
| `/sys/bus/usb/drivers/uvcvideo/` | present with `bind`, `new_id`, `remove_id` | registered and bindable |
| `/proc/devices` char 81 | `81 video4linux` | V4L2 core is present |
| `/dev/video*` | none | no UVC device currently attached |

So the kernel UVC path is **available**, which answers part of open item #1 in
`docs/IPOLAR-UVC-BACKEND-PLAN.md` — the module is there, contrary to that document's
note that "the absence of a separate `uvcvideo.ko` file in the idle audit is
inconclusive". `modprobe` cannot run anyway (`/lib/modules` does not exist), so nothing
would be loadable on demand regardless.

## Why "not recognised" is the expected outcome today

Per the same plan's implementation status (2026-10-04):

> `patch.sh` only compile-checks the adapter and frame store, and **no runtime
> camera-source consumer calls them**. No packaged or Polaris hardware support claim is
> justified until the common camera-source interface is linked and exercised on Polaris
> with a real iPolar.

So even if the kernel created `/dev/video0`, nothing in the patched stack would surface
the device to Benro Connect. **"Not recognised" is unimplemented scope (#159), not a
regression** — and it is consistent across every build to date, including `.69`.

Two distinct layers, which should not be conflated:

1. **Kernel**: `uvcvideo` + V4L2 present → `/dev/video*` *should* appear on attach.
   Unverified for this device on this kernel.
2. **Application**: no camera-source consumer is linked → the app cannot list it,
   regardless of layer 1.

## The decisive check (needs the device plugged in)

This is still open item #1 from the plan and has never been answered on hardware:

```bash
export PATH="$PWD/tools/host-bin:$PATH"
# plug in the iPolar, then:
ssh root@192.168.0.1 'for d in /sys/bus/usb/devices/*/idProduct; do v=$(dirname $d); \
  echo "$(cat $v/idVendor):$(cat $d) $(cat $v/product 2>/dev/null)"; done; \
  ls -la /dev/video* 2>/dev/null; echo "[end]"'
```

Expected if layer 1 works: `1233:1455 iOptron iPolar` plus `/dev/video0` and
`/dev/video1`. If the device enumerates but no `/dev/video*` appears, that is a genuine
kernel/UVC finding worth its own issue. If it does not enumerate at all, suspect power
or hub capability — the Polaris sits behind a `1a40:0101` USB 2.0 hub, and the iPolar
draws more than a camera body would.

Either result is still **not** an application-level recognition failure; that requires
the consumer from #159 to exist first.

## Related

- **#159** — iPolar UVC backend plan (this device, this gap).
- **#158** — StarShoot work, separate from #159 per the plan.
- **#213** — log retention; no Mlog/Clog evidence of this session survives.

## Artifacts

- `out/ipolar-20261023/device-state.txt` — enumeration after unplugging (no iPolar)
