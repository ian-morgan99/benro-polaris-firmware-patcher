# Firmware patcher agent instructions

These instructions apply to all automated or human-assisted work in this repository.

## Documented skills are the source of truth — do not improvise

Before doing any operation that a skill under `.github/skills/` covers, **read
that skill first and follow it exactly**. Do not invent an alternative approach
"as you go along" (e.g. hand-rolled chunked transfers, ad-hoc HTTP servers,
custom retry loops) when a documented, proven process exists.

- `fwpkt-update-flow` — the ONLY sanctioned way to stage/install firmware on a
  device (tar-stream the extracted tree, on-device MD5 verify, `/sbin/reboot`).
- `fwpkt-private-upload` — publish every built zip to PrivateResearch in the
  same session it is built.
- `polaris-debugging` — SSH access, gimbal-vs-router diagnosis, keepalives.

If a documented process fails, diagnose *why* (link drop? device state?) and
retry the documented process or fall back to its documented fallbacks. Only
deviate when the skill explicitly allows it, and record the deviation in the
evidence/registry so the next agent knows. Improvised one-offs that work are a
trap: they hide the real failure mode and get repeated with new bugs.

## Mandatory libgphoto2 upgrade contract

Before changing any packaged libgphoto2 component, read and follow `docs/LIBGPHOTO2-UPGRADE-PROCESS.md`.

A libgphoto2 upgrade is a **matched-stack change**, not a camlib-only change. The load-bearing set includes:

- `/app/bin/pgphoto` wrapper/launcher;
- `pgphoto.stage2ondisk`;
- `libpolaris_stage2.so`;
- `libgphoto2.so.6`;
- `libgphoto2_port.so.12`;
- `ptp2.so`;
- `usb1.so`;
- every active camlib/iolib lookup path;
- the wrapper environment and ABI/symbol assumptions.

Do not conclude an upgrade is correct because `ptp2.so` builds, QEMU passes, or direct `gphoto2` works.

## Source/runtime ownership rule

When a camera operation fails:

```text
direct exact libgphoto2 SHA + directly attached camera FAIL
  -> candidate libgphoto2 issue

direct PASS + Polaris-local FAIL
  -> patcher / pgphoto / Stage-2 / loader / path / session issue

direct PASS + Polaris-local PASS + OpenPolaris FAIL
  -> OpenPolaris issue
```

Compare the first divergent lower-level PTP operation/state transition, not just final GP error numbers.

Do not make a libgphoto2 change to fix a Polaris-only symptom without a direct source-repo reproducer.

## No direct runtime mutation as a release fix

Do not replace camera-stack binaries directly under `/app` over SSH as a supported fix. Release-qualified changes must flow:

```text
source change
 -> clean patcher build
 -> architecture/ABI/provenance gates
 -> immutable FwPkt + manifest
 -> supported firmware install
 -> cold reboot
 -> runtime-loader proof
 -> physical camera regression matrix
```

SSH is read-only diagnostic by default. A temporary explicitly authorised experiment invalidates qualification evidence until a canonical FwPkt is reinstalled.

## FwPkt provenance contract (cross-repo, cross-agent)

Every FwPkt artifact — no matter which repo (`BenroPolarisPatcher`, `OpenPolaris`,
the libgphoto2 fork) or which agent session produced it — must be traceable by
**commit links + hashes**, per `docs/FWPKT-PROVENANCE-CONTRACT.md`:

- **Record before handoff.** The moment a zip is built, received, or copied to
  another machine/card/repo, add (or update) its row in the registry table in
  `docs/FWPKT-PROVENANCE-CONTRACT.md` with: zip MD5 + SHA-256, payload appfs MD5,
  libgphoto2 source commit SHA, and patcher commit/branch. Recompute hashes from
  the actual file; never copy them forward from a doc.
- **Handoff passes four things:** registry id, zip MD5+SHA-256, appfs MD5, and
  both commit links. The receiver verifies all of them before staging on a device.
  A zip with no matching registry row is *unprovenanced* — do not stage it.
