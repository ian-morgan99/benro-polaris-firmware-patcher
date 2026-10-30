# K-1 II offline follow-up and hardware test entry points

All work is on `fix/k1ii-control-latency`, based on v90 patcher
`f344e41261a886f8f6107b9467095bc90b3835a1`. Commit `efeaa08` completes bounded
timing and listener ownership. No source has been merged to main, no firmware
has been built or installed, and no camera operation was performed here.

## Diagnostic collector

`container/stage2_config_receiver.c` is a separate Linux process with no
libgphoto2 or camera API dependency. The packaging source now cross-compiles it
with the loader's toolchain, checks soft-float ABI, installs it into the staged
appfs at `/app/lib/stage2/stage2-config-receiver`, and checks identical bytes
after repacking. When present, the candidate install manifest records its
hash. Historical candidates without the utility remain supported. These are
source changes; firmware packaging has not been executed. Host and ARM compile
tests do not prove linkage against the actual Polaris userspace.

Nothing starts the collector or enables timing automatically. The loader
requires both `STAGE2_CONFIG_TIMING=1` and a valid `STAGE2_CONFIG_TIMING_PORT`
at process start. It sends to IPv4 localhost only, at most 128 attempts per
process lifetime. That budget includes startup reads and failed sends; do not
assume the budget remains for a later settings write. Do not add polling,
repeat writes or automatically restart the daemon to obtain more samples.

The collector accepts `--port`, `--output`, optional `--pid`, `--seconds`
(default 30, maximum 120) and `--max-records` (default/maximum 128). It binds
`127.0.0.1` only, validates the record syntax and bounds, rejects oversized or
embedded-NUL datagrams, and can filter by the verified pgphoto PID. It stops
collecting at its deadline, record count or 512 received datagrams, including
invalid traffic. The retained records occupy at most 32 KiB. A new output file
is created with mode 0600; existing files and symlinks are refused. File writes
occur after collection in this separate process. The collection deadline does
not guarantee a deadline for filesystem writes. No fsync/durability claim is
made; copy and hash the resulting evidence after collection.

Exit codes: 0 = collected records at deadline/record limit; 1 = operational
error; 2 = invalid arguments; 3 = deadline with no records; 4 = datagram limit;
130 = interrupted collection, retaining already received records when output
succeeds. Partial logs are evidence, not successful camera tests. Sequence
gaps can mean dropped diagnostics. Core return codes precede the widget guard
and do not prove settings were applied. Pair them with Clog/Mlog and readback.

The host test uses real loopback sockets, malformed/oversized input, PID
filtering, limits, interruption and overwrite refusal. It also generates
candidate-manifest fixtures with and without the receiver and verifies its
content hash. Run `sh container/test_stage2_config_receiver.sh`; this compiles
for ARM only if the cross-compiler is already available. No installation is
required by the test.

## Additional Bulb finding: two cancellation routes

The read-only audit `tools/audit_v90_bulb_cancel_static.py` accepts only the
saved v90 pgphoto SHA-256
`8973d9486e0207446cc111234ed39e878676ce1f3edca2967a97db86c8d9eaac`.
It checks actual instructions and ELF literals; it does not modify the binary
or substitute for the unavailable ARM emulator.

- `captureImage` at `0x208b0` parses the literal keys `state` and `b`.
  With its stored `bulb.11463` value positive, `state=0` takes the branch at
  `0x20adc` to `0x20b00`, clears that global, then writes zero to
  `gp_params+0x10d0` at `0x20b20`.
- `capture_image_with_Bulb` sets that same byte to one at `0x101bc8`.
  Its intended loop reads it at `0x101dec`; zero leads to the common stop
  path, separately from the `GP_ERROR_CANCEL` comparison at `0x101dd8`.
- `ctx_cancel_func` at `0xf6fd8` uses a different global, `glob_cancel`:
  it clears a pending cancellation at `0xf7014` and returns feedback 1.
- The saved v90 instruction at `0x101ddc` is unconditional `0xea00001b`,
  entering the stop path before that shared-byte test. After the stop callback,
  `0x101ee4` overwrites the saved result. These independently confirmed anchors
  agree with the earlier WIP review; they are not new physical observations.

Consequence: a complete repair must distinguish normal expiry, the message
stop flag and context cancellation. Preserving only `-52` will not cover a
message stop that reaches the common stop path with another saved value.
The earlier deferred `bulb=0` capture risk therefore needs testing against
both routes. The Android reference below establishes its stop-request format;
the actual tester APK, polestar translation and concurrent request handling
still need a matching trace. No Bulb behavior was patched in this
follow-up. The unconditional release block stays in place.

