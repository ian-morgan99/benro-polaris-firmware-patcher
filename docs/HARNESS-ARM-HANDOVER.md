# Handover: make the test harness able to qualify patcher issue #251

Audience: an agent working **in the harness repo**
(`BenroHardwareValidator/benro-polaris-test-harness`, `main`).
Read `AGENTS.md` and `docs/ARM_EMULATION.md` there first.

Canonical issues: patcher
[#251](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/251)
(camera fix, stays the owner of acceptance criteria) and harness
[#15](https://github.com/ian-morgan99/benro-polaris-test-harness/issues/15)
(reusable emulator platform). The four blocking items below are filed against the
harness repo and referenced from #15:

| Task | Harness issue | Blocks | Status after retest (`f6bc210`) |
|---|---|---|---|
| 1 ARM vs Thumb mode | [#16](https://github.com/ian-morgan99/benro-polaris-test-harness/issues/16) | everything below | **Landed and verified** |
| 2 Stub ABI marshalling | [#17](https://github.com/ian-morgan99/benro-polaris-test-harness/issues/17) | cases 3, 4, 7 | **Partial** - R0-R3 + return work; `abi_shape` dead (see #22) |
| 3 Pinned Stage-2 region | [#18](https://github.com/ian-morgan99/benro-polaris-test-harness/issues/18) | all nine cases | **Not delivered** - still absent, five `TBD` fields |
| 4 Real lifecycle input + SKIP semantics | [#19](https://github.com/ian-morgan99/benro-polaris-test-harness/issues/19) | #251 consumption | **SKIP semantics landed**; cases still have no real input |

Follow-up defects found during the retest, filed against the harness:
[#21](https://github.com/ian-morgan99/benro-polaris-test-harness/issues/21)
(false provenance on failure paths),
[#22](https://github.com/ian-morgan99/benro-polaris-test-harness/issues/22)
(`abi_shape` never consumed + call-site vs PLT-target ambiguity),
[#23](https://github.com/ian-morgan99/benro-polaris-test-harness/issues/23)
(no regression tests for #16-#19).

**Remaining critical path to qualifying #251: #18, then #22, then real lifecycle
input under #19.** #21 and #23 must land alongside them or the evidence produced
will be both untested and misreported.

## Verified state at handover (2026-10-31)

| Repo | Revision | State |
|---|---|---|
| Patcher `/home/ian/polaris-build-73` (`main`) | `8c015c0a73c8affea8fa723badcceb4070ef81b4` | offline gate GREEN 10/0/0; 85 ARM tests pass; cancel diagnostic RED exit 1 |
| Harness `main` | `e69d5e413dfd06dea41975d561b991e5ff548dc5` | 51 emulator tests pass; `arm-emulate --suite` exits 3 with all 9 cases FAIL |

Engine: Unicorn 2.1.4, capstone 5.0.7. Transcripts:
[`evidence/issue-251-harness-emulator-20261031/`](evidence/issue-251-harness-emulator-20261031/)
in the patcher repo.

The emulator engine itself is sound — it executes Thumb instructions, counts
them, records stub calls with register snapshots, and fails closed correctly on
illegal opcodes, runaway loops and missing stubs. Do not rewrite it. The work is
four specific gaps, in dependency order.

## Task 1 — ARM vs Thumb mode (hard blocker) — harness #16

`src/polaris_harness/arm_emulator/emulator.py:341` hardcodes
`Uc(UC_ARCH_ARM, UC_MODE_THUMB)`, and `run()` ORs the Thumb bit onto PC and LR
(`self.config.entry_address | 1`). `EmulationConfig` has no mode field.

Our target binary is ARM mode, not Thumb:

```
pgphoto.stage2ondisk: ELF 32-bit LSB EXEC, ARM, Flags: 0x5000200,
                      Version5 EABI, soft-float ABI
capture_image_with_Bulb @ 0x101aac, size 2176
first words: e92d4810 e28db008 e24dd0d4   (STMFD/LDR/ADD — ARM encodings)
```

Feeding that region in today gives `unsupported_instruction`,
`instructions_executed: 0`, failing at `0x1002` — the classic mis-framed-word
signature of decoding ARM bytes as Thumb.

Required:

- Add `mode: str = "thumb"` to `EmulationConfig`, accepting `"arm"` and `"thumb"`.
- Map it to `UC_MODE_ARM` / `UC_MODE_THUMB` in `_initialize_unicorn()`.
- Only set the Thumb bit on PC/LR when mode is `"thumb"`. In ARM mode PC must be
  written unmodified.
- Reject unknown mode values at construction time (fail closed, not silently
  defaulting).
- Record the mode in `EmulationResultRecord` and the JSON contract so evidence
  stays self-describing.
- Tests: run the existing Thumb fixtures unchanged (they must still pass), plus a
  new ARM-mode fixture proving an ARM-mode instruction sequence executes and
  reaches `BX LR`. Assert `instructions_executed > 0` in both modes.

## Task 2 — AAPCS argument marshalling for stubs — harness #17

Stubs currently receive a Python `arguments` list that the harness invents
(`emulator.py:_call_stub`, `stubs.py:StubRegistry.call`). Real code passes
arguments in R0–R3, with anything beyond on the stack. Until stubs read the
actual registers, a call from real camera code into a stub carries no meaning,
and cases 3, 4 and 7 cannot be decided.

Required:

- When execution reaches a stub entry address, read R0–R3 (plus stack words past
  R3 when the profile declares more) and pass those as `arguments`.
- Write the stub's return value back into R0 and continue execution.
- Let the stub profile declare the ABI shape per boundary (argument count,
  whether arguments are pointers into emulated memory, and if so how many bytes to
  dereference for recording).
- Keep recording the full register snapshot per call — that already works and is
  what case 7 needs.
- Fail closed on a stub entry reached with fewer readable arguments than the
  profile declares (unmapped memory → `MISSING_STUB`/error, not a silent zero).
- Tests: an ARM-mode fixture that loads two known values into R0/R1, calls a stub
  address, and asserts the recorded arguments equal those values and that the
  stub's return value lands in R0.

## Task 3 — Check in the provenance-pinned Stage-2 region — harness #18

`tests/fixtures/arm/stage2_region.bin` is still only
`stage2_region.bin.placeholder`. Without real code, #15 delivers a platform with
nothing to run.

A candidate was extracted read-only during this review and is **not** checked in:

```
source   pgphoto.stage2ondisk (v90-era), symbol capture_image_with_Bulb
address  0x101aac   size 2176 bytes
sha256   23398c6efc7c737c1b2b91664a98b45a2b7bc01f97e704c3ccb4bf3fc4a618c3
```

Decide and record, in the fixture's JSON sidecar:

- the exact source binary SHA-256 and where it is retained;
- the patcher commit the region corresponds to;
- entry address, function size, instruction mode (`arm`);
- the stub profile that region requires.

Constraints from #15 still apply: never patch or mutate the input artifact; fail
closed on unknown hashes/layouts. If the binary cannot be redistributed in-repo,
record the hash plus a retrieval procedure instead — but say so explicitly rather
than leaving a placeholder.

## Task 4 — Point the lifecycle cases at real code; stop reporting FAIL for a missing fixture — harness #19

`lifecycle.py` builds every case with `fixture_name="tiny_fixture"` — a 2-instruction
synthetic `MOV R0,#1; BX LR`. The nine cases then assert stop/close/cancel/timer/
callback events. Two instructions cannot produce them, so all nine fail with "not
observed". The assertions are correct; the input is absent.

Required:

- Each case takes its own fixture, entry address and preconditions (initial
  register values, timer state, whether cancellation was requested) rather than
  sharing one synthetic blob.
- Keep `tiny_fixture` as an engine smoke test only, not as lifecycle input.
- Until Tasks 1–3 land, report the nine cases as **SKIP with a reason** ("no
  ARM-mode Stage-2 fixture available"), not FAIL. Nine red lights caused by a
  missing input hide the one red light that is a real defect — which is exactly
  the situation today. Distinguish "cannot run" from "ran and failed" in both the
  CLI output and the exit code.

## Definition of done

1. `polaris-harness arm-emulate --suite` exits 0 with all nine cases genuinely
   executing ARM-mode Stage-2 code, or exits non-zero with per-case reasons that
   are real behavioural failures.
2. A case fails if a cancel edge becomes unconditional, and fails if normal
   completion takes the cancel path — positive *and* negative assertions, as #15
   requires.
3. The patcher can consume one machine-readable result per run without importing
   harness internals.
4. CI still treats a missing emulator as a hard failure for the ARM job, not a
   silent skip.

## Boundaries — do not cross

- This is **not** a Pentax/PTP or physical camera emulator. Do not claim
  otherwise in docs or issue comments.
- An emulator PASS proves only that a consumer handled a known recorded ARM
  contract. It does not qualify firmware, and it does not close #251. Device
  install-hash checks and supervised Benro Connect / Manual / Bulb regression
  remain mandatory.
- No privileged QEMU, no host networking/bridge/iptables changes, no implicit
  system package installation.
- Keep `arm_emulator/` independent: no imports from `polaris_harness.engine`,
  `.runtime` or `.transport`.
- Never mutate the input binary.

## Known environment traps (save yourself the time)

- The harness `.venv` is unusable from the current sandbox: `.venv/bin/python3`
  symlinks to `/usr/bin/python3`, which resolves to Python 3.13 against a 3.12
  venv, and the venv has no `unicorn`. Use the sandbox interpreter with
  `PYTHONPATH=src python3 -m polaris_harness.cli …` instead. Do not install
  packages into the sandbox to work around this.
- Stale `__pycache__` in `arm_emulator/` masked a real fix during this review and
  caused a false failure. Clear bytecode before re-testing.
- `--cov-fail-under=80` from the CI ARM job does not run in that sandbox (no
  `pytest-cov`). Note it as unverified rather than quietly dropping the gate.
- At `5add765`, `_setup_hooks()` referenced a non-existent `_hook_intr`, so every
  fixture run errored with `'ARMEmulator' object has no attribute '_hook_intr'`.
  Fixed at `e69d5e4` — if you see that error, the tree is stale.

## What the patcher already has (context, not work for you)

The patcher ships its own ARM-mode Unicorn suite
(`tests/test_polaris_bulb_dispatch_arm.py`, 85 tests, uses `UC_MODE_ARM`) and an
exact-binary cancellation diagnostic (`tools/audit_polaris_bulb_cancel.py`). The
diagnostic is currently RED: cancelled wait `-52` plus a successful stop `0`
returns `0`, not `-52`. That defect belongs to #251; do not attempt it from the
harness repo. The harness's job is the platform, then #251 consumes its result.
