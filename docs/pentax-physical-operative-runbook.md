# Pentax stability: agent + physical operative runbook

## Purpose

The coding/testing agent controls the experiment. The human physical operative supplies the physical action that software cannot perform: moving the USB cable/camera between the **test PC** and the **Benro Polaris**, powering/toggling the camera when instructed, and reporting visible camera/Polaris state.

The agent MUST actively steer the operative. It must never silently assume which host the camera is attached to.

## Absolute rule: one USB host at a time

The camera must be connected to **exactly one** test host for an experiment:

- `PC` for Layer A/B tests; or
- `POLARIS` for Layer C tests.

Never connect, switch, power-cycle, or change USB Compatibility while a capture is active unless the current experiment explicitly calls for destructive fault injection.

Before every run, the agent must establish and log `ATTACHMENT=PC` or `ATTACHMENT=POLARIS` from observable enumeration, not merely from the operative saying it was moved.

## Layer model

### Layer A — PC + camera, direct libgphoto2 control

Physical topology:

```text
Pentax K-3 III/K-1 II -> USB -> test PC -> direct gphoto2/libgphoto2 test path
```

Use Layer A for camera/Pentax-driver semantics without Polaris variables:

- candidate discovery/reconciliation;
- JPEG vs DNG+JPEG output semantics;
- back-to-back captures;
- 95/99/100/101/105 s boundary characterisation where applicable;
- long exposure and NR;
- Pixel Shift where supported/configured;
- command-concurrency experiments supported by the direct harness;
- overlapping shutter rejection/behaviour;
- session lifecycle;
- direct-driver soak.

Layer A is the preferred first location for any experiment that does not require pgphoto/Polaris behaviour.

### Layer B — PC + camera, Benro/pgphoto-compatible harness

Physical topology remains:

```text
Pentax -> USB -> test PC
```

but the software path should reproduce the relevant Benro/pgphoto command sequencing/state machine as faithfully as practical.

Use Layer B to answer: **does the failure appear when Benro integration semantics are introduced even though the camera is still on a normal PC USB/runtime environment?**

Layer B should reproduce, where possible:

- command 264/capture sequencing;
- candidate ownership/finalisation behaviour;
- preview/capture sequencing;
- deterministic command serialization/queue/reject policy;
- session open/close/reinit semantics;
- pgphoto-equivalent completion semantics.

Do not pretend Layer B is equivalent to Polaris if a component cannot actually be reproduced. Record those gaps.

### Layer C — real Polaris + camera

Physical topology:

```text
Pentax -> USB -> Benro Polaris -> real pgphoto/staged libgphoto2/firmware/runtime
```

Use Layer C for:

- confirmation of failures/fixes found at A/B;
- real pgphoto process/watchdog behaviour;
- camera_usb_supervisor behaviour;
- actual embedded USB controller/runtime;
- firmware packaging/runtime-loader interactions;
- 8080 preview path;
- Broadcom Wi-Fi/resource pressure;
- Benro Connect/OpenPolaris end-to-end qualification;
- Polaris-only process/resource soak;
- real reset/recovery behaviour.

## Required agent/operative protocol

The agent must use an explicit handshake before changing host.

### Move camera to PC

Agent tells operative:

> **PHYSICAL ACTION REQUIRED — attach camera to PC.** Ensure no capture is active. Disconnect the camera USB cable from Polaris. Connect the camera by USB to the test PC. Leave the Polaris alone. Turn the camera on if required. Do not start Benro Connect/OpenPolaris. Tell me when complete.

After the operative confirms, the agent MUST verify from the PC that the expected Pentax VID:PID/model is actually enumerated. If it is not visible, STOP and diagnose; do not run the experiment.

Then log:

```text
ATTACHMENT=PC
CAMERA=<model>
USB=<observed identity>
LAYER=A|B
```

### Move camera to Polaris

Agent first stops/closes all PC camera processes and verifies the PC no longer owns/claims the camera. Then tells operative:

> **PHYSICAL ACTION REQUIRED — attach camera to Polaris.** Ensure no capture is active. Disconnect the camera USB cable from the PC. Connect it to the Polaris camera USB path. Turn the camera on if required. Do not open Benro Connect/OpenPolaris until I ask. Tell me when complete.

After confirmation, the agent MUST verify on Polaris/current logs that the expected Pentax body is newly/currently enumerated. Do not accept a cached model name or stale `usb:BUS,DEVICE` as proof.

Then log:

```text
ATTACHMENT=POLARIS
CAMERA=<model>
USB=<current observed identity>
LAYER=C
```

## Agent decision tree

For each scenario:

