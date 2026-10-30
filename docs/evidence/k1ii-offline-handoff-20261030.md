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
both routes. This audit does not establish that a particular Android red-slider
action sends `state=0` in the observed session; the app/polestar transport and
concurrency still need a matching trace. No Bulb behavior was patched in this
follow-up. The unconditional release block stays in place.

Reproduce (read-only):

```sh
python3 tools/audit_v90_bulb_cancel_static.py \
  /home/ian/polaris-build-73/out/o-v18m-k1ii-pgphoto-readiness-20261029/stage2-ondisk/ondisk/pgphoto.stage2ondisk
```

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

No user action is required until hardware testing is explicitly resumed.
