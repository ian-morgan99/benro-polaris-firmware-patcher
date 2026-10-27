# Rollback path for the `.75` install

`.74` is **operator-confirmed working** ("v74 was working really well"), so `.75`
is a regression risk, not just an improvement: its fail-closed shutter write can
refuse a capture `.74` would have taken, and its model gate can withhold a list
`.74` would have synthesised.

If `.75` regresses anything, roll back by re-flashing `.74`:

```bash
cd /home/ian/polaris-build-73
./scripts/release/release-fwpkt.sh out/o-v18d-shutter-list-always-populated
```

`.74` artifact on disk: `out/o-v18d-shutter-list-always-populated/FwPkt.zip`,
md5 `307d8bd4ca4264973a16df0d0586de48` (matches the registry row). The on-boot
watcher compares the whole appfs, so re-flashing the older tree is a complete
restore, not a partial patch.

Do not attempt to hand-edit `/app/lib/ptp2/ptp2.so` to revert just the two
changes -- the skill prohibits direct NAND edits and records that doing so bricked
the device once.
