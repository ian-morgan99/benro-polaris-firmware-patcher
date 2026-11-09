# #297 — the camlibs load, and the K-3 III is detected: outside pgphoto

Date: 2026-11-09. Device: Astro v99 (`/app`), K-3 III attached at `25fb:0189`.

## Result

Using the artifacts already on the device, with no rebuild and no install:

```
LD_LIBRARY_PATH=/app/lib/stage2:/app/lib
CAMLIBS=/app/lib/stage2/libgphoto2/2.5.34
IOLIBS=/app/lib/stage2/libgphoto2_port/0.12.2
/app/bin/gphoto2 --list-cameras   -> Number of supported cameras: 2492
/app/bin/gphoto2 --auto-detect    -> Pentax K-3 Mark III (MTP mode)   usb:001,004
```

Layers 1–4 are healthy. The camera is enumerated, libgphoto2 loads, the camlibs load, and the
USB port driver claims the device and matches it to the correct model.

## Why this is not a vacuous result

Three controls, each of which would have caught a false positive:

- `CAMLIBS=/nonexistent/dir` gives **0** cameras, not 2492. So the count really comes from the
  directory I passed and there is no compiled-in fallback path.
- `LD_DEBUG=files` shows exactly three camlibs opened, all under the path I set:
  `camlibs.so`, `pentax.so`, `ptp2.so`. Nothing was loaded from elsewhere.
- `LD_DEBUG=libs` shows `calling init: /app/lib/libgphoto2.so.6`. `/app/lib/libgphoto2.so.6` and
  `/app/lib/stage2/libgphoto2.so.6` are the same artifact (199356 bytes, same mtime), so this is
  our library either way.

The Pentax entries include `Pentax K-3 Mark III (MTP mode)`, `Pentax K-3 Mark III Monochrome
(PTP Mode)`, `Pentax K-1 Mark II (MSC mode, USB id 0182)` and `Pentax K-1 Mark II (PTP mode)`.

## What this rules out

Everything I had previously suspected about the shipped artifacts is now disproven by direct
execution rather than inspection:

| Hypothesis | Status |
|---|---|
| camlib missing / not packaged | refuted — opened and enumerated |
| `DT_NEEDED` unsatisfiable, silent `lt_dlopenext` failure | refuted |
| version-node mismatch on `gp_log@LIBGPHOTO2_5_0` | refuted |
| `camlibs.manifest` overwritten and suppressing enumeration | refuted (libgphoto2 never reads it) |
| `CAMLIBDIR_PREFIX_ENV` filter skipping every camlib | refuted |
| directory perms (`drwxr-x--- 1000:1000`) blocking the load | refuted |
| wrong libgphoto2 loaded (Benro's instead of ours) | refuted — same artifact |
| USB layer cannot claim the device | refuted — `usb:001,004` |

## What remains

The defect is specific to pgphoto. In the running process (`PID 10026`,
`/app/lib/stage2/pgphoto.stage2ondisk`) `libgphoto2.so.6` and `libltdl.so.7` are mapped, but no
camlib and no port driver ever appear in `/proc/PID/maps`, even after a client connects and is
answered with HTTP 200. Its env already carries the same `CAMLIBS`/`IOLIBS` values that work above,
and it runs as root, so the environment is not the difference.

So pgphoto is not reaching `gp_abilities_list_load_dir`. The remaining question is *where it stops*
— never called, refused by our capture guard, or failing earlier — which is exactly what
`STAGE2_TRACE_INIT_ENTRY` distinguishes. That trace is now on the branch, ARM-compiled clean and
behaviour-tested; running it needs a rebuilt loader installed to `/app/lib/stage2/`, which I have
not done unattended.

## Safety notes

`--list-cameras` opens no device: `gp_abilities_list_load` enumerates via `lt_dlforeachfile`.
`--auto-detect` does open the device briefly, so before running it I confirmed via `fuser` that no
process held `/dev/bus/usb/*/*` — pgphoto was not claiming it. The camera returned to the same
state afterwards and pgphoto is unaffected.
