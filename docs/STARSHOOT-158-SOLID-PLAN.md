# #158 StarShoot — SOLID PLAN (2026-09-29)

> Preserved historical author plan from 2026-09-29. Attachment, line numbers
> and test observations below refer to that session, not current live state.
> The measured vendor-specific device contract remains authoritative.

Status: adapter skeleton present; NOT linked; NOT enumerated by gphoto; device physically attached (USB 001:022, dmesg 16c0:29a0 reconnect cycle). User: "will now attach the starshoot" (corrected from earlier "will not attach"). No StarShoot shutter/test fired; no runtime mutation.

## Where it is (verified evidence)
- Issue file: GITHUB_ISSUE_ORION_STARSHOOT.md (#158, vendor-protocol / libusb, NOT UVC — adapter contract docs/ORION-STARSHOOT-ADAPTER-CONTRACT.md confirms USB class 255, single interface, bulk+isochronous endpoints; no kernel driver bound).
- Adapter source: container/stage2_starshoot_adapter.c (142 lines) + .h (36 lines); exports init/open/close/stream_bulk_iso; libusb backend.
- Adapter linkage: container/patch.sh line 424 — "NOT yet linked into libpolaris_stage2.so (full link is the next step)"; compile-check only (`-c -o .o`); adapter .o NOT added to link line.
- Loader/policy: container/stage2_loader.c / stage2_policy.c / stage2_policy.h — zero starshoot/adapter references; no adapter_init() call; no adapter policy.
- Device USB (SSH 192.168.0.1): lsusb = Bus 001 Device 022: ID 16c0:29a0; dmesg = idVendor=16c0 idProduct=29a0 reconnect (same 1-1.2 port as iPolar 1233:1455 — both reconnect-cycling).
- gphoto: /app/bin/gphoto2 --auto-detect = EMPTY (no Model/Port rows) — USB-attached ≠ gphoto-visible.
- 13w build (o-v13w-context-isolation-20260929, FwVer 6.0.0.54.42): Pentax K-3 III (25fb:0189) two-shot PASS; StarShoot adapter compiled (per evidence); iPolar adapter compile-check skipped (libuvc headers absent). 13w scope excludes StarShoot linkage — consistent.
- Linkage feasibility check (this session): adapter source complete; linkage ALONE insufficient — requires loader init + policy wiring + protocol identification + on-device proof.

## What needs to be done next (ordered, fail-closed; separate from #159 iPolar)
Per adapter contract (docs/ORION-STARSHOOT-ADAPTER-CONTRACT.md) + #151 ownership layer + patch.sh linkage gap:

1. Confirm exact StarShoot model/firmware (vendor-protocol QHY5L-II variant family spans UVC + vendor-protocol; 16c0:29a0 is vendor-protocol, NOT UVC — do NOT treat as UVC camlib addition).
2. Identify QHY5L-II / INDI command protocol / SDK version for 16c0:29a0 (adapter contract open item #2 — BLOCKING prerequisite).
3. Validate libusb backend on host (adapter contract open item #3; adapter uses libusb-1.0, not libuvc).
4. Define adapter interface: command set, stream format (bulk alt 1 + isochronous alt 3 per descriptor), reconnect behavior (adapter contract open item #4).
5. Wire adapter into stage2_loader.c (adapter_init() call) + stage2_policy.c/h (adapter policy / routing) — NOT just compile-check.
6. Add adapter .o to libpolaris_stage2.so link line in patch.sh / build_fullstack.sh (mechanical linkage step; patch.sh line 424 notes this is the next step).
7. On-device proof (adapter contract open item #5): open, handshake, bounded frames, reconnect, packaging/provenance/rollback — before any release claim.
8. Only after (1)-(7): consider gphoto enumeration test (`gphoto2 --auto-detect` must show StarShoot); do NOT claim PASS on linkage alone.

## What is NOT in scope for #158 (explicit exclusions)
- iPolar (#159, 1233:1455, UVC/libuvc) — separate adapter contract (docs/IPOLAR-UVC-BACKEND-PLAN.md), separate linkage, separate protocol. Do NOT combine linkage steps.
- UVC camlib addition (`--with-camlibs=ptp2,pentax,uvc`) — StarShoot is vendor-protocol (USB class 255), NOT UVC; adding uvc camlib does NOT solve #158.
- StarShoot shutter/test — not fired; no runtime mutation performed; no evidence added to 13w (scope remains Pentax-only).
- Direct /app binary mutation — release-qualified changes must flow: source change → clean patcher build → architecture/ABI/provenance gates → immutable FwPkt + manifest → SD-card install → cold reboot → runtime-loader proof → physical regression matrix (per AGENTS.md).

## Evidence references (local workspace)
- Adapter source: container/stage2_starshoot_adapter.c, .h
- Adapter contract: docs/ORION-STARSHOOT-ADAPTER-CONTRACT.md
- Issue file: GITHUB_ISSUE_ORION_STARSHOOT.md (this file; 2026-09-29 note appended)
- Linkage gap: container/patch.sh lines 422-431 (compile-check only; "NOT yet linked")
- Loader/policy gap: container/stage2_loader.c, stage2_policy.c, stage2_policy.h (zero adapter refs)
- USB evidence: SSH 192.168.0.1 lsusb (16c0:29a0 device 022); dmesg reconnect cycle
- gphoto evidence: /app/bin/gphoto2 --auto-detect = empty
- 13w evidence: docs/evidence/o-v13w-context-isolation-20260929/ (Pentax PASS; adapter compile state)
- Ownership layer: docs/IPOLAR-UVC-BACKEND-PLAN.md (#151); docs/LIBGPHOTO2-UPGRADE-PROCESS.md
- Provenance: docs/FWPKT-PROVENANCE-CONTRACT.md (adapter linkage is a build/provenance gate, not a zip-byte change)

## Next action (single, bounded)
Identify QHY5L-II/INDI command protocol for 16c0:29a0 (adapter contract open item #2) — this is the blocking prerequisite before loader init, policy wiring, or linkage can be validated. Until protocol is identified, linkage (step 6) is mechanical but untestable.
