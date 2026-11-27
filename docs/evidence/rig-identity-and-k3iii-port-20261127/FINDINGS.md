# Which bytes run, and why the K-3 III "regression" is not a regression

Started from the 27 Nov conversation review's three questions: **which bytes are
running? what transaction did we actually measure? what evidence would disprove our
explanation?** Applied to rig `d13e86` on 2026-11-27. Every claim below names the
command that establishes it. Three of my own explanations were falsified and are
recorded as falsified.

## 1. Which bytes are running — `/app/FwVer` is not evidence

`cat /app/FwVer` returns `FwVer:6.0.0.54.118`. That is a packet-level display stamp
and proves nothing about the loaded stack; the v115 source-pin record already settled
that `strings` on the Stage-2 ELF contains no version marker at all.

The independent proof is `/app/openpolaris-libgphoto2-provenance.txt`:

```text
requested_version=2.5.34   actual_version=2.5.34
git_commit=f48a05e08b54d6d433a556c2df512987a51ce742
patcher_commit=858edfd87be3681d26cbfee4810dff2c25c8696f
build_id=astro-v118-stage2-gate-wedge-fix-20261126
```

And what is actually mapped into the live process (`awk '{print $6}' /proc/249/maps`):

```text
/app/lib/stage2/pgphoto.stage2ondisk
/app/lib/stage2/libgphoto2.so.6
/app/lib/stage2/libgphoto2_port.so.12
/app/lib/stage2/libpolaris_stage2.so
/app/lib/libgphoto2/2.5.27.1/ptp2.so        <- stock, not stage2
/app/lib/libgphoto2_port/0.12.0/usb1.so     <- stock, not stage2
```

### I claimed a mixed-stack defect. It is cosmetic. Retracted.

`CAMLIBS=/app/lib/stage2/libgphoto2/2.5.34` and `IOLIBS=.../0.12.2`, yet the mapped
modules come from the stock `2.5.27.1` and `0.12.0` directories. That looks like a
version-mismatched stack. It is not:

```text
# md5sum /app/lib/stage2/libgphoto2_port/0.12.2/usb1.so \
         /app/lib/libgphoto2_port/0.12.0/usb1.so
18848f0a09841f83fabf296cb52f7173  .../0.12.2/usb1.so
18848f0a09841f83fabf296cb52f7173  .../0.12.0/usb1.so
```

Byte-identical, same size. The directory name is a packaging label; the bytes are the
same build. No functional defect. I asserted a mismatch from path names without
comparing the files — exactly the error class the review warns about.

## 2. The K-3 III never reached the host, and it was plugged into the wrong port

Today's session (`docs/evidence/k3iii-v118-20261126/`) used **direct USB-C, no hub**.
Result: `lsusb` shows no Pentax at all, Bus 002 has no children, and the string `k-3`
appears in none of the 40 log files on the rig.

The variable that changed is not the firmware. Across every evidence file ever
collected, both bodies are always on Bus 001 behind the hub:

```text
# grep -rhoE "Bus 00[0-9] Device [0-9]+: ID 25fb:[0-9]+" docs/evidence/ | sort | uniq -c
     41 Bus 001 Device 003: ID 25fb:0183     <- K-1 II
     35 Bus 001 Device 003: ID 25fb:0189     <- K-3 III
      3 Bus 001 Device 010: ID 25fb:0189
      2 Bus 001 Device 005: ID 25fb:0189
      1 Bus 001 Device 011: ID 25fb:0189
```

And Bus 002 — the USB-C SuperSpeed port — has never enumerated a single device:

```text
# grep -rhoE "Bus 002 Device [0-9]+: ID [0-9a-f:]+" docs/evidence/ | sort | uniq -c
    127 Bus 002 Device 001: ID 1d6b:0003     <- the xHCI root hub, nothing else
```

`1d6b:0003` is the host controller's own virtual device. There is no record in the
entire history of this project of anything attaching on Bus 002.

**Conclusion:** the K-3 III failure is a cabling/topology problem, not a firmware
regression. Test it through the hub at `1-1.2`, where both bodies have always worked.

### The "regression since v114/v115" premise does not survive contact with the data

`git diff 87032af4 HEAD -- container/ondisk/camera_usb_supervisor.sh` is **36 insertions
and 1 deletion**, and the only USB-behaviour change in it is `already_bound_k3iii()`,
which *helps* a K-3 III attach. Nothing in the v114→v118 window changes USB enumeration,
power management or binding.

Two further hypotheses I tested and rejected:

