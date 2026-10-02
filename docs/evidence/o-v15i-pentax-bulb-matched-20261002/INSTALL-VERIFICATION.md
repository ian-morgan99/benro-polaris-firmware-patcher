# Install verification

Date: 2026-10-02

## Device identity

- Polaris AP BSSID: `48:E7:DA:D4:B5:73`
- Route: `192.168.0.1 dev wlp8s0`
- Pre-install firmware: `6.0.0.54.51-o-v15h-adversarial-bulb`
- Post-install firmware: `FwVer:6.0.0.54.52;date:2026.10.02;`
- Embedded `git_commit`: `6979070597ebddbaa5f1cff1e56b7597e4594ed2`
- Embedded `build_id`: `6.0.0.54.52-o-v15i-pentax-bulb-matched`

## SD staging and updater

The complete extracted `FwPkt/` tree was streamed to `/app/sd/FwPkt/`.
The target directory was empty before staging. All six payload MD5 values
matched `firmwareInfo` before reboot. The device was rebooted with:

```text
sync; /sbin/reboot
```

The device returned after the firmware update and reported the expected
display version.

## Runtime proof

The following matched component SHA-256 values were equal between the build
output and the installed device:

| Component | SHA-256 |
|---|---|
| `pgphoto.stage2ondisk` | `00d8e9e80e2813ddf2c89d28f219de33a09b1fde17dd20f7f2590793fb6df81d` |
| `libpolaris_stage2.so` | `534377d19b1c20325cbf156e27f0c525cdc35df49633caeec17342c7378162af` |
| `libgphoto2.so.6` | `a51a813cb5e241cf9e5d6d8da1a2c29592a5ca98d2ffa56524f8760a763b73f9` |
| `libgphoto2_port.so.12` | `e9e979be616eebd93551e58c9ced1a99d7a247a195bf5b6a57a819358c482b67` |
| `ptp2.so` | `9f9a7930a380202978be5a3d57608268f9b36443bed88e204b63ffd0d42771e8` |
| `usb1.so` | `4d4bfe4863508dd33aeb1276c5eb1c887845aa7fdf1644299853a760a097dd0e` |

The Stage-2 loader reported `dlopen core ok`, `dlopen port ok`, and
`resolved 64/64`. Both Stage-2 and stock-path core hashes matched, as did
both port hashes. One `pgphoto.stage2ondisk` process and the expected 8080
and 9090 listeners were present after reboot.

## Qualification boundary

The K-3 III/K-1 II was absent from USB after reboot. Physical M-mode display,
ordinary capture, RAW+JPEG capture, and Bulb capture are therefore **NOT
TESTED** on o-v15i. The package is installed and runtime-proven, but not yet
physically qualified.