```text
Can the hypothesis be exercised with direct libgphoto2?
  YES -> ask operative for PC attachment -> run Layer A.
           |
           +-- FAILS -> reproduce/minimise at A; likely camera/Pentax-driver family.
           |           Do not move to Polaris merely to collect another crash.
           |
           +-- PASSES -> can Benro/pgphoto sequencing be reproduced on PC?
                         YES -> run Layer B without moving cable.
                                  |
                                  +-- FAILS -> integration/command-lifecycle family.
                                  |
                                  +-- PASSES -> move to Polaris and run Layer C.
                         NO -> record B gap -> move to Polaris and run Layer C.

Requires Polaris-specific runtime/USB/Wi-Fi/watchdog behaviour?
  YES -> ask operative for Polaris attachment -> run Layer C.
```

The purpose of moving the camera is **layer isolation**, not ritual repetition.

## Minimising physical cable moves

Batch tests by attachment where safe. The agent should prepare a queue such as:

```text
PC SESSION — K-3 III
  A/E4 candidate lifecycle
  A/E5 DNG+JPEG permutations
  A/E1 timeout boundaries
  A/E6 long exposure/NR
  A/E13 overlapping shutter
  B equivalents for cases that passed A

then one physical move

POLARIS SESSION — K-3 III
  C confirmation of A/B differences
  C preview/pgphoto/watchdog tests
  C soak/recovery tests
```

Do not ask the operative to move the cable after every individual test when a coherent batch can be completed on the same host.

K-1 II is a second-pass campaign and should use the same batching strategy after K-3 III causal discovery.

## Before any capture batch

Agent records:

- body and camera firmware;
- host attachment and layer;
- exact libgphoto2 SHA/binary provenance;
- patcher/firmware SHA/build where relevant;
- image format;
- exposure mode;
- NR;
- Pixel Shift;
- shutter;
- preview state;
- relevant process PIDs;
- USB identity;
- run IDs/output trace path.

For A/B, ensure Benro Connect and OpenPolaris are absent unless the experiment specifically needs an upper-layer consumer. For C, preview remains OFF for baseline until explicitly enabled by the experiment.

## After each run

The agent, not the operative, decides PASS/FAIL from evidence. The operative may report physical observations such as LCD busy indication, shutter actuation, LEDs or need for power-cycle, but these observations are recorded as evidence rather than substituted for trace state.

The agent records the first abnormal event and decides whether to:

- repeat on same layer;
- minimise the reproducer;
- progress A -> B -> C;
- stop because cause is already isolated;
- request a physical recovery action.

## Physical recovery requests

Recovery must also be explicit. Examples:

> **PHYSICAL ACTION REQUIRED — camera power-cycle only.** Do not move the USB cable and do not restart Polaris. Turn the camera off, wait until fully off, turn it back on, then tell me when complete.

> **PHYSICAL ACTION REQUIRED — USB reconnect only.** Camera is not exposing. Leave camera powered on. Disconnect/reconnect the camera USB at the current host only. Do not power-cycle anything else.

This separation is important: combining camera power-cycle + USB reconnect + Polaris reboot destroys evidence about which action actually recovered the system.

## Destructive experiments

E7/E8/E9 and equivalent fault-injection tests require the agent to announce that the next run is intentionally disruptive and state exactly what the operative should do and **when**.

Never ask the operative to guess exposure completion. The agent must provide the trigger, e.g.:

> When I say **DISCONNECT NOW**, remove only the camera USB from the current host. Do not turn the camera off.

The agent must confirm the experiment is armed before issuing that trigger.

## Cross-body sequence

### K-3 III — Pass 1

1. PC Layer A discovery batch.
2. PC Layer B integration batch for A-clean hypotheses.
3. Move once to Polaris for Layer C differential/embedded tests.
4. Repeat/minimise only where evidence requires it.

### K-1 II — Pass 2

1. Move K-1 II to PC and run the high-information Layer A subset.
2. Run Layer B without moving cable where applicable.
3. Move K-1 II to Polaris for Layer C comparison.
4. Expand only experiment families where K-1 II differs or where a generic-Pentax fix requires validation.

Do not assume a K-3 III result is generic until the relevant K-1 II invariant is demonstrated.

## Required result attribution

Every result must contain:

```text
CAMERA=K-3 III|K-1 II
ATTACHMENT=PC|POLARIS
LAYER=A|B|C
PATH=<actual software path>
```

Without these four fields, a result is not sufficient evidence for layer attribution.

## Key principle

The agent owns **experiment design, sequencing, verification and interpretation**. The physical operative owns **physical manipulation on explicit instruction**. Neither should infer what the other has done.

Always verify attachment in software after a physical move. Always isolate the earliest layer that reproduces the fault. Only move upward to Polaris when the lower layer passes or when the hypothesis is inherently Polaris-specific.
