---
name: polaris-evidence-discipline
description: "Evidence and tracing discipline for the Benro Polaris camera stack. USE FOR: deciding who owns a defect, writing findings/evidence files, attributing a failure to vendor vs our code, deciding whether a fix is verified, and looking up Pentax/pgphoto/Benro Connect behaviour in the authoritative sources already on this workstation. DO NOT USE FOR: building or flashing a packet (polaris-release-orchestrator, fwpkt-update-flow) or editing camlib source."
---

# Evidence discipline (Polaris camera stack)

This skill exists because of one specific failure, repeated in many costumes.

On 2026-11-27 an agent recorded in `docs/evidence/k1ii-overnight-20261126/HANDOFF.md`
that K-1 II autofocus is "not our code" because `updateCameraAutoFocus`,
`camera_autoFocus_enable` and `sp_Gphoto_Init` "appear in no source file in this
repo", and concluded it must be reported upstream. That reasoning is invalid:
the vendor binary had already been decompiled with Ghidra and was sitting on the
same workstation. Its `updateCameraAutoFocus()` is a generic libgphoto2 widget
call — `_find_widget_by_name` then `gp_camera_set_config` — so the widget it
names belongs to our camlib, and ownership was never ours to disclaim.

The grep was correct. The inference was wrong, and nothing in the workflow
caught it. Every rule below exists to make that class of error mechanical to
avoid rather than a matter of diligence.

## 1. Absence of evidence is not a finding

"X does not appear in our repos" supports exactly one conclusion: *we have not
found it*. It never supports "not ours", "vendor limitation", or "cannot be
fixed here". Before any such sentence, run the lookup across every authoritative
source:

```bash
scripts/find-authoritative-source.py updateCameraAutoFocus
scripts/find-authoritative-source.py --opcode 262
scripts/find-authoritative-source.py --feature autofocus
```

It searches the vendor decompilations, the Pentax reference implementations and
our own layers, prints which roots are **MISSING** rather than skipping them
silently, and refuses to let a zero-hit result read as a clean answer. A silent
skip is precisely how the pgphoto decompilation stayed invisible for weeks.

The sources it covers, all verified present on this workstation:

| Source | What it settles |
|---|---|
| `pr-publish/pgphoto-re/decompiled/` | what the shipped daemon actually calls |
| `LibGphoto2/ImageTransmitter2/.../MtpDevice.cs` | vendor protocol opcodes, per-model gating |
| `LibGphoto2/ImageTransmitter2/.../MainWindow.xaml.cs` | which UI actions are gated and on what |
| `PrivateResearch/openpolaris-research/Benro-Connect/benro-connect-decompiled/` | phone-app behaviour and opcode framing |
| `LibGphoto2/libgphoto2/camlibs/ptp2/` | our camlib implementation |
| `container/astro/` | our Web UI, httpd opcode table, Stage-2 kit |

Vendor hits are **Ghidra/decompiler output**, not upstream source. Names and
signatures come from DWARF; statement text is reconstructed. Quote them for
behaviour, never as "the vendor file says".

## 2. Read the code that printed the line

Every mechanism claim must cite the producing code, not the log line. Across
this project's own findings files the recurring self-correction is exactly this:
a supervisor message read as a latch bug, a `held_ms` distribution read as a
cause, an `output_pending=0` field read as a format condition when it is a latch
from a previous capture.

Before writing "X does Y because Z":

```bash
grep -rn "the exact literal string in the log" <the repo that owns that binary>
```

If the string is not in any source we own or decompiled, say *unknown producer*
— do not invent one.

## 3. An empty grep is a broken probe, not a healthy device

Two incidents, same shape: rig tools grepped `/app/Clog.txt`, which does not
exist on `.115+` (rotating logs live under `/app/sd/system/log/`). Zero matches
were indistinguishable from zero failures, and a gate with 61 live refusals was
reported as clean. Fixed in `scripts/probe-config-gate.py`; unknown now reports
UNKNOWN rather than 0.

Rule: any check that can return "nothing found" must distinguish *nothing wrong*
from *nothing looked at*. When adding one, assert the input is non-empty before
interpreting it. Prefer the existing tools over ad-hoc greps:

