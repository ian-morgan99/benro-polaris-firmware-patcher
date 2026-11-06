# v96 on the BenroHardwareValidator — results and limits

Candidate: `astro-v96-cancel-writer-20261105` (`6.0.0.54.96`)
`FwPkt.zip` sha256 `999cc68c1b824870717c9778dbfd424315a1e1311b228f2c5ca52c25338c04b2`
Validator: `/home/ian/Documents/VSCodeProjects/BenroHardwareValidator/benro-polaris-test-harness`
Run 2026-11-06. Nothing was installed, flashed or uploaded.

## What ran, and what it actually proved

| Check | Command | Result | What it does NOT prove |
|---|---|---|---|
| Package integrity/provenance | `package verify` | **PASS**, exit 0, 0 errors | Updater acceptance, boot, loader selection, camera behaviour |
| SD-card deploy flow | `sd-emulate --packet … --current-version 6.0.0.54.95` | **PASS** — `outcome: updated`, `succeeded: true`, `failures: []` | That a real Polaris accepts the packet |
| Runtime ELF/ABI/resolution | `runtime verify` | **PASS**, `valid: true`, 0 issues | That the on-device loader picks these at runtime |
| Scenario schema | `validate scenarios` | 24 manifests, failures=0 | Any behaviour at all |
| Harness self-tests | `pytest tests/ -q` | 456 passed, 6 skipped, **2 failed** | — (see below) |
| Physical-execution safety gate | `safety check --target physical` | **exit 6, blocked** | — |

Checks inside `package verify`: `packet_sha256`, `zip_layout`, `zip_duplicates`,
`firmwareInfo`, `provenance`, `managed_member_hashes` (8 members), `appfs_sha256`
all PASS. `runtime_round_trip` is reported `NOT_TESTED` by design — that is the
runtime verifier's job, done separately above.

## Negative tests — the controls that make the PASSes mean something

A PASS from a tool that cannot fail is worthless, so each gate was inverted:

- **Wrong build refused.** Pointed `POLARIS_FIRMWARE_ROOT` at the v96 binary while
  the fixtures pin v90. Harness refused, exit 2:
  `has SHA-256 f167e668…, recorded 8973d948…. Seeding from a different build would
  produce results that do not describe this artifact.` This is the control that
  stops one build being measured and another reported.
- **Tampered hash refused.** Set an artifact's `sha256` to all zeros →
  `Hash mismatch`, `valid: false`, exit 5.
- **Downgrade refused.** `--current-version 6.0.0.54.97` →
  `outcome: version-rejected`, `refusing downgrade 6.0.0.54.96 < 6.0.0.54.97`, exit 3.
- **Physical execution blocked.** Exit 6, `EVIDENCE_PROVENANCE_REQUIRED` and
  `SAFETY_CONTRACT_REQUIRED`. No real hardware action is reachable from here.

## ARM emulation of the actual v96 fix — achieved

The harness refused to run v96 against the v90-pinned fixtures (see negative
tests above), so a v96-pinned fixture was authored in `/tmp` — **not committed to
the harness repo**, whose tree remains clean.

### Deriving the coordinates, not guessing them

AGENTS.md forbids guessing opcodes or addresses, so every coordinate was derived
and checked:

- `file(1)` on the v96 binary: *"ELF 32-bit LSB executable, ARM, EABI5 … with
  debug_info, **not stripped**"*. An earlier note here claimed it was stripped;
  that was a false negative caused by piping `objdump` through `2>/dev/null | wc -l`
  while the host binary path did not exist — the portal error was swallowed and
  zero output looked like zero symbols. `readelf` on the host found the symbols.
- `captureBulbImage` = `0x20604`, 684 bytes; `capture_image_with_Bulb` =
  `0x101aac`, 2176 bytes — **identical coordinates in v90 and v96**.
- Carve offset convention was established by reproducing the committed v90 region
  hashes: file offset = `vaddr − 0x10000`. Both committed regions reproduce
  exactly, so the convention is verified, not assumed.
- `.text`, `.got`, `.data`, `.bss` addresses and sizes are **identical** between
  v90 and v96, so the fixture's existing data-region seeding stays valid.

### What the patch actually changed

`captureBulbImage` is **byte-identical** between v90 and v96 (0 differing bytes),
so its stub coordinates carry over unchanged. `capture_image_with_Bulb` differs in
**9 of 2176 bytes**, at three sites:

| vaddr | v90 | v96 |
|---|---|---|
| `0x101ddf` | literal-pool word `…3448ea` | `…34480a` |
| `0x101ee4` | `str r3, [fp, #-0x10]` | `b #0x2df92c` |
| `0x102188` | `str r0, [fp, #-0x10]` | `b #0x2df9bc` |

The two redirects jump to a code cave that disassembles as:

```
0x2df92c:  cmp r3, #0 ; beq #0x101ee8 ; str r3, [fp, #-0x10] ; b #0x101ee8
0x2df9bc:  ldr r1, [fp, #-0x10] ; cmp r1, #0 ; bne #0x10218c ; str r0, [fp, #-0x10] ; b #0x10218c
```