Reproduce (read-only):

```sh
python3 tools/audit_v90_bulb_cancel_static.py \
  /home/ian/polaris-build-73/out/o-v18m-k1ii-pgphoto-readiness-20261029/stage2-ondisk/ondisk/pgphoto.stage2ondisk
```

## Android reference correction

The local reference root is
`PrivateResearch/openpolaris-research/Benro-Connect/benro-connect-java/sources/com/snoppa/polaris/`.
`activity/MainActivity.java:787` starts `clickStop`; its ordinary-photo branch
at lines 795–805 calls `SP_SET_PHOTO_RECORD_STATUS` with state `"0"`, the
selected Bulb duration (or zero), and c `"0"` for continuous shooting or `"-1"`
otherwise. Other shooting modes have their own stop commands. Its SHA-256 is
`256bd8d36778091a01db8a65516086c52b544f0112245c496e901e2d08f64117`.

`singleton/PolarisOrderCommunication.java:587–596` defines that photo method
as wire code 264/type 2 with `state`, `bulb`, and `c` fields. The nearby method
`SP_GET_ISO_INFO` sends code 265/type 1 without a payload. SHA-256:
`72877f224e0eddb8fc3ba08593cbe261242e9261ad19f3ad75a5976d512a6919`.
Consequently the old release record's sentence "the Bulb stop is code 265"
was incorrect for this reference and has been corrected. This is reference
source evidence, not confirmation of the tester's currently installed APK
or of delivery through polestar to the pgphoto state flag.

## Hardware availability does not clear the release block

1. Establish the physical body, connection route and the exact installed
   firmware. Follow `.github/skills/polaris-debugging/SKILL.md` for device
   identity/wake, and retain a single camera-session owner. Begin with bounded
   read-only logs; do not start a second gphoto2 process against pgphoto's USB
   session. No Bulb/cancel or capture test on the known affected v90 path.
2. If direct-PC testing is possible, use the libgphoto2 repository's clean-SHA
   procedure and existing IT2 setting-path plan. Record loaded core/camlib
   identity and fresh-session debug output. Do not change the library based
   solely on Polaris observations.
3. For a later diagnostic firmware, first resolve the Bulb release blocker,
   complete source review and all required gates, then use the documented
   firmware ZIP release/install process. The collector must come from that
   verified package, never an SSH binary replacement. Record loader and
   receiver hashes, environment, PID and collection start/end.
4. Start with a single requested setting read and separate request-to-reply
   latency from core read/full-tree/write durations. Record mode, live-view
   state, active client and any drops/budget exhaustion. Empty EV/WB cache
   responses are Polaris evidence, not proof of absent camera support.
5. A setting write requires an original value/descriptor, one advertised
   change, source-defined condition/readback verification, exact restoration
   and an independent restoration check. Stop at the first mismatch. Preserve
   K-3 III and other-camera regression obligations; do not label a setter's
   success code or these offline tests as a physical PASS.

## Final offline gate and direct-PC preflight

Runtime source is committed locally as `efeaa08` and `df50c1c`; neither has
been merged, pushed to GitHub or deployed. The full offline gate against
`df50c1c` returned **RED**:

- Deterministic harness: **27 passed, 1 failed, 2 skipped**. The failure is
  the deliberate `test_pending_v90_bulb_safety.sh` release block. The package
  build and source-input tests lack their explicit inputs and were skipped.
- Python regressions: **393 passed, 8 skipped**. Skips concern unavailable
  archived .68 artifacts and .68/.69 manifests.
- Timing, collector, empty-widget/control guard, write-path and readiness
  ownership tests pass, including IPv4/IPv6 socket inode ownership and process
  start-time checks. The installed ARM cross-compiler also compiled the loader
  and collector. This is not an actual firmware/Polaris-userspace build.
- Aggregate gate: **8 passed, 1 failed, 1 skipped**. No candidate was supplied,
  so package/installed-runtime qualification did not run. No Unicorn emulator
  was installed; historical emulator results have not been revalidated.

Raw logs are retained beside this document in
`k1ii-host-preflight-20261030/`. No hardware claim follows from these passes.

The operator subsequently attached the K-1 II to the PC. USB enumeration
showed `25fb:0183`, bus 001/device 005, and `fuser` reported no open owner of
that USB node. **No Pentax PTP session was opened.** The direct test stopped
at source review, for the safety reason below.

