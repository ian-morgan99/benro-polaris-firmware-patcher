# Using the benro-polaris-test-harness ARM emulator for #251

> **Status update, third pass on 2026-10-31 (harness HEAD `a907fcb`).** A further
> commit claimed #16-#20 were addressed. It contains **no `src/` changes** - only
> tests and fixtures - so it can close test-coverage gaps but not behavioural ones.
> Verified by execution: **#16 is now genuinely fixed and regression-tested** (real
> ARM encodings execute; suite 58 passing, harness-wide 160). **#21 and #22 still
> reproduce unchanged.** **#18 still has five `TBD` provenance fields** and its new
> test only inspects the sha/address/size/mode rows, so it passes while the
> requirement is unmet. **The lifecycle suite is still 9 SKIP / exit 0 - no camera
> code executes, so #251 remains unqualified by the harness.** See "Third pass:
> `a907fcb`" below; transcript `harness-reverification-a907fcb.txt`.
>
> **Earlier update (same day).** The harness addressed #16-#19 in `f6bc210`. ARM
> mode and AAPCS marshalling began working, and the lifecycle suite reports SKIP
> instead of FAIL. Three follow-up defects were filed as harness #21-#23. See
> "Retest after `f6bc210`" below; original findings are retained for context.

Checked 2026-10-31 against:

| Component | Revision |
|---|---|
| Patcher (authorized delivery worktree `/home/ian/polaris-build-73`, `main`) | `8c015c0a73c8affea8fa723badcceb4070ef81b4` |
| Harness (`BenroHardwareValidator/benro-polaris-test-harness`, `main`) | `e69d5e413dfd06dea41975d561b991e5ff548dc5` |
| Unicorn / capstone used for every run below | 2.1.4 / 5.0.7 |
| Interpreter actually used | sandbox `python3` 3.13.15 (see "Environment") |

Transcripts: [`docs/evidence/issue-251-harness-emulator-20261031/`](evidence/issue-251-harness-emulator-20261031/)

## Short answer

**Yes, the harness emulator runs, and no, it cannot test #251 yet.** It executes
ARM **Thumb** only; `pgphoto` is ARM-mode. The 9 lifecycle cases that are supposed
to be the #251 tests execute a 2-instruction synthetic fixture, so all 9 fail. The
patcher's own ARM suite already does the real work and passes.

| Question | Answer | Evidence |
|---|---|---|
| Does the emulator execute ARM instructions? | Yes — Thumb only | `tiny_fixture` → `result: pass`, `instructions_executed: 2` |
| Can it execute `capture_image_with_Bulb`? | No | real region → `unsupported_instruction`, `instructions_executed: 0`, at `0x1002` |
| Do the 9 #251 lifecycle cases pass? | No, all 9 fail, CLI exits 3 | `harness-lifecycle-suite-cli.txt` |
| Does #251 need it? | Not today — patcher has its own ARM-mode suite | 85/85 pass; offline gate GREEN 10/0/0 |
| Is #251 fixed? | No | cancel diagnostic still RED, exit 1 |

## Third pass: `a907fcb` (claimed #16-#20)

The decisive fact is in the diff, not the commit message:

```text
$ git show --name-only a907fcb | grep '^src/'
(no output)
```

Tests and fixtures only. So behavioural defects cannot have been fixed by it.

| Issue | Verified result on `a907fcb` |
|---|---|
| #16 ARM mode | **Fixed and now tested.** `arm_mode_fixture.bin` decodes to real ARM (`e3a00001 e12fff1e` = `MOV R0,#1; BX LR`). Three new tests cover execution, mis-decode fail-closed and invalid-mode rejection. Reasonable to close. |
| #17 marshalling | **Partial.** R0-R3 and R0 write-back are tested and work. `abi_shape` still dead, PLT-target fall-through unchanged, calls still recorded as flat `aapcs_call`. Needs a source fix (#22). |
| #18 provenance | **Not done.** Five fields still `TBD`; binary absent. New TBD check is scoped to sha/address/size/mode lines only, so it reports green while #15's binding requirement is unmet. |
| #19 SKIP semantics | Behaviour correct (9 SKIP, exit 0) but no CLI test exists; cases still have no real input. |
| #21 failure-path provenance | **Still reproduces** - `mode='thumb'` on an ARM run, `instructions_executed=0` against an internal counter of 15. |
| #22 abi_shape / entry model | **Still reproduces** - target registration falls through; flat label persists. |
| #23 regression tests | **Partly.** +7 tests (58 total). Missing: failure-path provenance, `abi_shape`, caller continuation, CLI exit code. |

A subtle one worth knowing before trusting the new AAPCS test: it registers the
stub at the BL **target** and asserts only arguments and R0. Run directly it
reports `instr_reported=4924` on a 4-instruction fixture - after interception PC
advances into unmapped space and runs to the instruction limit - yet still returns
`pass`. The test masks the fall-through described in #22. A caller-continuation
assertion (`R2 == 0x33` style) would catch it.

