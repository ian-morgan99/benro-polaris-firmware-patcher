# Installation verification — o-v15j-fw-version-20261002

## Package identity

- registry id: `o-v15j-fw-version-20261002`
- ZIP MD5: `d30bd6428c1af3e1b18b46a088cf3266`
- ZIP SHA-256: `88600426531627a96c8f4c866316d420e4cf478ac4a8cc25e3d6d940965d4ac2`
- appfs MD5: `238ab41aa77d958cd7e9276d696eead1`
- PrivateResearch artifact commit: `2e95bdd0c`

## Sanctioned install

The complete extracted `FwPkt/` tree was streamed to `/app/sd/FwPkt/` over
the verified Polaris route. Before reboot, all six `firmwareInfo` payload
entries were recomputed on the device and matched the staged manifest:

```text
ON_CARD_MANIFEST=PASS
FwVer:6.0.0.54.52;date:2026.10.02;
```

The device was rebooted with:

```text
sync; /sbin/reboot
```

SSH dropped, then the Polaris AP returned. Post-boot `/app/FwVer` is:

```text
FwVer:6.0.0.54.52;date:2026.10.02;
```

## Post-boot provenance

```text
git_commit=6979070597ebddbaa5f1cff1e56b7597e4594ed2
patcher_commit=065fca497930ffc31e58c0667521a8f879568e7
build_id=o-v15j-fw-version-20261002
display_fwver=6.0.0.54.52
```

The installed provenance matches the registry row and the build inputs.

## Runtime integrity

- `polestar_app` and `pgphoto.stage2ondisk` are running.
- ports 22, 8080 and 9090 are listening.
- the loaded process maps show the Stage-2 `libgphoto2.so.6`, matched port
  library and `libpolaris_stage2.so`.
- Stage-2 and stock-path core MD5: `4ef64d8950eee70d9200093286fb0f3b`.
- Stage-2 and stock-path port MD5: `ad50e83594397aef48b63ed2375890cc`.
- installed component SHA-256 values match the candidate package, including
  `polestar_app` `c699044bfac18a7c40f9490a9e94c11004156610dc00c7ba346d442b951bd6bd`.

Read-only binary checks on the installed `/app/bin/polestar_app` report:

```text
[polestar_fwver_patch] already patched (unique SP_GetDeviceVer site at file offset 0x12fb80)
[polestar_bulb_patch] already patched (unique replacement site at file offset 0x39754)
version_literal=98779100  # decimal 0x00917798; correct standalone %s target
bulb_anchor_count=0
bulb_replacement_count=1
```

A code-780 query while no camera was attached correctly returned the no-camera
status `785@state:0;#`, so it did not produce the normal code-780 response.
The same request logged `mFwVer[6.0.0.54.52]`; the exact code-780 formatter is
verified in the installed binary. A camera-attached code-780 response and
physical capture canary remain pending.
