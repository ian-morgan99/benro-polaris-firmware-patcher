# Pentax Hardware Stability Agent Skill

## Goal

Create a dedicated agent skill for the Pentax/Polaris hardware stability campaign so every coding/testing agent follows the same deterministic laboratory procedure when working with the physical K-3 III, K-1 II, test PC and Benro Polaris.

This should be a **small, prescriptive operating skill**, not another copy of the detailed experiment documentation. The skill should point to the existing runbooks/specifications and enforce how an agent uses them.

Cross-reference: #82 is the field-stability umbrella.

## Why this is needed

The investigation now deliberately isolates failures across three layers:

- **Layer A — PC + real camera + direct libgphoto2/gphoto2**
- **Layer B — PC + real camera + Benro/pgphoto-compatible harness**
- **Layer C — real Polaris + real camera + embedded pgphoto/staged libgphoto2/runtime**

The human at the bench is the **physical operative**, not the test director. Agents must not leave the operative to decide which host the camera belongs on, when to move it, which recovery action to try, or when a long exposure/processing phase has completed.

Without a reusable skill, a new agent can easily skip the PC isolation stages, jump directly to Polaris, conflate recovery with root cause, combine several physical recovery actions, or trust stale camera/USB state after a cable move.

## Proposed skill

Add a repository-local skill using the convention supported by the agent environment, e.g. a `SKILL.md` under an appropriate `.github/skills/...` location if that is the supported mechanism.

Before choosing the final path, inspect the repository/agent environment for the existing skill convention and use that rather than inventing an incompatible layout.

Suggested logical name:

`pentax-hardware-stability`

## Mandatory skill behaviour

### 0. Release integrity is a hard precondition

Never build or stage a release from an uncommitted patcher tree. Record the
exact patcher commit, libgphoto2 commit, stock FwPkt hashes, build parameters,
and generated runtime wrapper contents. The public provenance row must be
committed before the artifact is handed off.

Run both package and `firmwareInfo` gates against the actual zip, then verify
the extracted appfs contains `/app/bin/pgphoto` with the intended `CAMLIBS`,
`IOLIBS`, `LD_LIBRARY_PATH`, `LD_PRELOAD`, and preview policy values. Source
tests alone do not prove packaged behavior.

Do not install a candidate until a no-camera runtime canary and the previously
qualified camera matrix have passed. If a candidate causes an outage, stop
qualification, preserve exact logs and provenance, and restore the last known-
good registered FwPkt through the sanctioned extracted-tree flow.

### 1. Start from the hypothesis, not from recovery

For every task, identify the failure hypothesis and ask:

> What is the lowest layer capable of reproducing or disproving this hypothesis?

Default progression where applicable:

```text
A: PC direct libgphoto2
        |\n        +-- reproduces -> minimise/investigate/fix here\n        |
        +-- clean -> B: PC Benro/pgphoto-compatible harness\n
        |\n                         +-- reproduces -> integration/command-lifecycle investigation\n
        |\n                         +-- clean -> C: real Polaris\n```\n\nDo not move to Polaris merely to obtain another reproduction of a defect already isolated below it.\n\nPolaris-specific hypotheses — embedded USB, pgphoto watchdog/process behaviour, camera_usb_supervisor, 8080/Wi-Fi pressure, firmware/runtime-loader/FwPkt behaviour — may start at Layer C.\n\n### 2. Agent is test director; human is physical operative

The skill should contain a strong rule:

> **You are the test director. The human is the physical operative. Never ask the human to decide which host, test, recovery action, or timing is appropriate. Give one explicit physical instruction, wait for confirmation, independently verify the resulting machine state, then continue.**

The agent must explicitly tell the operative when to attach the camera to:

- the **test PC** for Layer A/B; or\n- the **Polaris** for Layer C.

It should use/reference the exact prompts in `docs/pentax-agent-operative-prompts.md`.

### 3. Verify every physical move in software

Human confirmation is not proof of attachment.

After every move, independently verify current enumeration on the destination host and log:

```text
CAMERA=K-3 III|K-1 II
ATTACHMENT=PC|POLARIS
LAYER=A|B|C
PATH=<actual software path>
USB=<current observed identity>
```

On Polaris, a cached model name or stale `usb:BUS,DEVICE` must never count as verification.

If verification fails, STOP and diagnose rather than starting the experiment.

### 4. Minimise physical cable moves

Batch compatible experiments by host. Typical K-3 III flow should be:

```text
PC session
  Layer A direct tests
  Layer B tests for A-clean hypotheses

one deliberate PC -> Polaris move

Polaris session
  Layer C differential/embedded tests
```

K-1 II follows as the explicit second pass using the same A -> B -> C method.

### 5. Preserve causal evidence

The skill must direct the agent to identify and record the **first abnormal state transition**, not merely the eventua
l stale session/crash/reset requirement.

Expected causal record:

```text
trigger
  -> first incorrect transition
  -> contaminated state
  -> visible
symptom
  -> recovery
```

Fix/test as far left in this chain as possible.

### 6. Physical recovery is one variable at a time

Never casually bundle:

- camera power-cycle;\n- USB reconnect;\n- USB Compatibility toggle;\n- pgphoto restart;\n- Polaris reboot.

Request them separately so the experiment preserves evidence about what actually recovered the system.

For destructive fault injection, arm the test first and give the operative an exact trigger such as `DISCONNECT NOW`; never ask them to estimate when an exposure or Pixel Shift/NR processing phase has finished.

### 7. Respect Pentax long-operation semantics

The skill must reference `docs/pentax-mode-aware-liveness.md` and enforce:

```text
physical sensor exposures != camera processing phases != output files != tether candidates
```

Requested shutter + mode establish expectations only. They are not authoritative completion/liveness signals.

Do not hard-code assumptions such as Pixel Shift candidate count = 4/5 or NR completion = exactly 2T.

Do not declare a multi-minute astro capture dead merely because a fixed timer elapsed while the camera/transport/process still supplies evidence of legitimate activity.

### 8. Candidate safety

Never purge/delete an unknown DNG or transfer candidate simply to clear state.

Candidate reconciliation must establish ownership and preserve the requirement that camera-side RAW/DNG can remain on the camera while the appropriate JPEG is transferred to Pol<unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk><unk>