**Net for #251: unchanged.** Critical path is still **#18 (needs your redistribution
decision) -> #22 source fix -> real lifecycle fixtures under #19**, with #21 and the
rest of #23 alongside. Our own patcher verification remains authoritative and RED.

## Retest after `f6bc210` (harness #16-#19)

Verified independently, not by trusting the commit message. Transcripts:
`harness-readiness-f6bc210.txt`, `harness-acceptance-probe.txt`.

| Item | Result |
|---|---|
| Harness suites | 51 ARM emulator + 142 total, all pass; no regressions |
| #16 ARM mode | **Works.** ARM fixture executes to `BX LR`, `instructions_executed=3`, contract records `mode=arm`. Unknown mode raises `ValueError` at construction. ARM bytes mis-decoded as thumb do not silently pass. |
| #17 marshalling | **Partly works.** R0/R1 reach the stub, return lands in R0, control resumes at call site + 4. But `StubProfile.abi_shape` is never consumed - `_marshal_stub_call` hardcodes `arg_count=4`, so stack args past R3 and pointer dereference are unreachable dead code (harness #22). |
| #18 Stage-2 region | **Not delivered.** `stage2_region.bin` still absent; provenance table retains five `TBD` fields. |
| #19 SKIP semantics | **Works.** Nine cases report `SKIP - no ARM-mode Stage-2 fixture available`; CLI exits 0 (was exit 3 / 9 FAIL). |
| New defects | harness #21, #22, #23 |

The two that matter most for evidence integrity:

- **#21 - false provenance on failing runs.** `mode` and `instructions_executed`
  are set only after `emu_start()` succeeds, so a faulting run reports the
  dataclass defaults. Reproduced: requested `mode='arm'`, contract says
  `mode='thumb'`; internal counter executed 15 instructions, contract reports 0.
  The failing record - the one we would rely on - is wrong.
- **#23 - no regression tests.** `f6bc210` adds zero test files; nothing in
  `tests/test_arm_emulator.py` references `mode=`, `register_stub_entry` or
  `abi_shape`. Both defects above would have been caught by the tests listed in
  #23.

One API trap worth knowing before pointing real code at stubs: `register_stub_entry`
intercepts the **call site**, not the call target. Registering the `BL` address
resumes correctly at call site + 4; registering the branch target (how real
`pgphoto` PLT calls resolve) falls through into the instruction after the stub body.

```text
register BL site   0x1008 -> R2=0x33 (resumed at call site+4)  CORRECT
register BL target 0x1010 -> R3=0x44 (fell through past stub)  WRONG
```

**Net for #251: unchanged.** The harness is a working ARM emulator with correct
fail-closed behaviour, but it still has no Stage-2 input, so it cannot exercise the
cancellation path. Our own verification remains authoritative and is still RED.

## Environment (this sandbox)

The harness `.venv` is unusable from here: `.venv/bin/python3` symlinks to
`/usr/bin/python3`, which resolves to 3.13 while the venv is 3.12, so
`.venv/bin/polaris-harness` dies with `ModuleNotFoundError: No module named
'polaris_harness'`. The venv also has no `unicorn`, so even a working interpreter
there would not run the emulator.

Use the sandbox interpreter against the source tree instead — it already has
Unicorn 2.1.4:

```sh
H=/home/ian/Documents/VSCodeProjects/BenroHardwareValidator/benro-polaris-test-harness
cd "$H"
PYTHONPATH=src python3 -m pytest tests/test_arm_emulator.py -q     # 51 passed
PYTHONPATH=src python3 -m polaris_harness.cli arm-emulate --fixture tiny_fixture \
    --output /tmp/arm_result.json                                   # exit 0, pass
```

`--cov-fail-under=80` from the harness CI job does not work here (no `pytest-cov`).
Do not install packages into this sandbox to make it work; that is a separate
decision.

One real defect was fixed by the harness update while I was testing: at `5add765`
`_setup_hooks()` referenced `UC_HOOK_INTR`/`self._hook_intr`, which did not exist,
so **every** fixture run failed with `'ARMEmulator' object has no attribute
'_hook_intr'`. That is gone at `e69d5e4`. If you see that error, your tree is
stale — and delete stale `__pycache__/arm_emulator` bytecode before re-testing; it
hid the fix on first run.

## What the harness gives us today

Working and useful:

- Fail-closed behaviour is genuinely exercised: illegal opcode →
  `unsupported_instruction`; infinite loop → instruction-limit `timeout`; missing
  stub → `missing_stub`; SVC #0 → OS stub dispatch recorded.
- Every run emits a provenance-bound JSON contract (binary SHA-256, patcher
  commit, harness revision, emulator version, stub profile, command, registers,
  stub calls). That format is the right shape for #251 evidence.
