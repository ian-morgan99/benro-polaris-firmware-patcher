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

## Documentation obligations

Every upgrade issue must identify which of these need updating and update them before closure:

- `docs/canonical-pentax-source.md`
- `docs/TESTED.md`
- `docs/HOW-IT-WORKS.md`
- `docs/patcher-gates.md`
- `docs/RUN-JOURNAL.md`
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
