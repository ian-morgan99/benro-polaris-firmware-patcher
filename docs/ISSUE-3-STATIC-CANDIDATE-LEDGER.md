# Issue #3 static candidate ledger

`tools/polestar_rate_candidate.py` is a read-only, fail-closed ledger for the
unqualified per-axis rate-control lead. It verifies the exact `.73` application
and matching `polaris413_2.0.0.22.bin` hashes, the reviewed ARM ELF/load
segment, the full `513..549` dispatcher table, and the `SP_GimbalSetAxsi`
`AC 4A` frame constructor. It reports the six default dispatcher slots and the
reviewed executable zero-filled area, but it never modifies a binary and never
sends a frame.

Example against the previously extracted exact payload:

```sh
python3 tools/polestar_rate_candidate.py \
  --app /path/to/appfs/958962934/ubifs/bin/polestar_app \
  --gimbal /path/to/FwPkt/gimbal/polaris413_2.0.0.22.bin \
  --command-id 515 \
  --out out/polestar-rate-candidate.json
```

The command ID is an inspection selector only. `515`, `516`, `518`, `523`,
`527` and `528` are still default paths, not approved extension points. The
available 352-byte executable zero area is evidence for future investigation,
not permission to inject code. No reply contract, MCU receiver semantics, rate
units/sign, stop/hold behaviour, watchdog, or physical motor qualification is
closed by this ledger.

This preserves the K-3 III boundary: no capture path, defaults, firmware
package, or runtime command surface is changed. Issue #240 remains open until
the evidence gates in [`ISSUE-3-INDEPENDENT-AXIS-RATE-CONTROL-SPEC.md`](ISSUE-3-INDEPENDENT-AXIS-RATE-CONTROL-SPEC.md)
are completed.

## Offset and register audit

The following values belong to different namespaces and must not be conflated:

| Namespace | Value | Meaning | Status |
|---|---:|---|---|
| `polestar_app` virtual address | `0x000636e8` | `SP_GimbalSetAxsi` helper in the reviewed `.73`/`.70`-identical application | verified only for the pinned application hash |
| `polestar_app` virtual address | `0x0005f524` | `GimbalUartTxMsg` helper used by the frame constructor | verified only for the pinned application hash |
| MCU virtual address | `0x0800501c` | historical `J`/`0x4A` handler | verified only for the pinned `polaris413_2.0.0.22.bin` hash |
| MCU file offset | `0x0000501c` | same handler relative to image base `0x08000000` | static fact, not a patch location |
| MCU file offsets | `0x5180`, `0x5184`, `0x5188` | conversion scale, divisor, and comparison literals | exact words are hash/fingerprint checked |
| per-axis state offset | `0x0e` | input float field | structure offset, not a hardware register |
| per-axis state offset | `0x21c` | axis-scale field read by the handler | structure offset, units unproven |
| per-axis state offsets | `0x25c`, `0x264` | output state flag and output-step fields | structure offsets, semantics unproven |

The exact MCU image has a `0x64`-byte per-axis record stride and the static
conversion literals are `0.0002770000137f`, `1000.0f`, and `-10000.0f`. These
facts do **not** establish degrees/second units, timer cadence, axis sign,
zero-rate hold behaviour, acknowledgement, watchdog semantics, or a safe
application command ID. The `AC 4A` frame remains analysis-only.
