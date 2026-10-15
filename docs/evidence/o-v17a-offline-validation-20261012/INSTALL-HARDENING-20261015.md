# o-v17a install-script hardening — 2026-10-15 (issue #199 review of 304e899)

Implements all four findings from the 2026-10-14 review comment on commit
`304e899` (installation/release safety), plus the requested negative tests.

## 1. Mandatory installed-binary SHA-256 verification (finding 1)

- New `scripts/generate-fwpkt-manifest.py`: extracts the candidate's
  `camera/appfs.ubifs` and writes an **immutable, candidate-specific**
  `install-manifest.json` next to the staged `FwPkt.zip`. It records the full
  SHA-256 of every mandatory installed file (10 for o-v17a: `/app/FwVer`,
  `/app/bin/polestar_app`, the nine `lib/stage2/*` binaries/libs, and
  `openpolaris-libgphoto2-provenance.txt`), the zip digest, and the target
  FwVer content.
- `phase_verify()` now reads every mandatory file back over SSH after reboot
  and compares full SHA-256 against the manifest. Missing/unreadable/mismatched
  files or unavailable SSH fail verification. Verdicts are explicit:
  **verified** | **installed-unverified** (version present, digests not) |
  **not-installed**. A version string alone no longer passes.
- The gate (`tests/run_prerelease_gate.sh --build`) now requires the manifest to
  exist for the candidate and its recorded zip digest to match the current
  `FwPkt.zip` (a stale manifest would verify the wrong build).

## 2. Authorisation gate on destructive install (finding 2)

New `phase_auth()` runs before stage/reboot in every mode:

- **Candidate digest**: zip SHA-256 must equal the frozen manifest digest.
- **Device identity**: SSH host key verified — default is
  `StrictHostKeyChecking=accept-new` against a per-host known_hosts file (first
  contact pins, later contacts must match); with `EXPECTED_HOST_KEY` set the
  scanned key must equal the recorded key exactly. The running FwVer must be in
  the `6.0.0.54.x` family or the install is refused (wrong device).
- **Idle/capture-state check**: wire code 286 is queried; a camera present
  (`state:1`) blocks the reboot unless `ALLOW_BUSY=1`.

## 3. Reboot delivery classification + no blind reflash (finding 3)

- `phase_reboot()` now classifies delivery: **observed** (device goes dark
  within `REBOOT_DARK_WATCH`, default 60 s) vs **uncertain** (send failed or the
  device never went dark). Uncertain delivery is reported, not claimed as a
  successful reboot.
- `phase_stage()` skips the scp entirely when the device already reports the
  target FwVer — polling/retries never blindly reflash an already-updated
  device.
- New modes: `--stage-only` (staged-install capability without the destructive
  reboot) and `--verify-only` (re-prove a device rebooted elsewhere).

## 4. Offline-qualified gate wording + stage2ondisk predicate (finding 4)

- The offline gate summary now prints **GATE: GREEN — OFFLINE-QUALIFIED only**
  and states explicitly that it is NOT device-qualified or release-qualified;
  the mandatory device install hash checks and the physical Benro Connect /
  Manual / Bulb regression remain separate gates.
- The `pgphoto.stage2ondisk` SKIP is now machine-checked: it is acceptable only
  when the repacked appfs has **no `lib/stage2` tree at all** (nonmandatory).
  If `lib/stage2` is present but `pgphoto.stage2ondisk` is missing, the gate
  fails. The manifest records the same predicate (`stage2_mandatory`) so the
  verify phase applies it too.

## Negative tests (all offline, fake ssh/scp/nc + TCP gate)

`tests/test_autonomous_install.py` — 12 tests, all passing:

| Test | Covers |
|---|---|
| `test_happy_path_verified` | full wake→auth→stage→reboot(observed)→verify |
| `test_hash_mismatch_is_installed_unverified` | finding 1: digest mismatch → exit 5 |
| `test_missing_binary_fails_verification` | finding 1: missing mandatory file → exit 5 |
| `test_spoofed_version_is_not_installed` | version present but ≠ target → not-installed |
| `test_busy_camera_blocks_auth` | finding 2: state:1 blocks (exit 6); ALLOW_BUSY=1 proceeds |
| `test_wrong_host_family_refused` | finding 2: foreign FwVer family refused |
| `test_failed_reboot_reports_uncertain_delivery` | finding 3: no dark → uncertain, still verified |
| `test_no_blind_reflash_when_already_updated` | finding 3: target FwVer present → scp skipped |
| `test_manifest_digest_mismatch_refuses` | finding 2: zip changed after freeze → refused |
| `test_poll_survives_interrupted_wake` | interrupted/repeated polling recovers |
| `test_host_key_mismatch_refuses` / `test_host_key_match_proceeds` | finding 2: host-key identity |

## Gate results (this round)

- Offline gate: **GREEN — OFFLINE-QUALIFIED** (5 checks; python regression
  suite 234 passed, including the 12 new install-script tests).
- Package gate with `--build out/staged/o-v17a-shutter-fallback-off-20261012/FwPkt`:
  **GREEN 10/10**, including the new "install manifest present and current"
  check.

## Device-side state (blocked on hardware)

The host has no BT adapter (`/dev/hci0` absent, no `bluetoothctl`, no USB BT
dongle) and the Polaris AP at `192.168.0.1` is not up (TCP 9090/22 refused), so
the wake phase cannot run yet. Re-arm with:

```bash
cd BenroPolarisPatcher
env POLL_INTERVAL=45 POLL_LIMIT=80 bash scripts/o-v17a-autonomous-install.sh --poll
```

Once the device is reachable the script performs auth → stage (skipped if
already `.66`) → reboot (observed/uncertain) → verify against
`out/staged/o-v17a-shutter-fallback-off-20261012/install-manifest.json`.