- **Zips stay out of public git.** Zip bytes live in `builds/`, `out/`, the SMB
  share, or the SD card; only the registry row (hashes + commit links) is
  committed. The private zip location now exists: every built zip is uploaded to
  the **private** `ian-morgan99/PrivateResearch` repo under
  `firmware-packets/<registry-id>/` in the same session it is built — see the
  `fwpkt-private-upload` skill (`.github/skills/fwpkt-private-upload/SKILL.md`)
  and its script. The registry row's location column points there; other agents
  fetch the bytes from that repo and verify all four handoff values before
  staging.

## Regression protection

Every libgphoto2 upgrade must rerun all previously physically qualified cameras. Never optimise only for the camera that motivated the upgrade.

At minimum preserve the known-good Canon R5 Mark II path from the Blaine upstream architecture and the Pentax K-3 III / K-1 II paths as they become qualified.

If required hardware is unavailable, mark the candidate unqualified for that camera; do not silently downgrade a previous PASS to untested.

## Pre-release gate (mandatory, coded — no AI interpretation)

Anything we believe is currently working MUST have a coded regression test, and every release candidate passes the deterministic gate before it may be staged or declared ready. The gate is a script; its output is the evidence. Do not substitute narrative judgement for a red gate.

1. **Run the gate** (from repo root):
   - Offline (always, before any claim of readiness): `./tests/run_prerelease_gate.sh`
   - With a built package (before SD-card staging / install): `./tests/run_prerelease_gate.sh --build out/<candidate>/FwPkt`
   - Live device gates (camera ON and attached; see canary rule below): `./tests/run_prerelease_gate.sh --canary [--two-shot]`
