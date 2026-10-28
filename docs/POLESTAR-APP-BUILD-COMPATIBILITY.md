# Polestar application compatibility record

Status: read-only provenance and static-analysis record. It is not a build
recipe for a firmware patch and does not authorise flashing.

## Reviewed payload

The current record is for:

```text
package: firmware-packets/6.0.0.54.73--o-v18c-bulb-duration-measured-hold/FwPkt.zip
FwVer:   6.0.0.54.73;date:2026.10.26;
polestar_app SHA-256: a5e58ffd76670cf9bdc76560a859d2e037ca4320d37bb3c2d93d482cf459ac02
polaris403 SHA-256:  35f8d0646339715e5e5e5d6ec01743f411d16325bc0b36fd58b590584fedf0b9
polaris413 SHA-256:  34d3f4186185c541adb9c8e57b3e2ec13e402dfb4bb3e9b2262cbf03f1a5c112
```

The `.73` `polestar_app` is byte-identical to the recorded `.70` app payload.
The two listed gimbal payloads are also byte-identical to their `.70` records.
These identities make the static observations reproducible for this payload
family; they do not establish compatibility with another firmware family.
The `polaris413` hash is the `polaris413_2.0.0.22.bin` image used by the
historical MCU `J`/`0x4A` analysis at handler address `0x800501c`.

## Static observations

- `SP_GimbalSetAxsi` is present at `0x000636e8`, size 144 bytes.
- `GimbalUartTxMsg` is present at `0x0005f524`, size 1288 bytes.
- The helper constructs `AC 4A`, axis, a little-endian IEEE-754 float, length
  seven and queues the message.
- No direct call to the helper was found in the full disassembly search.
- The MCU-side research for the matching `polaris413_2.0.0.22.bin` reports the
  existing `J` handler and an approximate per-tick step relationship; the
  rate-unit conversion and hold semantics still require target qualification.
- `SP_MsgGimbalCmdFromAppProc` dispatches the existing fast-jog controls: 513
  maps to axis 2, 514 to axis 1 and 521 to axis 3. The helper
  `SP_GimbalUartAdjSpeed` emits `AC 41`, axis, signed little-endian int16 speed,
  length five.
- Its 513--549 jump table currently falls through the default path at 515,
  516, 518, 523, 527 and 528. These are investigation candidates only; no new
  command ID is approved.

The last two bullets describe an existing jog path, not independent tracking
rate control. The app source and the receiving MCU source are not available in
this checkout, so no source rebuild or binary patch can be claimed.

## Compatibility decision

| Question | Decision |
|---|---|
| Can the current native Astro solver safely send `AC 4A`? | No; the MCU lead is stronger, but app exposure, reply, units and physical semantics remain unproven. |
| Can the existing jog path be treated as tracking-rate control? | No; it is a leased fast-jog/deadman path. |
| Can issue #240 be called resolved from static analysis? | No; physical and MCU contract gates remain open. |
| Does this work change K-3 III capture code or defaults? | No. |

The host-only parser and safety model in `tools/polaris_rate_protocol.py` are
useful preparation only. They open no socket, are not in the Polaris runtime
bundle, and must remain so until the evidence gates in
`ISSUE-3-INDEPENDENT-AXIS-RATE-CONTROL-SPEC.md` are completed.
