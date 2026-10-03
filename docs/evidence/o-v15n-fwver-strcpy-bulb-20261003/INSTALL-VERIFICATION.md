# o-v15n installation verification

Date: 2026-10-03

## Staging and reboot

- Device identity verified through the `polaris_d13e86` AP, BSSID
  `48:E7:DA:D4:B5:73`, and route via `wlp8s0`.
- The SD card was empty before staging.
- The complete extracted `FwPkt/` tree was streamed to `/app/sd/FwPkt/`.
- Every shipped camera/gimbal MD5 matched the local candidate before reboot.
- Reboot used the sanctioned `/sbin/reboot` path.

## Post-boot identity

The device reported:

```text
FwVer:6.0.0.54.52;date:2026.10.03;
git_commit=e0e5135023165b9a4411bba637076b8ca1e63ed1
patcher_commit=8e96decce989af694c24313ae39c55088d85ac1e
build_id=6.0.0.54.52-o-v15n-fwver-strcpy-bulb
display_fwver=6.0.0.54.52
```

The post-reboot code-780 canary returned:

```text
780@hw:1.1.1.2;sw:6.0.0.54.52;exAxis:1.0.2.14;sv:1;ov: ;#
```

`polestar_app`, Stage-2, and ports 80/8080/9090 were alive after the query.

## Qualification boundary

The camera was absent from USB (`manufacturer:none;model:none;state:-5`), so
no Manual or Bulb capture was attempted and no physical Bulb qualification is
claimed. The installed candidate is runtime-verified and ready for the K-3
III test matrix when the camera is attached.