2. **Gate policy.** Fail-closed: any runnable check that fails = RED, do not stage/install. Missing prerequisites report SKIP (never silent green); record skips in the release evidence. Exit 0 = green, 1 = red, 2 = usage error.
3. **Regression-test rule.** When a fix is verified working (by any means), add or extend a coded test that would have caught the regression, and wire it into the gate:
   - container/patcher behaviour → `container/test_*.sh` (picked up by `tests/run_deterministic.sh`; exit 2/77 = prerequisite skip)
   - scenario/routing/trace/contract invariants → `tests/test_*.py` (pytest, picked up by the gate's python suite)
   - live capture behaviour → `scripts/canary-probe.py` / `canary-two-shot.py` (run via the gate's `--canary` / `--two-shot`)

   A fix that cannot be expressed as a coded test must say so explicitly in the release evidence, with the reason.
4. **What can be tested WITHOUT a firmware zip installed** (offline gate):
   - `tests/run_deterministic.sh` — patch/patcher behaviour against fixtures (stage2 gates, fail-closed manifest gate, wrapper locks, settle window)
   - pytest suite — scenario routing, stability catalogue invariants, trace tooling, astro multi-shot command contract
   - `container/validate_fw_package.py` + `verify_firmwareinfo.py` on a built package (layout, duplicates, stock SHA-256 cross-check, firmwareInfo manifest self-consistency vs the stock manifest)

   These prove the *package and its invariants*; only the live gates prove the device.
5. **Canary rule (camera on or off at deployment).** The canary is a single bounded capture proving the installed build actually captures:
   - Camera **ON** (attached, powered, SD present): run `./tests/run_prerelease_gate.sh --canary` — probe reads camera state, then one shot must show lifecycle completion (`[1,4,…]`) plus a 773 file event. Add `--two-shot` when the evidence standard is two distinct files (fail-closed; no further shutter after a failed shot).
   - Camera **OFF** at deployment: the live gates SKIP (probe fails to reach a camera-ready state) — that is recorded, not a failure. The canary is owed as soon as the camera is attached; until then the candidate is "installed, canary pending", never "qualified".
   - Keep the 9090 keepalive running during any multi-minute live gate (see wake/keep-alive below); stop it before rebooting.

## Wake and keep-alive (Polaris) — exact commands

- **Wake:** gimbal must be powered on; BT connect to `48:E7:DA:D4:B5:72` is the wake pulse. If Wi-Fi/SSH is down, use `scripts/polaris-bt-keepalive.sh` (independent BT link + SSH reach path).
- **Keep alive:** idle timeout is ~5 min of no TCP traffic on 9090. For any job longer than a few minutes run:

  ```sh
  while :; do printf '1&266&0&#' | timeout 4 nc -q1 192.168.0.1 9090 >/dev/null 2>&1; sleep 30; done &
  ```

  and kill it before rebooting. `val[-100]` on 266/284/286 = keepalive/no-data.
- **Identity first:** never trust a session until (a) real `polaris_*` AP association (`nmcli … | grep 48:E7:DA`), (b) `ip route get 192.168.0.1` via the wifi dev, and (c) `cat /app/FwVer` over SSH. Pingability alone proves nothing (the home cable router shares 192.168.0.1).

## Pushing a fix and testing it (locked-down flow)

1. Fix lands in the owning repo (issue → repo routing per the debugging skill), never as a direct `/app` mutation on the device.
2. Build the FwPkt (`container/build_fullstack.sh` / `patch.sh` flow), then run the gate: `./tests/run_prerelease_gate.sh --build out/<candidate>/FwPkt`.
3. Stage to SD card and install via the on-board updater (fwpkt-update-flow skill). The on-board crcInfo gate re-MD5s only what firmwareInfo claims — the manifest gate in step 2 is what catches silent no-op installs.
4. Run the canary per the canary rule above (camera ON → `--canary`/`--two-shot`; camera OFF → record "canary pending").
5. Commit evidence: gate transcript + canary/two-shot transcripts into `docs/evidence/<candidate>/` (transcripts as `.txt`), update `docs/CURRENT-STATE.md`, and close the issue with the gate output quoted.

## Documentation obligations

Every upgrade issue must identify which of these need updating and update them before closure:

- `docs/canonical-pentax-source.md`
- `docs/TESTED.md`
- `docs/HOW-IT-WORKS.md`
- `docs/patcher-gates.md`
- `docs/CURRENT-STATE.md` and the current candidate's bounded `SUMMARY.md`
- `docs/LIBGPHOTO2-UPGRADE-PROCESS.md`
- `docs/FWPKT-PROVENANCE-CONTRACT.md` (registry row for any new/received FwPkt zip)
- README supported/qualification claims
- libgphoto2 direct-hardware matrix
- OpenPolaris E2E matrix

Keep direct libgphoto2 evidence separate from Polaris runtime and OpenPolaris E2E evidence.

## Project memory — Polaris debugging (junior-agent onboarding)

The full operational debugging guide lives in
`.github/skills/polaris-debugging/SKILL.md` (SSH access, gimbal-vs-router
identity checks, on-device pgphoto/gphoto2 testing, log reading/download,
Bluetooth wake + wireless connect incl. sandbox, repo routing). Read it before
touching the live device. Load-bearing rules, restated:

- **Identity first.** `192.168.0.1` is shared with the home cable router. Never
  trust a session until you have (a) a real `polaris_*` AP association
  (`nmcli … | grep 48:E7:DA`), (b) `ip route get 192.168.0.1` via the wifi dev,
  and (c) `cat /app/FwVer` over SSH. Pingability alone proves nothing.
- **SSH is read-only diagnostic.** No direct code/binary changes under `/app`
  as a supported fix; everything flows issue → owning repo → FwPkt build →
  SD-card install (see `fwpkt-update-flow` skill).
- **On-device camera test = direct CLI, not the daemon.** Stop pgphoto, run
  `/app/bin/gphoto2` with `CAMLIBS`/`IOLIBS`/`LD_LIBRARY_PATH` from
  `/app/lib/stage2`, then restart the daemon and tail `/app/Clog.txt`.
- **Dual-path (#38) check on every flashed build:**
  `md5sum /app/lib/stage2/libgphoto2.so.6 /app/lib/libgphoto2.so.6` must match,
  and `/proc/<pgphoto>/maps` must show which core is actually loaded. Symptom
  signature: `No iolibs found in '../lib/libgphoto2_port/0.12.0'` +
  `sp_Gphoto_Init ret -2` + `state:-2`.
- **Repo routing (log the issue where the first divergence happens):**
  direct libgphoto2 SHA fails → `ian-morgan99/libgphoto2`; direct passes but
  packaged Stage-2/pgphoto path fails → this repo; both pass but app fails →
  `ian-morgan99/OpenPolaris`; evidenced defects may be modelled in
  `BenroHardwareValidator/benro-polaris-test-harness` (harness PASS ≠ physical
  support).
- **Wake/keepalive:** BT connect to `48:E7:DA:D4:B5:72` is the wake pulse
  (gimbal must be powered on); keep long jobs alive with the 9090 ping loop
  (`1&266&0&#` every 30 s). Details in the skill.