The clean v90 libgphoto2 SHA `63a894b0821a510fc40244c5cc4ef84a5220a91c`
was compiled out of tree at
`/home/ian/Documents/VSCodeProjects/LibGphoto2/build-k1ii-readonly-63a894b`,
using installed Meson/Ninja tools, `--wrap-mode=nodownload`, `camlibs=ptp2`,
`iolibs=libusb1`, and `pentax_research_capture=false`. The source checkout
remained unchanged. Nothing was installed into a system prefix.

The unfiltered host test run returned **17 passed, 2 failed**:
`test-gphoto2` requires the omitted Directory Browse driver; `test-gp-port`
is explicitly in the `no-ci` suite and writes serial settings to the first
port. With this USB-only configuration it failed parameter validation before
opening a device. It must be excluded from future unattended/offline runs,
not treated as a camera test or silently reported as a pass. No settings or
capture commands reached the attached K-1 II in this run.

Compiled host artifacts (not deployed or runtime-qualified):

| Artifact | SHA-256 |
|---|---|
| `libgphoto2.so.6.4.0` | `0799f934cc7ef07e9c77f85ed091f72cc236911f89ef5c66b1b99ac82755350e` |
| `libgphoto2_port.so.12.2.0` | `b5f7e261c8c2abf80e12ae8ecfe1d27878f6336d816698f717088346ca1514c0` |
| `ptp2.so` | `3a3129041a257a1b91696e7c495f88edbd23acd0a7addd446ce6dc0a9206aad5` |

### Safety blocker: ordinary teardown sends CameraShutdown

Tracked as [libgphoto2 #138](https://github.com/ian-morgan99/libgphoto2/issues/138),
with the existing #33 recovery review retained as a separate acceptance input.

At the exact SHA above, `camlibs/ptp2/library.c:3429` calls
`ptp_pentax_camera_shutdown(params)` after successful vendor-mode disable
in `camera_exit`. `camlibs/ptp2/ptp.c:1941` implements it as a no-data
`0x9002` transaction with no parameters. It was introduced by
`8ba60c3e7c60d9bab403a19711202282f12f8a03`. It is not gated on an explicit
user shutdown request. The stale-session initializer also sends CloseSession
and a USB reset after observational reconciliation, even if that observation
has just set `recovery_required`.

IT2 2625 source evidence:

- `RemoteAssistant/MtpDevice.cs`, SHA-256
  `e8d11ed772aad3731d7eabd0c06fb0174aae859c5a1f6d241bf73b6d046de059`:
  `Model` selects 78400/extension 1 for K-1 II; `Disconnect()` at line 3628
  stops/disposes timers, sets `VendorMode=false`, and closes WPD. It does not
  call shutdown. `VendorMode` at line 923 uses `0x9001` with parameters
  `[13, model, on/off, extension, 0]`. `RequestCamShutdown()` at line 3762
  is a separate path, and `MtpPentaxCameraShutdown()` at line 4623 sends
  `0x9002` without parameters. `0x2019` rejects that shutdown request; other
  responses currently let IT2 proceed to disconnect. `IsRequestShutdown`
  is another explicit request setter, not the ordinary disconnect path.
- `RemoteAssistant/MainWindow.cs`, SHA-256
  `0710e0174877f644abd689f98cb7df6f1c1111b2300e3fc1985002f4e2b4822c`:
  `DisconnectDevice()` at line 2422 calls ordinary `Disconnect()`;
  `CamShutDwnBtn_Click()` at line 6333 explicitly calls
  `RequestCamShutdown()` before disconnecting when it succeeds.

This is a directly demonstrated **source-contract and test-safety discrepancy**,
not a measured cause of the K-1 II lag, overheating, or any physical shutdown.
No speculative opcode was sent to investigate it. The repository's prohibition
on shutdown/reset merely to diagnose another feature prevents calling the
unmodified init/read/exit path a read-only test. Do not evade cleanup, interpose
a success response, or pretend a modified library is the original SHA.

Next: separately review a narrow Pentax-only lifecycle safety fix, with mocked
no-shutdown-on-exit and no-reset-when-unsafe tests, before resuming direct-PC
timing. Preserve vendor-disable/CloseSession error reporting and previously
qualified reconnect behavior. This needs a library feature branch; the active
patcher branch and main have not been changed to conceal the blocker. No
library DEVELOPMENT_PLAN or hardware PASS entry has been added because no
direct camera test occurred.