That is the cancellation check: test the flag, branch around the store if set.
This is the first direct disassembly confirmation of what the cancel writer emits.

### A fixture gap that produced a false failure

With the region re-pinned but nothing else changed, cases 5/6/8/9 went
PARTIAL→FAIL with `UC_ERR_INSN_INVALID`. Attracting this to "Unicorn can't decode
the patch" would have been exactly the misclassification AGENTS.md warns about.
Disassembly showed the cave holds perfectly valid ARM. The real cause: the cave is
*inside* the mapped code window (`0x101000..0x37d000`) but only the carved 2176
bytes are written — `emulator.py:182` documents that everything else in the range
is **zero-filled**. The fixture never loaded the patch's cave.

Fixed with a `memory_patches` entry (the mechanism built for this) seeding
`0x2df800..0x2dfc00` from the retained binary. Also raised `max_instructions`
from the sidecar's 5000 to 200000 **on both builds** so the comparison stayed
like-for-like.

### Result — v96 matches v90 case for case

| Case | v90 | v96 |
|---|---|---|
| 1 normal_bulb_completion | PARTIAL | PARTIAL |
| 2 message_stop_vs_context_cancel | PARTIAL | PARTIAL |
| 3 cancel_result_survives_stop | PARTIAL | PARTIAL |
| 4 stop_failure_preserves_primary_error | **PASS** | **PASS** |
| 5 deferred_timed_capture_cancelled | PARTIAL | PARTIAL |
| 6 normal_timer_expiry | PARTIAL | PARTIAL |
| 7 callback_ordering_register_preservation | FAIL | FAIL |
| 8 output_publication_cleanup | PARTIAL | PARTIAL |
| 9 manual_non_b_control | PARTIAL | PARTIAL |

Nine for nine identical: **no regression** against the reference build. The two
non-PARTIAL outcomes (case 4 PASS, case 7 FAIL) are unchanged from v90 and are
properties of the fixture, which declares no callback edges.

### Direct evidence the patched path executed

Single-fixture runs, same profile, differing only in binary:

| | result | mode | instructions | stub calls |
|---|---|---|---|---|
| v90 | pass | arm | **14303** | 525 |
| v96 | pass | arm | **14305** | 525 |

Identical stub-call signature (`wait_and_handle_event`×501, `gp_log`×6,
`HI_LOG_Print`×6, `sqrt`×3, `setCameraStatus`×2, `textdomain`×2) and **+2
instructions on v96**. The inserted check is on the executed path, and nothing else
about observable behaviour changed. Contract saved beside the artifact:
`out/astro-v96-cancel-writer-20261105/arm-emulation-stage2-v96.json`
(`binary_sha256 d50c5b19…`, `patcher_commit a72e7bf`).

This is emulation, not hardware. Per AGENTS.md, "no emulator result qualifies any
candidate" — it shows the code runs and behaves as expected under stubs, not that a
real camera cancels.

## Two harness defects found (not fixed — different repo)

1. **`validation.py:157` crashes on array indices.** `'.'.join(path)` raises
   `TypeError: sequence item 1: expected str instance, int found` whenever a schema
   error is inside an array. Any invalid runtime manifest produces a traceback
   instead of a readable error. Worked around by validating with `jsonschema`
   directly; the real error was `'expected_path' is a required property`.
2. **`ARM_EMULATION.md` documents `max_instructions: 200000`, but the committed
   sidecars declare `5000`.** The doc example does not match the shipped fixtures,
   which is what made the 5001-instruction timeout look like a v96 behaviour at
   first. Nothing here is wrong with the code; the documentation is stale.
2. **Two pre-existing test failures**, unrelated to this session:
   `test_smoke::test_cli_help` and `test_integration::test_harness_cli_integration`
   both fail with `FileNotFoundError: 'polaris-harness'` — the console script is not
   installed in `.venv`, which is empty. A stash dated 2026-09-29 predates this work;
   the harness tree is unmodified by me.

## Also learned about the stock packet

`package verify --stock` **cannot** be used with
`BenroPolarisPatcher/firmware/FwPkt.zip`. That factory image has 10 members and no
`FwVer`; the verifier requires `FwVer` in both packets, so every unchanged-member
check fails with `STOCK_MEMBER_MISSING`. The stock comparison is therefore unusable
against this particular stock file. Re-run without `--stock` gives a clean PASS.

## Boundary, stated plainly

Per AGENTS.md: **"A harness PASS is never proof of physical camera support."**

What is now established: the v96 packet is internally consistent, its declared
provenance matches the artifacts, its Stage-2 ELF files are ARM 32-bit and resolve
to the paths `install_stage2.sh` targets, and an emulated SD-card upgrade from
`.95` to `.96` completes and verifies after reboot.

What is **not** established: that a real Polaris updater accepts it, that the
device boots it, that the on-device loader selects these libraries, or anything at
all about red-cancel behaviour on a K-3 III. Which handler the control reaches is
still inferred from symbol names, never traced.

The Astro candidate also remains **not accepted** for install: its packet README
requires the standard camera owner to accept the shared baseline and patcher issue
#251 to be closed or explicitly waived. Neither has happened.
