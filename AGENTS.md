# Firmware patcher agent instructions

These instructions apply to all automated or human-assisted work in this repository.

## HARD RULE — never build on device; deploy only by zip and flash

**Nothing is ever compiled, assembled, patched or installed on the Polaris head.** All builds happen
on the workstation. The only sanctioned way to change what runs on the head is:

```text
workstation build -> immutable zip/FwPkt (registered with hashes + commit links)
                  -> supported flash/install process
                  -> cold reboot
                  -> identity verification (release + component hashes)
```

Prohibited on the device, with no exceptions for "just a quick test":

- Compiling or assembling anything on the head. It has no `gcc`, `cc`, `clang`, `tcc` or `make`, and
  that absence is intentional — do not install a toolchain to work around it.
- Copying a locally built binary into `/app` (including `libpolaris_stage2.so`, any `ptp2.so`, or any
  `.so`) and restarting a service to pick it up. This includes `scripts/stage2-hotswap.sh push`.
- Relaunching `pgphoto` by hand with a modified environment (`STAGE2_*`, `LD_PRELOAD`, etc.) to
  enable a feature for an experiment. A manual relaunch bypasses the wrapper's pidfile, launch lock
  and crash-backoff, and the resulting process is not attributable to any build.
- Editing files under `/app` in place, including config/wrapper scripts.

Allowed on the device: **read-only diagnostics** — reading logs, `md5sum`, `strings`, `ls`,
`/proc/<pid>/environ`, and issuing camera commands over the control socket. Enabling a feature that
the *flashed* build already supports via a documented toggle is not permitted either unless it
survives a reboot; if a capability needs an env change, it belongs in the flashed wrapper and ships
in a zip.

### Why this rule exists — there is no read-only image to fall back to

**A reboot does NOT restore the device.** Verified on 2026-11-26:

```
ubi0:ubifs on /    type ubifs (rw,relatime)
ubi1:ubifs on /app type ubifs (rw,relatime)
```

Both are **writable UBIFS** and persist across reboot. Anything written under `/app` or `/` — a
swapped `.so`, an edited wrapper, a modified config — is still there after a reboot, forever, with no
marker saying it did not come from a flash. There is no A/B partition, no automatic fallback, and no
recovery mode that restores `/app`. The only recovery is **re-flashing a known-good packet**, which
takes 5–10 minutes, requires the device to still boot, and fails outright if the radio or the boot
path was damaged.

That is why building on device is prohibited: a bad binary written into `/app` can leave the camera
stack unable to start, and if it also breaks the network path there is no remote way to put it back.
The failure is not recoverable by rebooting.

### Patching must always be reversible — prove it before you flash

Before flashing anything, confirm a **verified restore packet for the currently installed release**
exists and is reachable:

1. Read the installed identity (`scripts/device-identity.py`) and the install receipt for that build.
2. Locate the exact zip that produced it and check its SHA-256 against `zip_sha256` in
   `install-receipt.txt`. A digest match is the only proof it is the packet that is running.
3. If no such packet exists, **stop** — flashing now makes the device unrecoverable to that state.
   Rebuild and archive the installed release first, or accept the loss explicitly with the operator.
4. Record the restore packet's path and digests in the evidence for the flash you are about to do.

Reversibility is a property of having the right bytes on hand, not of the flash process itself.
`docs/FIRMWARE-INSTALL-PROCESS.md` "Checklist for every install" carries the matching gate.

## Read `docs/WHO-DOES-WHAT.md` first

This project spans two repositories and the issue numbers are easy to mix up. If
you are unsure which repo, branch, or issue number something belongs to, read
`docs/WHO-DOES-WHAT.md`. In one line: **this repo is everything except the camera
library; `ian-morgan99/libgphoto2` is the C library that talks to cameras.**

Deciding rule for a new issue: does the fix require changing C code that talks to
the camera? Yes → driver repo (`#1xx`). No → this repo (`#2xx`). If a fix needs
both, it is tracked **here** and references the driver change. A firmware binary
change is never tracked as a driver issue — see libgphoto2 #145, closed 2026-11-05
and folded into this repo's #251.

## Two-agent working agreement

This project is worked by two agents with deliberately separated roles.

- **Development agent (you, in the coding session):** implements code, build, gate and
  packaging changes; writes and closes implementation issues; produces candidates.
