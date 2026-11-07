# astro-v97-liveview-diag-20261106 — plate-solving build with Astro WebUI

Display firmware `6.0.0.54.97`. Built 2026-11-06 from patcher HEAD (baseline
`bf1aad4`, the tree astro-v96 was built from) and libgphoto2 `3fb26e536ac169e4970d69516a9d45daf62563f5`.

**Status: candidate build only.** Identity check `PASS (deployable)`, shared
camera gate GREEN (20 passed, 0 failed), Astro tests 78 passed / 5 skipped.
Nothing was installed, flashed, rebooted or uploaded, and no camera was attached
during the build. Hardware qualification is still required before this is called
a release.

Artifacts (in `out/astro-v97-liveview-diag-20261106/`):

| file | sha256 (prefix) |
|---|---|
| `FwPkt.zip` | `66ff8de8bea3845e…` |
| `astro-bundle.tar.gz` | `dacce9fbf24bb198…` |

The astro bundle tree hash is byte-identical to v96 (`0493ed42…`). That is
expected: the only functional change in v97 is firmware-side (the stage2 crash
classifier). Everything the plate solver and WebUI need was already correct in
v96 and is carried forward unchanged.

---

## Turning Astro on and off

Astro is **additive**. It is never flashed into the firmware image; it lives under
`/app/astro` plus a boot hook, and removing both returns the device to exactly
its prior behaviour. The firmware packet and the astro bundle are independent:
you can flash `FwPkt.zip` without ever installing Astro, and you can uninstall
Astro without reflashing.

### On

Copy the **contents** of `astro-bundle/COPY-TO-SD-CARD-ROOT/` to the root of the
Polaris microSD, put the card back, then run once:

```sh
/app/sd/polaris-astro/install_astro.sh
```

That copies the binaries and scripts into `/app/astro`, creates a `site.conf` if
you have none, seeds `camera-sensors.tsv` if absent, and installs the boot hook at
`/app/network_telnetd.sh`. If a boot hook already exists (the patcher's `--ssh-key`
option uses the same file) it is preserved and chained, so SSH keeps working.

To install the files but **not** autostart:

```sh
NO_BOOT=1 /app/sd/polaris-astro/install_astro.sh
```

### Off

```sh
/app/sd/polaris-astro/uninstall_astro.sh
```

Stops the daemons, restores whatever boot hook was there before (so SSH access
survives), and deletes `/app/astro`. The microSD is left alone: your `site.conf`,
index files, logs and captured frames stay.

### Verify it is on

`polaris-httpd` listens on **:8090**. With the card in and the hook installed:

```sh
ps | grep polaris-httpd
netstat -tlnp 2>/dev/null | grep 8090
```

Then point a browser at `http://<polaris-ip>:8090`. The UI is embedded in the
binary (gzipped into `.rodata`), so it works even if the card is missing,
half-installed or mounted read-only.

### The one trap that bites every time

**Flashing replaces `/app`, which deletes `/app/network_telnetd.sh` — the Astro
autostart hook.** After any flash, Astro silently stops starting on boot and
nothing listens on :8090. This was observed in the wild
(`docs/evidence/liveview-crash-camera-offbus-20261103` §4f). Re-run
`install_astro.sh` after every flash, or restore the hook directly:

```sh
cp /app/sd/polaris-astro/polaris-astro-boot.sh /app/network_telnetd.sh
chmod 755 /app/network_telnetd.sh
```

---

## What this build carries for the Pentax bodies

Both bodies are supported by the shipped driver at
`/app/lib/stage2/libgphoto2/2.5.34/ptp2.so`, verified by reading strings out of
the binary inside `FwPkt.zip` — not from source assumptions.

### K-3 III — Bulb wheel