| Hypothesis | Test | Result |
|---|---|---|
| Power pinning is new since v114 and hides the camera | `git show 87032af4:...supervisor.sh \| grep -c "power/control"` | **7** — already present at v114. Rejected. |
| Supervisor latches to the old camera ID, rejecting a swapped body | read `camera_vendor()` and the #126 comment | accepts vendor `25fb` generically; a product change takes the rebind path. Already recorded as refuted in the v118 evidence. |

What genuinely changed at v115 is `fbfa133a fix(stage2): native camera claim via
stage2_camera_claim gate`, which affects both bodies equally — and it is what produces
the refusal telemetry quoted below. It is a real change, but it is not why the K-3 III
does not appear on the bus.

## 3. One K-1 II transaction, end to end — passing

The production entrypoint, not a hand-built reproduction:

```text
# LAT=35.35199 LON=-119.17208 ./solve-now.sh --frame /app/sd/normal/SP_0004.jpg
2026-11-27 03:18:02 extract: SP_0004.jpg fullres=7360x4912 downsample=4 stars=200
                             camera='PENTAX K-1 Mark II' focal_exif=50.0000
2026-11-27 03:18:21 solve SOLVED: 19.07s rc=0 stars=200
```

Capture, extraction, plate solve and result all work on v118 with the K-1 II attached.

## 4. My index-truncation explanation was wrong about the solve failures. Retracted.

`index-4110.fits` on the rig **was** corrupt — 981,504 bytes against a published
24,871,680, md5 `bd38ae95…` instead of `d9aeb509…`. I repaired it. But it was not why
solves were failing:

| Frame | Stars | Result |
|---|---|---|
| SP_0004.jpg (Nov 21) | 200 | **SOLVED** 18.76 s, logodds 501, 54 matches, index-4117 |
| SP_0001.jpg (Nov 21) | 131 | timeout, every hypothesis `0 match, 0 conflict` |
| SP_0011.jpg (Nov 26) | **0** | cannot solve — not a sky frame |
| SP_0049.jpg (Nov 26, newest) | **0** | cannot solve — not a sky frame |

The solver and the index set are healthy. SP_0001 has stars but matches nothing at any
sky position, and today's captures contain no stars at all. Attributing that to firmware
would be wrong; it is subject matter and framing. `0 match, 0 conflict` across every
searched scale is the signature of a frame that does not contain the sky, not of a
broken search.

## 5. A real defect found while chasing that one — fixed here

`astrometry-indexes.zip` ships upstream's whole-series `md5sums.txt` (4107..4119) while
containing only 4110..4119. On the device:

```text
# md5sum -c .md5sums.txt
md5sum: can't open 'index-4107.fits': No such file or directory
index-4107.fits: FAILED          <- x3, for files we never shipped
md5sum: WARNING: 4 of 13 computed checksums did NOT match
```

Three phantom failures sit alongside the one real one and are indistinguishable from it.
That is why the truncated `index-4110` was nearly missed. `scripts/build-astro-candidate.sh`
now prunes the manifest to shipped files before zipping: 13 entries → 10, and
`md5sum -c` returns ten `OK` lines with no warnings. A corrupt file still fails —
verified by test, since #288 established that a bad index yields a confident wrong sky
position rather than an error.

## 6. Open question, left open deliberately

Live view flickers every ~3–4 s (defect A). The gate telemetry answers "what" and not
"why":

```text
site=100540 kind=2 owner_site=100540 last_owner_kind=2 generation=2 budget=500
  tid=290 owner_tid=1600 depth=1 held_ms=629 stolen=0
  ... held_ms=1666 ... held_ms=2710
site=102ff0 kind=0 owner_site=100540 ... held_ms=3358
site=1013ac kind=0 owner_site=100540 ... budget=1250 ... held_ms=5911
```

One config-path claim (`owner_site=100540`, `STAGE2_CONFIG_WAIT_RETURN`) is held for
seconds at a time, and preview waits refuse against it. `stolen=0` and depth bounded at
1, so the lease behaves as designed — the open question is what pgphoto operation holds
a config claim for 4–6 s. That needs a trace of the holder, not more gate instrumentation.

Attribution caution carried over from the v118 findings: refusals exist in logs from
before v118. Do not describe the flicker as introduced by v118 without a pre-v118
measurement of the same cadence.

## Next executable steps

1. Re-test the K-3 III **through the hub** at `1-1.2`. If it enumerates there, the
   regression premise closes and the finding is "USB-C port does not enumerate bodies".
2. If it fails behind the hub too, capture kernel-side USB evidence at the moment of
   attachment — userspace uevents alone have already proved insufficient here.
3. For defect A, trace the holder of `owner_site=100540` to identify the pgphoto call
   that holds a config claim for seconds.
4. Bulb capture end-to-end on v118 remains unverified. Do not record it as fixed.
