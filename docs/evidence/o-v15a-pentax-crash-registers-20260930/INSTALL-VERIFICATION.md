# o-v15a install verification

Date: 2026-09-30. Device wall clock is about one hour ahead of host UTC.

## Before install

- Confirmed Polaris SSID/BSSID: `polaris_d13e86`, `48:E7:DA:D4:B5:73`.
- Route: `192.168.0.1 dev wlp8s0 src 192.168.0.4`.
- Installed firmware: `6.0.0.54.43` / build `6.0.0.54.43-o-v13x-camlib-prep-20260930`.
- SD `/app/sd/FwPkt` did not exist before staging.
- Registered candidate ZIP MD5: `64ccd4a4173d0d3364b4380ee73f4002`.
- Registered candidate ZIP SHA-256:
  `77c80c1fcc9a09d3e4018679e78179c951828a1c948b18a67d517de8938c5280`.
- Manifest appfs MD5: `d9874445c9355eb173cf2d31eae8ef19`.

The complete extracted `FwPkt/` tree was streamed to the SD mount, not copied
into NAND. Before reboot, each on-card payload was checked against
`firmwareInfo`:

| Payload | Bytes | MD5 | Result |
|---|---:|---|---|
| `camera/config` | 326 | `1905e2d041be62b679f7dc6c64ab9d3a` | PASS |
| `camera/uImage` | 4,188,435 | `5f6a0c1861a254371c4a956b57f26685` | PASS |
| `camera/rootfs.ubifs` | 21,102,592 | `778b27bcade9ddc6ea4a7cb45254c551` | PASS |
| `camera/appfs.ubifs` | 64,356,352 | `d9874445c9355eb173cf2d31eae8ef19` | PASS |
| `gimbal/polaris403_2.0.0.22.bin` | 84,328 | `4facafa7d29c1e6c2a125b8309c9b901` | PASS |
| `gimbal/polaris413_2.0.0.22.bin` | 84,284 | `c0299d06a15f5c2fbecb9a6db76a29c5` | PASS |

After all six passed, the 9090 keepalive was stopped and `/sbin/reboot` was
issued. The same Polaris AP and Wi-Fi route returned.

## After reboot

```
FwVer:6.0.0.54.44;date:2026.09.30;
source_kind=git-directory
actual_version=2.5.34
git_commit=fbc2e7e6544efc93cc708a1e7d2fdf2b2bf7c7cd
patcher_commit=9a2c1396f4a77b85b0f8e8f3f2ce16f3238e0980
build_id=6.0.0.54.44-o-v15a-pentax-crash-registers-20260930
display_fwver=6.0.0.54.44
```

Processes `polestar_app` and `/app/lib/stage2/pgphoto.stage2ondisk` were alive.
Runtime environment:

```
LD_LIBRARY_PATH=/app/lib/stage2:/app/lib
IOLIBS=/app/lib/stage2/libgphoto2_port/0.12.2
CAMLIBS=/app/lib/stage2/libgphoto2/2.5.34
LD_PRELOAD=/app/lib/stage2/libpolaris_stage2.so
```

Matched runtime copies:

| Component | Stage-2 MD5 | Stock-path MD5 | Result |
|---|---|---|---|
| core `libgphoto2.so.6` | `4ef64d8950eee70d9200093286fb0f3b` | `4ef64d8950eee70d9200093286fb0f3b` | PASS |
| port `libgphoto2_port.so.12` | `ad50e83594397aef48b63ed2375890cc` | `ad50e83594397aef48b63ed2375890cc` | PASS |
| `ptp2.so` | `7d630332dc2880155b78c0559cef9f8c` | `7d630332dc2880155b78c0559cef9f8c` | PASS |
| `usb1.so` | `4423bba29bf8c5d899598841ec3e6310` | `4423bba29bf8c5d899598841ec3e6310` | PASS |

Runtime `libpolaris_stage2.so` contains `[stage2]   arm lr=` and
`[stage2] process maps begin`. The camera enumerated as `25fb:0189`. TCP
listeners 8080 and 9090 were present. The read-only probe reported:

```
RX 286@manufacturer:ricoh imaging company, ltd.;model:pentax k-3 mark iii;state:1;storage:2;photoFormat:2;
SUMMARY model=pentax k-3 mark iii state=1 photoFormat=2
PROBE-DONE
```

This was probe-only; no `--shot` request or physical shutter test was run. The
reboot log includes a USB bus reset and then the camera enumerated; no claim is
made about subsequent capture stability. Mlog reported that the SD card had
not been properly unmounted before reboot. All on-card payload hashes had
passed before reboot.