The shutter-speed list ("bulb wheel") is synthesised when the body returns it
empty. In B mode with no JPEG offered the K-3 III reports an enum count of zero,
which the device forwards as a one-entry list containing a bogus `00:00`, and
Benro Connect crashes on it (issue #241). The driver re-adds the thirteen whole-second
counts the body itself publishes in a populated list — 1, 2, 3, 4, 5, 6, 8, 10,
13, 15, 20, 25, 30 (`PENTAX_BULB_LIST_SECONDS_COUNT` = 13) — so the wheel is never
empty and never carries a bogus value.

Confirmed present in the shipped binary:

```
pentax-shutter: camera returned an empty shutter list (B mode, no JPEG); added %u Bulb/seconds entries
```

Gated deliberately to the **colour** K-3 III only (model 78420, USB product
0x0189). The Monochrome has a distinct IT2 model number and its own published
counts have never been read from hardware, so it stays outside the gate. The
shipped binary says so explicitly:

```
pentax-bulb: K-3 III Monochrome held-Bulb action remains unqualified
```

Bulb writes **fail closed** (issue #239): if the requested duration cannot be
written, the capture is refused rather than silently producing a file at some
unrelated setting.

### K-1 II

Present in the driver's capability table with its own row (`uses_it2_direct_live_view_start`,
dual slot, new transfer, movie, card-writing mode, undeclared generic props), and
its old-focus family handling is in the shipped binary:

```
Drive Pentax old-focus far (K-1 II)
Pentax K-1 II LV AF spot stored (%u,%u); camera does not echo the selection.
```

On-device evidence for K-1 II is **partial**, from `.87` on 2026-10-28: read-only
liveness 3/3, ISO/shutter/aperture lists populated, preview closed cleanly, one
ordinary capture with lifecycle `[1,4,0]`. Bulb, persistent live view, focus and
full setting round-trips are not yet qualified on Polaris.

### Astro profiles

Both bodies ship as data rows, not solver gates, in the bundle's
`polaris-astro/camera-sensors.tsv`: K-3 III 23.3 mm APS-C, K-1 II 35.9 mm
full-frame. Add any other camera by appending `EXIF Model<TAB>sensor width mm`
to that file on the card — no rebuild needed.

`camera-profiles.json` is a host-side build input (`container/astro/`) that seeds
the shipped `.tsv`; it is not itself copied to the device.

---

## The live-view correction in this build

The crash handler in `libpolaris_stage2.so` labelled **every** `pc == 0` fault
"the pre-fix unfilled-slot race". Both observed live-view crashes reported
`resolved 65/65` with checkpoint `slots filled`, so that label was wrong and
pointed the investigation at our loader instead of at the real null-pointer call
inside an already-resolved target.

The handler now scans the slot words with plain volatile loads (async-signal-safe:
no heap, no stdio, no locking) and reports which case actually happened:

- a slot genuinely zero → names it, because that *is* our bug and is actionable;
- all slots non-zero → states plainly that this is **not** the unfilled-slot race.

Verified in the shipped `libpolaris_stage2.so` inside `FwPkt.zip`: the new marker
is present and the old unconditional wording is gone. Compiles clean for ARM with
`-Wall -Wextra -Werror`; all five offline stage2 shim tests pass, including the
live-view keep-alive and preview-error-classification suites.

**This corrects the diagnostic only.** It does not change capture or recovery
behaviour and it does not claim to stop the crash. The root cause is still
unproven; read the new `pc classify` line before assuming anything next time it
dies.

---

## Not fixed — read this before planning a night around it

- **Deferred timed Bulb cancellation (#251) is not fixed.** Nothing writes
  pgphoto's cancel flag, so a started Bulb exposure cannot be cancelled early.
  Accepted for this build at the operator's instruction. Plan sessions assuming a
  Bulb shot runs to its full duration.
- **Live-view SIGSEGV root cause unproven.** Only the mislabelling is fixed.
- **K-3 III Monochrome** has no Bulb wheel or held-Bulb action — needs its own
  hardware pass first.
- **BLE wake** remains impossible: the rig never advertises LE (firmware defect,
  unrelated to this build).

## Validate first, in this order

1. Flash `FwPkt.zip`, then **re-run `install_astro.sh`** (the flash deletes the hook).
2. Confirm :8090 answers and the WebUI loads.
3. Toggle off with `uninstall_astro.sh`; confirm daemons stop and SSH still works.
4. K-3 III: in B mode with no JPEG offered, confirm the shutter wheel is populated;
   then one Bulb capture — it must produce the requested duration or fail closed.
5. K-1 II: re-run liveness, exposure lists, preview open/close, one ordinary capture.
6. If live view crashes, read the new `pc classify` line before theorising.