- **Review/verification agent:** reads content periodically, audits assumptions against
  source, validates evidence and claims, and posts guidance. It does **not** perform
  development edits, and it does not restructure documents it did not author.

Rules that keep the two from standing on each other's toes:

- Guidance flows through **issues**, not silent edits into each other's work. The review
  agent files an issue with acceptance criteria; the development agent implements it and
  reports back in that issue. `#214` is the model.
- The review agent may edit its own verification artefacts
  (`docs/LIBGPHOTO2-ALIGNMENT-AUDIT.md`, evidence reviews). Treat those as **read-only**
  unless you are asked to change them; cite them, do not rewrite them.
- Do not edit files another agent has uncommitted changes in. Check `git status` before
  starting, and leave anything you did not author alone.
- A claim that something is *correct* is the review agent's to confirm; a claim that
  something *builds and passes the gate* is yours. Do not upgrade the second into the
  first in commit messages, issue comments or docs.

## Documented skills are the source of truth — do not improvise

Before doing any operation that a skill under `.github/skills/` covers, **read
that skill first and follow it exactly**. Open the corresponding SKILL.md
directly from the checkout in clients without native skill discovery. Do not invent an alternative approach
"as you go along" (e.g. hand-rolled chunked transfers, ad-hoc HTTP servers,
custom retry loops) when a documented, proven process exists.

- `polaris-release-orchestrator` — ONE front door for every build type. Phase
  state machine `BUILT → ARCHIVES_VERIFIED → DOCS_GENERATED → PRIVATE_PUBLISHED →
  REMOTE_VERIFIED`, plus `DEVICE_INSTALLED` and `HARDWARE_QUALIFIED`. Delegates
  to scripts; build success is not release success. Incorporates #356.
- `polaris-release-artifact-auditor` — checks required companion packages and
  digests from the exact PrivateResearch commit. Pair the local archive checker
  with the documented remote readback while #292/#350 are open.
- `polaris-release-documentation` — write and review the install, changelog,
  compatibility and recovery instructions against the exact build records.
- `polaris-release-reconciliation` — audits built candidates vs PrivateResearch
  index; detects missing/incomplete/mislabelled versions; produces version-by-version
  exception ledger. Backfills v110/v111.
- `polaris-regression-preservation-review` — for each PR affecting camera,
  firmware, Astro, Wi-Fi or installation: changed-component manifest,
  stock/previous-version feature diff, negative regression tests, explicit
  unverified hardware matrix.
- `fwpkt-update-flow` — the ONLY sanctioned way to stage/install firmware on a
  device (tar-stream the extracted tree, on-device MD5 verify, `/sbin/reboot`).
  Device installation only (`DEVICE_INSTALLED`), not publication.
- `fwpkt-private-upload` — uploads `FwPkt.zip` to PrivateResearch
  (`PRIVATE_PUBLISHED` phase only). Does NOT treat FwPkt-only upload as a
  sufficient release definition.
- `polaris-debugging` — SSH access, gimbal-vs-router diagnosis, keepalives.
- `polaris-evidence-discipline` — who owns a defect and what counts as proof.
  Requires the authoritative-source lookup (`scripts/find-authoritative-source.py`)
  before any "not our code" / "vendor limitation" claim, requires the producing
  code to be cited for every mechanism claim, and pins three verification states
  (`logic-tested` / `device-installed` / `hardware-qualified`) so a host-side test
  is never recorded as a hardware fix.
- `polaris-release` — legacy routing guide; delegates to
  `polaris-release-orchestrator`. Does not define a competing lifecycle.
- `astro-multishot-qualification` — deterministic repeated Pentax capture
  qualification on physical hardware.
- `pentax-hardware-stability` — Pentax K-3 III / K-1 II stability investigations.
- `conversation-review` — audit of agent-work process and ledgers.

Before any candidate build, run `scripts/build-doctor.sh`. It takes seconds and
proves each build prerequisite actually *works* rather than merely existing —
Docker reachable *and* able to bind-mount our files, ubireader that runs, a
self-contained libgphoto2 clone at a reachable pin. Building astro-v97 took six
failed attempts because six prerequisites passed existence checks and failed
anyway, each reporting itself as an unrelated problem. Use
`scripts/build-astro.sh --version N --summary FILE` for Astro candidates; it runs
the doctor, provisions what it can inside the repo, and refuses to build rather
than producing something misleading. The full message-to-cause table is in
`docs/REPRODUCIBLE-BUILD-RUNBOOK.md`.

