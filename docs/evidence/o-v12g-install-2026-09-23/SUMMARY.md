# o-v12g installation evidence — 2026-09-23

- Identity: `polaris_d13e86`, BSSID `48:e7:da:d4:b5:73`, route via `wlp8s0`.
- Previous firmware: `6.0.0.54.16-o-v12f-shutterfix`.
- SD target was empty before staging.
- ZIP MD5 `459a29aff9e58f90c903ac6e3bac98c7` and SHA-256
  `8ae8c884aaff7dbdf5df604e8fa04877ac2b7d460bbb06c3f905a950031a2a74`
  matched the registry.
- The complete extracted `FwPkt/` tree was tar-streamed to `/app/sd`.
- All six on-card sizes and MD5s matched `firmwareInfo`; appfs MD5 was
  `661bf2810be6d0ac23946e1b56d5689c`.
- `/sbin/reboot` produced a positive SSH drop and uptime reset.
- Installed FwVer: `6.0.0.54.17-o-v12g-recoverydiag`.
- Installed provenance: libgphoto2 `252b98d5740480206756c3f1cd39f2302c0b312a`,
  patcher `769b54b0c0a5ce5c5f1f925c9f7358450fd23746`, clean inputs.
- Stage-2 and stock core hashes both `5973e8c8999b1f4f01be70a9cafdb7ba`;
  port hashes both `ad50e83594397aef48b63ed2375890cc`.
- `/proc/250/maps` proved the running daemon loaded Stage-2 core, port and
  `libpolaris_stage2.so`; CAMLIBS/IOLIBS/LD paths matched the packaged stack.
- polestar_app and pgphoto remained at PIDs 249/250 across a 10-second check;
  listeners 22, 80, 8080 and 9090 were present.
- No `No iolibs found`, unresolved-symbol, early-call fatal, or init `-2`
  signature appeared in current logs.
- The camera was off and absent from USB, so shutter/preview/config and the
  recovery-probe trace are **NOT TESTED** in this installation step.
