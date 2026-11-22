# astro-v115-k01-camera-admission-20261122 — build attempt, gate RED, nothing installed

Scope: preserve the evidence from the interrupted 2026-11-22 v115 build attempt.
Full resume instructions live in
[`../../V115-HANDOFF-20261122.md`](../../V115-HANDOFF-20261122.md). This directory
holds the transcripts that would otherwise have been lost, because they were written
under gitignored `out/`.

## Outcome

**No install. Device identity is still v114.** Verified read-only at ~20:45 GMT:
`FwVer:6.0.0.54.114;date:2026.11.19;`, uptime `83768.72` (no reboot).

The build ran as systemd user unit `polaris-v115-build-nov22.service` from
`/home/ian/polaris-v101` and exited 1 at 20:26:40Z on a RED gate:

```
Pre-release gate summary: 25 passed, 1 failed, 1 skipped
Failed: container deterministic harness (exit 1)
GATE: RED — do not stage/install the FwPkt until the failed checks pass.
BUILD FAILED (exit 1)
  WARNING: a partial FwPkt.zip exists -- do NOT use it
```

## Cause and fix

`container/test_keepalive_required.sh:51` used the bashism `exec -a` under a
`#!/bin/sh` shebang. `tests/run_deterministic.sh:53` runs each test through its own
shebang, so on this host (dash) it aborted with `exec: -a: not found`. Test bug, not
a product regression; it passed locally only because bash was used there.

Fixed in the canonical tree by generating a POSIX `polaris-bt-keepalive.sh` wrapper
so `/proc/<pid>/cmdline` still carries the string `detect()` looks for. Re-verified:
`34 passed, 0 failed, 2 skipped`, exit 0 (see `deterministic-after-fix.txt`). The
builder clone `/home/ian/polaris-v101` does **not** have the fix yet.

## Files here

| File | Origin |
|---|---|
| `gate-build-v115-host.txt` | `out/k01-378-reviewed-20261122/build-v115-host.log` (workspace tree, gitignored) |
| `builder-astro-v115.txt` | `/home/ian/polaris-v101/out/logs/astro-v115-k01-camera-admission-20261122.log` |
| `deterministic-after-fix.txt` | full harness run after the fix, `EXIT=0` |
| `k01-summary.txt` | K-01 harness summary from the merged-driver check |
| `issue117.md`, `issue378.md`, `issue379.md` | issue notes gathered during the session |

## Reading these logs correctly

- `FAIL: 1 mismatch(es) across 5 entries`, `FAIL: 2 structural error(s)`,
  `FAIL: 6 mismatch(es) across 6 entries` are **negative controls inside passing
  tests** — a manifest naming a file the card lacks must fail. Not gate failures.
- `WARN: this single display version moves 3 shipped components … registry entry
  must describe every one of them` is a warning about `libpolaris_stage2.so`,
  `pgphoto.stage2ondisk` and `ptp2.so` sharing one display version. Not blocking;
  worth a registry entry review before the next release.
- Skips are prerequisite-gated: `test_polaris_pentax_build_package.sh`,
  `test_source_input.sh`, and the firmwareInfo manifest gate (no stock `FwPkt.zip`
  in repo).

## Do-not-use artifact

```
/home/ian/polaris-v101/out/astro-v115-k01-camera-admission-20261122/FwPkt.zip
  size   68409670 bytes
  md5    a9bc2a83dd90a7188ca8a7bc32e7cf87
  sha256 18ccd7d18e57c7cbebd96f8f08939a864f0de3910e91376f9236d4f992550e48
```

Produced under a RED gate. Never stage or flash it; quarantine before rebuilding.

## Candidate identity (unchanged, ready to rebuild)

- Driver pin `0f2f34e0004011136fa75bf43e215acc0c8b9fdb` (PR #168 + #169 merged).
- Patcher `466c17a15dbd57b1c0e165d961be8abcc1a7ed0a` on `main`, pushed.
- Release record `docs/release-change-summary-v115-astro.json`
  (md5 `52239101125a8dc7cdaf1d650675f75c`, identical in both patcher trees).

## No camera evidence

The session stopped before the installer ran. K-01 SCSI port inside pgphoto on
Polaris, and K-1 II shutter / exact restoration / live preview cadence, are still
unqualified on device. No physical 645D was available.