- `scripts/probe-config-gate.py` — gate admission state
- `scripts/stress-config-gate.py` — concurrent read load
- `scripts/capture-outcomes.py` — per-capture PASS/FAIL with the missing-`state:4` tell
- `scripts/find-unmatched-capture-attempts.py` — attempts that never completed

## 4. Check depth before declaring something absent

`git rev-parse` in `/home/ian/Documents/VSCodeProjects/LibGphoto2` reports "not a
git repository". The repo is one level down at `LibGphoto2/libgphoto2`, on
`main`, clean, pushed to `origin`. A whole session's worth of "your driver work
is unversioned" was wrong because the check stopped at the container directory.

Same shape as a duplicate evidence tree that looked like lost work:
`LibGphoto2-v113-release/docs/evidence/pc-dual-camera-final-2026-09-11` is
byte-identical to the copy already in the driver repo — `diff -rq` says so.

Before "there is no X": search one level deeper, and diff before concluding
anything is unique or missing.

## 5. Verified means the layer it will run on

A host-side unit test proves logic. It does not prove behaviour on the head.
The store-full capture remap passes 8 cases on the workstation and has never
executed on a rig; recording that as "fixed" would be false. Label every fix in
one of exactly three states, and never promote one to another silently:

- `logic-tested` — host test passes, named test file cited
- `device-installed` — `scripts/verify-installed-build.sh` PASS, loader digest
  matches the built artifact byte-for-byte
- `hardware-qualified` — the operator's symptom is gone on the physical body,
  with the command and log that show it

Anything else is `not verified`. "Built" is not a state.

## 6. One command per claim

Every finding line carries the reproducible command and the exact artifact path
that produced it. If a claim cannot survive being re-run, it is a hypothesis and
must be written as one. This is what separates a finding from a diary entry, and
it is what lets the next agent build on the work instead of re-litigating it.

Verbs like "investigated", "traced", "analysed" are not deliverables. If a step
produced no artifact, no commit and no decision, say so plainly.

## 7. Ownership routing still applies — after the lookup

Route to the layer that **first diverges**, per `polaris-debugging`. The lookup
in §1 is what makes "first diverges" an evidenced statement rather than a guess.
A Polaris-only symptom is not enough to file against the driver fork; you need a
direct reproducer first. Conversely, once vendor decompiled code shows the call
lands in a widget our camlib owns, the defect is ours regardless of which binary
printed the error.

## Worked example: K-1 II AF (issue #359)

Verified from the sources, in order:

1. `pgphoto-re/decompiled/gpManager.decompiled.c` — `updateCameraAutoFocus(int
   enable)` calls `_find_widget_by_name`, checks `gp_widget_get_readonly`,
   requires `GP_WIDGET_TOGGLE`, then `gp_camera_set_config`. It returns `-1`
   when the widget is not found, when it is readonly, or when the type is not a
   toggle.
2. Our camlib has a Pentax `autofocus` menu entry whose get/put delegate to the
   generic `_get_Autofocus` / `_put_Autofocus`, which only read and write a
   libgphoto2 **setting** — they never touch the camera.
3. The K-1 II advertises five properties in DeviceInfo where the K-3 III
   advertises thirty-five, and our own comment records that this is a declaration
   gap, not a hardware limit.

What is **not** yet proven: which widget name pgphoto resolves for Pentax,
whether that widget is created on the K-1 II at all, and which of the three `-1`
branches fires. Those are answerable from the decompilation plus one direct-PC
run — not from a bench log. Do not record #359 as upstream-only until they are.

## Quick reference

```bash
# who owns this? search every authoritative source first
scripts/find-authoritative-source.py <symbol> --context
scripts/find-authoritative-source.py --opcode <n>

# is the installed thing actually what we built?
scripts/verify-installed-build.sh

# gate / capture truth, from the real log paths
scripts/probe-config-gate.py
scripts/capture-outcomes.py
```

## Cross-references

- `polaris-debugging` — SSH access, gimbal-vs-router, direct-on-PC ownership
  experiment, repo routing table.
- `pentax-hardware-stability` — K-3 III / K-1 II stability investigations.
- `polaris-regression-preservation-review` — what a fix must carry before merge.
