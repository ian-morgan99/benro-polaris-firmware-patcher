
## 2026-09-07T16:37:32Z — Stock FwPkt.zip staged on SD card (recovery attempt)

**Reason.** Polaris wedged. /app/bin/pgphoto missing from NAND or
loader-race. Clog_000062 shows [stage2] FATAL early call to gp_port_new
at slot=0x300000f0 before fill, then pgphoto respawn loop.

**Action.** Remounted SD read-write on this PC, copied
firmware/FwPkt.zip (stock, MD5 90bdad511f556f25a2904ae9d2980102, 65.3 MB) to /FwPkt.zip at
card root. MD5 verified on card. Sync done. Unmounted cleanly.

**Next.** User pulls card from PC, reseats in gimbal, power-cycles
(button off, 30s wait, button on). On-boot watcher reads
/FwPkt.zip, sees MD5 mismatch vs NAND, hands off to U-Boot for
NAND reflash to stock.

**Logs.** Full SD card log dump (80 files, 46 MB) staged at
docs/evidence/fwpkt-install/on-card-logs-2026-09-07/.
Archive: /home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/docs/evidence/fwpkt-install/sd-card-logs-2026-09-07_20260907T163607Z.tar.gz

## 2026-09-07T16:38:10Z — Re-staged: pre-extracted FwPkt/ on SD card (canonical flow)

**Correction.** First staging put /FwPkt.zip on the card. Per
docs/evidence/fwpkt-install/ROOT-CAUSE-2026-09-01.md and the
2026-09-06 Benro download page revision, the on-boot watcher
ignores the zip and reads /FwPkt/{gimbal,camera}/. Re-staged as a
pre-extracted tree.

**Action.** Remounted SD read-write, removed /FwPkt.zip,
created /FwPkt/, extracted firmware/FwPkt.zip into it. Sync done.
Unmounted cleanly.

**On-card layout:**
```
/FwPkt/camera/appfs.ubifs   (MD5 )
/FwPkt/camera/...
/FwPkt/gimbal/...
```

**Next.** User pulls card, inserts in gimbal slot, clean power-cycle.
On-boot watcher reads /FwPkt/camera/appfs.ubifs, MD5-compares vs
NAND, finds mismatch, hands off to U-Boot for NAND reflash.

## 2026-09-07T16:38:51Z — Correct staging: FwPkt/ tree at SD root (canonical Benro layout)

**Correction.** Previous staging attempts were wrong in two ways:
1. Dropping FwPkt.zip alone (watcher ignores zips — needs the
   extracted tree).
2. Extracting into a subdir /FwPkt/ — gave /FwPkt/FwPkt/{...}, a
   doubled prefix that the on-boot scanner (which reads
   /app/sd/FwPkt/{camera,gimbal}) won't find.

**Correct layout per docs/evidence/fwpkt-install/ROOT-CAUSE-2026-09-01.md
and Benro download page (2026-09-06 revision):**
```
SD card root
└── FwPkt/                       ← the folder that was inside the zip
    ├── firmwareInfo             ← per-file MD5 manifest (NOT zip-level)
    ├── camera/
    │   ├── appfs.ubifs
    │   ├── config
    │   ├── rootfs.ubifs
    │   └── uImage
    └── gimbal/
        ├── polaris403_<ver>.bin
        └── polaris413_<ver>.bin
```

**Action.** Remounted SD rw, removed nested /FwPkt/FwPkt, extracted
firmware/FwPkt.zip to card root. Verified:
- appfs.ubifs MD5: 47f2ae680be3a5f5d69aa20e20a2397b (matches original)
- firmwareInfo's appfs MD5 line: 47f2ae68... (matches actual)
- All per-file sizes in firmwareInfo match actual sizes
- Sync done, unmounted cleanly

**Next.** User pulls card, reseats in gimbal, clean power-cycle
(button off 30s on). On-boot SP_EVENT_SD_SCAN walks
/app/sd/FwPkt/{gimbal,camera}, runs SP_UpgradeCheckFw (per-file MD5
in firmwareInfo), sees mismatch vs NAND, hands off to U-Boot for
NAND reflash to stock.

**Logs of the wedged boot.** docs/evidence/fwpkt-install/on-card-logs-2026-09-07/
Archive: /home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/docs/evidence/fwpkt-install/sd-card-logs-2026-09-07_20260907T163607Z.tar.gz (2.4 MB, 81 entries)