- The stub registry records call order and per-call register snapshots, which is
  what cases 3, 4 and 7 need.

Not usable for #251:

1. **Thumb only.** `emulator.py:341` hardcodes `Uc(UC_ARCH_ARM, UC_MODE_THUMB)` and
   `run()` ORs the Thumb bit onto PC/LR (`entry_address | 1`). `EmulationConfig`
   has no mode field. `pgphoto.stage2ondisk` is `Flags: 0x5000200, Version5 EABI,
   soft-float ABI` — ARM mode. Its first words are `e92d4810 e28db008 e24dd0d4`.
   Decoded as Thumb these mis-frame at +2, which is exactly where the run stops.
2. **No ABI argument marshalling.** Stubs receive a Python `arguments` list built
   by the harness, not values read from R0–R3 / the stack. Real code calling
   `camera->cmd(...)` cannot reach a stub meaningfully.
3. **The 9 lifecycle cases execute nothing relevant.** Every case builds its
   emulator from `fixture_name="tiny_fixture"` (`MOV R0,#1; BX LR`) and then
   asserts stop/close/cancel/timer/callback events. Two instructions cannot
   produce them, so all 9 fail with "not observed". The assertions are correct;
   the input is absent.
4. **`stage2_region.bin` is still a placeholder** — only
   `stage2_region.bin.placeholder` exists.

## Reproduced #251 results (patcher main)

These are the authoritative results for #251 right now, independent of the harness:

```sh
cd /home/ian/polaris-build-73
python3 -m pytest -q tests/test_polaris_bulb_dispatch_arm.py    # 85 passed
./tests/run_prerelease_gate.sh \
    --libgphoto2-src /home/ian/Documents/VSCodeProjects/LibGphoto2-v86-main
# 10 passed, 0 failed, 0 skipped -> GREEN, OFFLINE-QUALIFIED only
OBJDUMP=/tmp/prerelease-objdump-host.sh python3 tools/audit_polaris_bulb_cancel.py \
    out/o-v18m-k1ii-pgphoto-readiness-20261029/stage2-ondisk/ondisk/pgphoto.stage2ondisk
# exit 1 -> RED
```

`CANCEL input=-52, stub stop result=0, subsequent saved result=0` — a successful
stop still overwrites the saved cancellation. **Unchanged from 2026-10-30.** A
green offline gate does not clear this; do not close #251 on it.

Two things worth knowing so results are not misread:

- `arm-linux-gnueabi-objdump` is not on PATH here. Build the wrapper with the
  gate's own resolver (`resolve_objdump()` in `tests/run_prerelease_gate.sh`,
  lines ~175–201); it emits `/tmp/prerelease-objdump-host.sh` using the
  `/run/host` bind and GNU Binutils 2.42. Without it the gate SKIPs that check —
  never silent green.
- `--check` is input-sensitive by design. On pristine stock
  (`0308393632dd…`) it reports `timed Bulb dispatch marker missing`; on the
  already-patched readiness binary it reports `capture_image_with_Burst prologue
  is not the verified stock sequence`. Both are correct fail-closed responses. The
  documented pass path is: copy stock → `--in-place` → `--check` twice. I did that;
  the patched copy hashed `52f0727b59ed7e27681e224973132bbce634f89969da63d61553b934ea042311`,
  matching the recorded value, and both checks passed.

## What must change in the harness before it can qualify #251

Ordered by dependency, for harness issue #15:

1. Add `mode` to `EmulationConfig` (`"arm"` / `"thumb"`), pass it to `Uc(...)`,
   and stop forcing `| 1` on PC/LR in ARM mode. Without this nothing else matters.
2. Add register/stack argument marshalling so a stub call reads R0–R3 (and the
   stack past R3) per AAPCS, and writes returns to R0. Otherwise stub calls from
   real code are meaningless.
3. Add a real `stage2_region.bin` with provenance. I extracted a candidate
   read-only for this check: `capture_image_with_Bulb`, symbol `0x101aac`, size
   2176, region SHA-256
   `23398c6efc7c737c1b2b91664a98b45a2b7bc01f97e704c3ccb4bf3fc4a618c3`. It is not
   checked in — the harness must own that decision and its stub profile.
4. Point each lifecycle case at that region with per-case entry addresses and
   preconditions, instead of `tiny_fixture`. Keep `tiny_fixture` as the engine
   smoke test only.
5. Until 1–4 land, the harness suite should report those 9 cases as **SKIP with a
   reason**, not FAIL. Nine red cases that fail for a missing fixture hide the one
   red case that is a real defect.

## Evidence-hierarchy boundary

An ARM emulator PASS proves only that a consumer handles a known recorded ARM
contract. It does not prove physical camera behaviour, installed Stage-2
interposition, shutter movement or file publication. Per `AGENTS.md`, #251 still
requires the device install-hash checks and supervised Benro Connect / Manual /
Bulb regression. Nothing here changes that.
