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
