# Build and source recovery evidence — 2026-10-30

Status: offline gate GREEN; #251 remains open and hardware-unqualified.
No firmware package was built, published or installed, no camera was operated,
and no release version was consumed. See [the handoff](../../ISSUE-251-HANDOFF.md)
for the exact worktrees, archive tag and remaining defects.

## Source identity

- Patcher base: `aecf7a360d90f35df9dd60b29ee93101e8da0036` plus the release-entry
  repair committed with this evidence. Runtime machine-code generation is
  unchanged from that partial fix; the patcher source edits here only correct
  misleading comments. `tested-source.sha256` pins the tested script contents.
- Library: clean local and remote `main`,
  `051d224dbd33fda67ff65ce73a6d6bbd9c9a3aff`.
- Recovered experimental source: archived tag `archive/issue-251-wip-20261030`,
  commit `c8fa42910b6a2c6ecdecf4cd558cce5645fa6cc0`. It was not merged.

## Commands and results

`./tests/run_prerelease_gate.sh` completed with exit 0 from stable scripts:

- Aggregate: 9 checks pass, 0 fail, 1 skip (no `--libgphoto2-src` argument).
- Deterministic suite: 25 pass, 0 fail, 2 prerequisite skips
  (`test_source_input.sh`, `test_polaris_pentax_build_package.sh`).
- Python suite: 397 pass, 8 skip.
- ARM Stage-2 shared library compiled with `-Wall -Wextra -Werror`.
- Package and physical gates were not requested. The reported GREEN is only
  the scope of the existing offline checks; it does not resolve #251.

Logs: `offline-gate.txt`, `deterministic.txt`, `pytest.txt`.
An earlier run was invalidated when this agent edited the runner while Bash
was still executing it; that run ended with a transient parse error and is not
used as evidence. The final complete run above began after the scripts stopped
changing. `bash -n` and `git diff --check` also passed.

The separate clean library build used the runbook's host regression setup:

```sh
meson setup /tmp/polaris-main-compile.2MuVr5 \
  /home/ian/Documents/VSCodeProjects/LibGphoto2-v86-main \
  --buildtype=debugoptimized -Dcamlibs=ptp2,pentax,directory
meson compile -C /tmp/polaris-main-compile.2MuVr5
meson test -C /tmp/polaris-main-compile.2MuVr5 --no-suite no-ci --print-errorlogs
```

Compilation completed; 20 tests passed, including the Pentax capture contract,
Bulb lifecycle, publication and session tests. `library-tests.txt` retains the
result. This host Meson test build is distinct from the shipped ARM/autotools
configuration. The hardware-dependent `no-ci` suite was excluded.

The new desktop-wrapper test first failed against the old `.77` default.
After correction, its four cases pass; with the existing monotonic-version
tests, `python3 -m pytest -q tests/test_build_and_install_entrypoint.py
tests/test_display_fwver_monotonic.py` reported 45 passes. It substitutes
Docker, clone and release-builder calls, so no package or device is involved.
The real version guard independently rejects `.77` against the `.90` registry;
`--next` returned `.91` without reserving it.

## Real ELF patch check

Extracted a disposable copy from the documented retained stock appfs:

- Stock appfs SHA-256:
  `5cbd24fd2a618f7939033aa77620e66a4132a2507109efcc16e59f57b3e565ef`.
- Extracted stock pgphoto SHA-256:
  `0308393632dd41d974bd1064e61942655131fe5392959a334cf24623d1bd4a62`.
- Partial-patch output SHA-256:
  `6575e3b272e108a0c83c8750bb9dc83bbbf1ebdbf3c66ecacf3d69d0a9875da0`.

The normal patcher wrote a separate `.patched` file, `--check` passed, and
repeating the patch reported `already patched`. The stock input hash stayed
unchanged. See `stock-elf-check.txt`. This avoids the earlier mistake of using
the already-patched v90 artifact as pristine input. The temporary output was
not packaged or executed; no full-stack or physical claim follows from it.

## Current limitations

Unicorn and qemu-arm remain unavailable in this environment; the recovered
ARM execution diagnostics were not rerun. Their historical results are not
counted above. Missing emulator support is separate from compiler success and
from the known cancellation defects. Follow #251's acceptance criteria and
the documented firmware process before supervised physical testing.
