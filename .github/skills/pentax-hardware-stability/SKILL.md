---
name: pentax-hardware-stability
description: Direct deterministic Pentax K-3 III and K-1 II stability investigations across host libgphoto2, Polaris runtime, and OpenPolaris without conflating recovery, timeouts, or repository ownership. Use for physical camera failures, long captures, reconnects, preview, or release qualification.
---

# Pentax hardware stability

You are the test director; the human is the physical operative. Give one exact
physical instruction, wait for confirmation, then independently verify the
new state in software. Use `docs/pentax-agent-operative-prompts.md`.

Read these before acting:

- `.github/skills/polaris-debugging/SKILL.md` for device identity and SSH;
- `.github/skills/fwpkt-update-flow/SKILL.md` before any install;
- `docs/pentax-mode-aware-liveness.md` for long-operation semantics;
- `docs/LIBGPHOTO2-UPGRADE-PROCESS.md` before changing packaged libgphoto2.

## Release integrity

Never build or stage from an uncommitted patcher tree. Record the stock FwPkt
hashes, exact patcher and libgphoto2 commits, build parameters, artifact hashes,
and generated wrapper. Run package and `firmwareInfo` gates against the actual
zip. Inspect the extracted appfs and verify the intended `CAMLIBS`, `IOLIBS`,
`LD_LIBRARY_PATH`, `LD_PRELOAD`, and preview policy. Upload and register the
artifact before handoff. Source tests, QEMU, or file presence do not prove the
runtime loader or physical camera.

## Choose the lowest reproducing layer

```text
A: exact libgphoto2 SHA + camera directly attached to the PC
B: exact packaged stack + camera on Polaris, OpenPolaris absent
C: OpenPolaris end to end with the same packaged stack and camera
```

Route ownership by the first divergence:

```text
A fails before valid ownership, session or trace -> setup/session diagnosis
A reproduces the same failing lower-layer operation -> candidate libgphoto2 defect
A passes, B fails               -> patcher / pgphoto / Stage-2 / loader
A and B pass, C fails           -> OpenPolaris
```

Do not change libgphoto2 for a Polaris-only symptom. Compare the first PTP
operation or state transition and prove which library, camlib and port module were loaded. Use the libgphoto2 AGENTS.md, IMAGE Transmitter 2 matrix and settings path as the source gates.

For setting writes, single-thread the client, choose one advertised value and use the
body-specific IT2 conditions path. An acknowledgement, app slider or descriptor
snapshot can lag or misreport application. Require a changed live readback, exact
restoration and a fresh-session check. Record preserved baseline separately from
restoration after a change. Treat preview-off and preview-on as paired trials.

## Physical moves and evidence

Batch Layer A/B work to minimise cable moves. After every move record:

```text
CAMERA=K-3 III|K-1 II
ATTACHMENT=PC|POLARIS
LAYER=A|B|C
PATH=<actual software path>
USB=<freshly observed identity>
```

A cached model or stale USB path is not proof. Stop if current enumeration does
not match. Preserve this causal chain:

```text
trigger -> first incorrect transition -> contaminated state -> visible symptom -> recovery
```

Change one recovery variable at a time: camera power, USB reconnect, USB mode,
pgphoto restart, or Polaris reboot. For disconnect injection, arm collection
first and tell the operative exactly when to disconnect.

## Long operations and candidate safety

Physical exposures, camera processing, output files, and tether candidates are
different signals. Requested shutter/mode and elapsed time are expectations,
not proof of completion. Do not assume a fixed Pixel Shift candidate count or
declare a long Astro capture dead while authoritative activity continues.

Never delete an unknown RAW/DNG or transfer candidate to clear state. Establish
ownership and preserve camera-side files. An ambiguous result is `OUTCOME
UNKNOWN`; stop before another shutter or destructive recovery.

For repeated or Astro capture, also follow
`.github/skills/astro-multishot-qualification/SKILL.md`.

## Qualification and reporting

Before camera claims, prove the installed provenance, wrapper, active process,
listeners, environment, `/proc/<pid>/maps`, matched Stage-2/core/port hashes,
and absence of loader/symbol/iolib errors. For the current Pentax programme,
qualify K-3 III and K-1 II on the exact build. Carry forward the applicable
previous camera matrix and representative non-Pentax coverage for shared paths.
Keep earlier results bound to the build that produced them. Mark absent hardware
unverified on this candidate.

Report `PASS`, `FAIL`, or `OUTCOME UNKNOWN` per layer and camera. Include exact
commits/artifact hashes, commands, UTC times, raw evidence paths, first
divergence, and recovery. A harness pass is not physical support.