If a documented process fails, diagnose *why* (link drop? device state?) and
retry the documented process or fall back to its documented fallbacks. Only
deviate when the skill explicitly allows it, and record the deviation in the
evidence/registry so the next agent knows. Improvised one-offs that work are a
trap: they hide the real failure mode and get repeated with new bugs.

## Mandatory libgphoto2 upgrade contract

Before changing any packaged libgphoto2 component, read and follow `docs/LIBGPHOTO2-UPGRADE-PROCESS.md`.

Before installing any candidate on the device, read and follow
`docs/FIRMWARE-INSTALL-PROCESS.md`. The only supported install path is
`scripts/release/release-fwpkt.sh <build-dir>`: it stages the extracted `FwPkt/`
tree (the on-boot watcher ignores a bare zip — issue #58), verifies every
`firmwareInfo` MD5 on-device, reboots, proves the boot was real by an uptime reset,
and fail-closes on build_id plus every mandatory file digest. Never copy files into
`/app` as an install, and never treat a vanished SSH as a reboot.

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

### Assumptions that must be re-verified, not carried over

`docs/LIBGPHOTO2-ALIGNMENT-AUDIT.md` records every assumption this repository makes about
upstream and the evidence that each one held at the last check. On any version bump or
upstream rebase, re-verify rather than assume:

- the version-pin surface — `container/patch.sh` (`LIBGPHOTO2_VERSION`),
  `container/stage2_loader.c` (`STAGE2_CAMLIBS_DIR`, `STAGE2_IOLIBS_DIR`) and
  `scripts/generate-fwpkt-manifest.py` (mandatory `lib/stage2/...` paths). The
  `configure.ac` version guard covers **only** the requested version; leaving the loader
  or manifest behind builds and gates GREEN and ships a stale module directory.
- the three out-of-tree `sed` anchors in `container/build_ptp2.sh`. Two of them fail
  **silently** — a moved anchor ships unpatched behaviour with a green build.
- the `_Camera` pad target and its `awk` anchor, the loader's ABI constants
  (`GP_WIDGET_TEXT`, `CameraAbilities.model[128]`), the exported-symbol assumption that
  removes the trampoline shim, and the name of the upstream test suite the gate skips.

### Gate GREEN does not mean the shipped configuration was tested

The gate runs upstream's tests with **meson** (`-Dcamlibs=ptp2,pentax,directory`); the
shipped libraries are built with **autotools** (`--with-camlibs="ptp2,pentax"
--without-libxml-2.0 --without-jpeg --without-libcurl`). Different build system,
different dependency graph. Never justify a link-time or dependency decision by pointing
at a passing gate — check the shipped artifact (`readelf -d`, `nm -D
--undefined-only`). Tracked in `#214`.

### Attribute telemetry to its actual source before reasoning about it

Autonomous work has twice misattributed battery evidence, and both times the error
survived into issues and tooling. Verify provenance from the log line that *produces*
the value, not from a docstring or a summary sentence.

- **Wire code 778 is the GIMBAL battery.** Mlog shows its producer directly:
  `GimbalUartRxMsgProcTask[378]:Voltage:12.16;capacity:97;ChargeState:1;` followed by
  `SP_SendMsgToApp ... code[778]`. The voltages (10.7–12.4 V) are a gimbal pack, not a
  Pentax D-LI (~7.4–8.4 V). Clog — the pgphoto/libgphoto2 side — never emits 778.
- **The CAMERA battery is `/main/status/batterylevel`**, read through the existing PTP
  owner (see `docs/evidence/o-v13v-stage2-direct-20260929/`). Do not open a second
  gphoto2 client to poll it — that contends with pgphoto's session ownership (#206 B1/B2).
- `docs/evidence/battery-log.csv` contains **gimbal** rows only. It is not camera-battery
  evidence, and there is currently no recorded camera-battery telemetry anywhere in the
  repo.

The standing correction: **the camera battery has been a consistent problem; we have never
had a specific gimbal-battery problem.** #119, closed #66 and the idle-drain report filed
under #147 are all *camera*-side observations, despite #119's wording ("the Polaris battery
drains very fast while the camera is connected") being read as gimbal-side for weeks. When
citing prior power evidence, say which battery it measured and quote the producing log line.

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
  `firmware-packets/<display-version>--<registry-id>/` in the same session it is built — see the
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
   - Arm the 9090 keepalive for **every** session that touches the device, not
     just long live gates (see "Wake and keep-alive" below); stop it before
     rebooting. The wording here used to scope it to long gates only, which is
     what let the v107 deploy lose the radio mid-session (issue #339): a deploy
     is many short SSH commands, none individually long.

## Wake and keep-alive (Polaris) — exact commands

**Standing rule: the keepalive runs in the background for every session that talks
to a Polaris, from before the first SSH command until the work is verified.** Not
optional, and not scoped to long jobs. Bursty one-shot SSH is actively harmful —
each short-lived session ends with a client leaving, and once the radio is down
nothing host-side can bring it back (see `docs/FIRMWARE-INSTALL-PROCESS.md`, "Arm
the keepalive before touching the device").

```sh
nohup scripts/polaris-bt-keepalive.sh > /tmp/polaris-bt-keepalive.out 2>&1 &
tail -f /tmp/polaris-bt-keepalive.log     # wait for phase=ssh-up
```

Read the terminal `phase=` value, never a vague success: `ssh-up`,
`joined-ssh-down`, `not-advertising`, `connect-aborted`, `ap-not-visible`,
`control-up`.

- **Wake — corrected.** `bluetoothctl connect 48:E7:DA:D4:B5:72` is *documented* as
the wake pulse, but it cannot be delivered from Linux: the rig never advertises LE
(`SP_BlueSetAdvertiseState: advertise on` / `Failed to register advertising object`
on every boot), so there is nothing to connect to. Verified again 2026-11-12 outside
the sandbox — adapter present, receives other devices, target `not available`. See
`docs/evidence/rig-le-advertising-absent-20261027/SUMMARY.md`. Treat
`phase=not-advertising` as **needs a physical power cycle**, not a host-side bug.
- **Keep alive:** idle timeout is ~5 min of no TCP traffic on 9090. Polling 284/822
does **not** reset it. For any job longer than a few minutes run:

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
- `docs/LIBGPHOTO2-ALIGNMENT-AUDIT.md` (re-verify and update the dated evidence when an
  assumption is checked or a version is bumped — owned by the review agent)
- `docs/FWPKT-PROVENANCE-CONTRACT.md` (registry row for any new/received FwPkt zip)
- `docs/FIRMWARE-INSTALL-PROCESS.md` (the single supported install path; update it if
  the installer's phases, gates, or failure modes change)
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

- **SD card is 1 GB or larger — standing assumption.** Assume this for every install,
  instruction and test from now on; do not design around smaller cards. All four SD
  payloads together are ~162 MB (~175 MB after FAT32 cluster rounding), so they fit a
  1 GB card at once and the manual route should say "extract all four, then reboot".
  Never quote `docs/FIRMWARE-INSTALL-PROCESS.md`'s "118 MB filesystem" as the head's
  capacity — that figure is one small test card observed while demonstrating the
  truncation failure mode, not a property of the device. Where capacity genuinely
  matters, read `df -k /app/sd`.
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
- **Wake/keepalive:** run `scripts/polaris-bt-keepalive.sh` in the background for
  every Polaris session. BT connect to `48:E7:DA:D4:B5:72` is *documented* as the
  wake pulse but is undeliverable from Linux — the rig never advertises LE, so a
  dead radio needs a physical power cycle. Keep jobs alive with the 9090 ping loop
  (`1&266&0&#` every 30 s). Details in the skill.

## Canonical workspaces and handover convergence

Delivery checkouts are `BenroPolarisPatcher` on `main`,
`LibGphoto2/libgphoto2` on `main`, and `OpenPolaris` on `main`, all under
`/home/ian/Documents/VSCodeProjects`. The `LibGphoto2` parent is a historical
research corpus, not a library build or release source.

A temporary branch/worktree is an implementation or immutable build input,
not the delivered result. Before handover, reconcile applicable changes and
evidence onto the owning canonical branch, verify local/remote commit identity,
and retire temporary worktrees. Preserve unique history and dirty/ignored files
with verified hashes in PrivateResearch before retirement. Do not merge closed,
rejected, or obsolete experimental behavior simply to make branch counts zero.
Record its disposition and recovery location instead. Immutable exact-SHA test
installs belong under ignored `_baselines/`, not additional active source forks.
Any necessary active exception must identify its owner, purpose, exact SHA,
and concrete convergence action in the handover. See
`docs/WORKSPACE-CONVERGENCE-20260930.md` for this cleanup and recovery inventory.
