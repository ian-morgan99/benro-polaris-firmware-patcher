# #362 companion delivery: measured on a PC, and the recorded reason is wrong

**Date:** 2026-11-28
**Host:** this workstation (x86_64), **not** the Polaris head
**Camera:** Pentax K-1 Mark II, `25fb:0183`, `usb:001,010`, JPG+RAW
**Library:** our patched libgphoto2 2.5.34 @ `089ae66c74f02f8b0305ffd5847ef18f56d880c4` — the exact
pin shipped in `astro-v121-companion-reporting-complete-kit-20261128`, built for the host arch from
`_build_rc` (same source SHA as v121's ARM build)

This corrects a claim I wrote into `docs/CURRENT-STATE.md` and the `.120`/`.121` rows of
`docs/FWPKT-PROVENANCE-CONTRACT.md`. It was true when written, and it is now false.

## What was recorded, and what is actually true

Recorded: *"The loader cannot download the companion because it cannot know pgphoto's destination
directory, so #362 stays open until either pgphoto calls `gp_camera_get_extra_capture_files` itself or
a consumer that knows the target path is added."*

Measured:

| Claim | Measured | Verdict |
|---|---|---|
| The API never returns companions; v121's reporting is dead code | `gp_camera_get_extra_capture_files` returns `ret=No error count=1`, naming `K1II8841.DNG` | **False** — the reporting path in v121 is live and will fire on a real dual-format capture |
| The companion is only a name; nothing has the bytes | The camlib downloads it during `gp_camera_capture()`: `published extra capture file //K1II8838.DNG (38393372 bytes)`, then `reconciled extra candidate 1` | **False** — 38 MB of real DNG is transferred and retained in-process |
| Delivery is blocked on pgphoto knowing the destination | `gp_camera_file_get(cam, "/", "K1II8841.DNG", NORMAL)` fails with `GP_ERROR_CAMERA_BUSY` on **6 consecutive attempts over ~12 s**, while the **primary** in the same session downloads and saves cleanly | **Partly false** — the blocker is not destination knowledge. A consumer that knows a destination still cannot fetch the bytes today. |

So #362 stays open, but for a different reason than recorded. The gap is not "nobody asks" — it is that
the retained companion is not served back through the file API.

## Why the primary works and the companion does not

`gp_camera_file_get()` → `gp_filesystem_get_file()` → ptp2's `camera_get_file_cb`
(`camlibs/ptp2/library.c:10975`). That callback first consults the retention ledger:

```c
publication = pentax_capture_publication_find_for_type (params, folder, filename, type);
if (publication) { ...; return gp_file_copy (file, publication); }
```

The primary hits this and is served from RAM. The companion misses it and falls through to a real PTP
object fetch, which the K-1 II answers with `PTP_RC_DeviceBusy` → `GP_ERROR_CAMERA_BUSY`
(`library.c:95`). Note the human-readable string for that code is **"I/O in progress"**
(`gphoto2-result.c:42`), which reads as transient but is not here — it was stable across every retry.

The lookup is an exact `strcmp` on both folder and name (`pentax-publication.c:52-60`). Both the
primary and the companion are reported with folder `/`, so a plain path mismatch does not obviously
explain the miss; the ledger entry for the companion appears not to survive to read time. Pinning down
which of `pentax_capture_publications_clear` / `_remove` / the generation bump at `library.c:7211`
drops it is the next step, and I have **not** done that. Do not plan a fix from this document alone.

## What this changes for #362

- **v121's reporting fix is confirmed useful**, not dead code. On a real JPG+RAW capture it will print
  `extra-capture count=1 ...` and name the DNG. That closes the silence, which was the point.
- **The loader cannot deliver today**, but not for the reason recorded. It is not only a destination
  problem: even with a destination, `gp_camera_file_get` returns `CAMERA_BUSY` for the companion while
  the primary in the same session downloads fine.
- **A fix inside libgphoto2 looks plausible and is unproven.** If the companion's ledger entry survived
  to read time, `camera_get_file_cb` would serve it from RAM exactly as it serves the primary — no
  pgphoto change, no destination problem, because the bytes are already in memory. That is a much
  smaller change than "patch pgphoto to call the API and pick a directory". It has **not** been
  attempted or tested.
- **PC results do not qualify the Polaris route.** The head has no SCSI generic layer (see
  `docs/evidence/k01-polaris-scsi-absent-20261128/`), pgphoto is a different binary, and the capture
  path there runs under the Stage-2 loader. Nothing here proves device behaviour.

## Reproduce

```sh
# Host-arch build of the exact v121 pin (already present, no rebuild needed):
SRC=/home/ian/Documents/VSCodeProjects/LibGphoto2/libgphoto2/_build_rc
mkdir -p /tmp/gp-patched/camlibs/2.5.34 /tmp/gp-patched/iolibs/0.12.2
cp $SRC/libgphoto2/libgphoto2.so.6.4.0 /tmp/gp-patched/
ln -sf libgphoto2.so.6.4.0 /tmp/gp-patched/libgphoto2.so.6
ln -sf libgphoto2.so.6.4.0 /tmp/gp-patched/libgphoto2.so
cp $SRC/camlibs/ptp2/ptp2.so $SRC/camlibs/pentax/pentax.so /tmp/gp-patched/camlibs/2.5.34/
cp $SRC/libgphoto2_port/libgphoto2_port/libgphoto2_port.so.12.2.0 /tmp/gp-patched/iolibs/0.12.2/
ln -sf libgphoto2_port.so.12.2.0 /tmp/gp-patched/iolibs/0.12.2/libgphoto2_port.so.12
cp $SRC/libgphoto2_port/libusb1/usb1.so $SRC/libgphoto2_port/serial/serial.so \
   $SRC/libgphoto2_port/disk/disk.so /tmp/gp-patched/iolibs/0.12.2/

export LD_LIBRARY_PATH=/tmp/gp-patched:/tmp/gp-patched/iolibs/0.12.2
export CAMLIBS=/tmp/gp-patched/camlibs/2.5.34 IOLIBS=/tmp/gp-patched/iolibs/0.12.2

# CAMLIBS must point AT the version dir, not its parent, or gphoto2 silently
# falls back to the system 2.5.31 tree and reports no camera at all.
gphoto2 --auto-detect          # Pentax K-1 Mark II (PTP mode)  usb:001,010
```

The probe source is `extra_test.c` / `dl_test.c` in `/tmp/k1ii-shot/` (transient). It must set the port
via `gp_port_info_list_lookup_path` + `gp_camera_set_port_info`; `gp_camera_set_abilities` alone yields
`init: Unknown port`.

## Four shutters were fired on the user's K-1 II

Captures `K1II8838`, `K1II8839`, `K1II8840`, `K1II8841` (JPG + DNG each) are now on the camera card.
They were **not deleted** — removing a user's photographs is not mine to do. The DNGs are ~38 MB each.

`gvfs-gphoto2-volume-monitor` holds the PTP session and logs
`Pentax session already open from a previous connection; observing camera state`. It was left running;
the control test above shows it does not block primary downloads, so it is not the cause of the
companion failure.
