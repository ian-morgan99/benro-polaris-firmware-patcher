# o-v15h installation verification — 2026-10-02

## Pre-install identity and provenance

- Polaris AP: `polaris_d13e86`, BSSID `48:E7:DA:D4:B5:73`
- Route: `192.168.0.1 dev wlp8s0 src 192.168.0.4`
- Previous runtime: `6.0.0.54.50-o-v15g-bulb-duration`
- `/app/sd/FwPkt` was absent before staging.
- The exact registered ZIP was re-hashed immediately before staging:
  - MD5 `fef08d6c994d4296e7f4441ff3528c40`
  - SHA-256 `0515048034ebef079322eb46528bdefdc8b6b5403cc2737cecfbf9a271ec14d7`
- The ZIP manifest reported appfs MD5 `e7dfc61e03dfbc9b1f9df9af4001122a`.

## Staging and reboot

The complete extracted `FwPkt/` directory was streamed to `/app/sd/` using
the documented tar-stream flow. The on-device files were checked before reboot:

| file | bytes | MD5 |
|---|---:|---|
| `camera/config` | 326 | `1905e2d041be62b679f7dc6c64ab9d3a` |
| `camera/uImage` | 4188435 | `5f6a0c1861a254371c4a956b57f26685` |
| `camera/rootfs.ubifs` | 21102592 | `778b27bcade9ddc6ea4a7cb45254c551` |
| `camera/appfs.ubifs` | 64356352 | `e7dfc61e03dfbc9b1f9df9af4001122a` |
| `gimbal/polaris403_2.0.0.22.bin` | 84328 | `4facafa7d29c1e6c2a125b8309c9b901` |
| `gimbal/polaris413_2.0.0.22.bin` | 84284 | `c0299d06a15f5c2fbecb9a6db76a29c5` |

The device was rebooted with `/sbin/reboot`, and the Polaris AP returned.

## Post-boot runtime proof

- `/app/FwVer`: `6.0.0.54.51-o-v15h-adversarial-bulb`
- Embedded libgphoto2 SHA: `4e996e69c0a832a59d0852f8c872510d1b5ce361`
- Embedded patcher SHA: `96604e38d2dc86b92f1744b6541d8252f5f4a4c9`
- Embedded build id: `6.0.0.54.51-o-v15h-adversarial-bulb`
- `polestar_app` and `pgphoto.stage2ondisk` were running.
- Stage-2 core and stock core both had MD5
  `4ef64d8950eee70d9200093286fb0f3b`.
- Stage-2 port and stock port both had MD5
  `ad50e83594397aef48b63ed2375890cc`.
- Stage-2 `ptp2.so` and stock-path `ptp2.so` both had MD5
  `73fc905b84a1148ed8848876966ae23d`.
- Stage-2 `usb1.so` and stock-path `usb1.so` both had MD5
  `4423bba29bf8c5d899598841ec3e6310`.
- `/proc/250/maps` showed pgphoto loading the Stage-2 core, port and loader.

## Live qualification boundary

No Pentax USB device was present after reboot (`lsusb` showed no `25fb` device).
The live gate therefore recorded a prerequisite skip and issued no shutter:

```
2 passed, 0 failed, 1 skipped
SKIP: live device gates (probe failed or camera state!=1 — gimbal off / camera not attached)
```

The device install and runtime provenance are verified. Bulb, RAW+JPEG, and
K-1 II physical behavior remain untested on this candidate.
