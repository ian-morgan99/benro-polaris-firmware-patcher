# IT2 v2.6.2.5 Feature Review — Pentax Capability Gap Analysis

**Status:** Documentation of findings only. No source changes, builds, or hardware tests performed by this document.
**Date:** 2026-11-22
**Source reviewed:** `LibGphoto2/IT2_2625_decompile/RemoteAssistant/` (decompiled C# of Ricoh/Pentax IMAGE Transmitter 2)
**Compared against:**
- `LibGphoto2/libgphoto2/camlibs/ptp2/` — PTP camlib with Pentax vendor extensions
- `LibGphoto2/libgphoto2/camlibs/pentax/` — legacy SCSI/USBSCSI camlib (older DSLRs only)
- `BenroPolarisPatcher/container/stage2_loader.c` / `stage2_policy.c` — Polaris stage2 patcher

---

## Purpose

This document records a systematic comparison of IT2's Pentax camera control surface against what is implemented in libgphoto2's ptp2 camlib and the Benro Polaris stage2 patcher. It is intended to guide future development: any item listed as "absent" or "partial" must be validated by the owning agent before being treated as a confirmed gap, and any item listed as "present" must be re-verified against the exact built artifact before being relied upon in a release.

---

## 1. IT2 vendor operation codes — all 25 defined

IT2 defines these Pentax vendor extension operation codes (0x9000–0x97FF range). All are defined in `libgphoto2/camlibs/ptp2/ptp.h`.

| Op | Hex | Name | Wrapper in `ptp.c` | Called from libgphoto2? | Called from stage2? |
|----|-----|------|-------------------|------------------------|---------------------|
| SetVendorMode | 0x9001 | `ptp_pentax_set_vendor_mode` | ✅ | ✅ (identify/exit) | ❌ |
| CameraShutdown | 0x9002 | `ptp_pentax_camera_shutdown` | ✅ | ✅ (library.c exit) | ❌ |
| ReceivedCreatedObject | 0x9003 | `ptp_pentax_received_created_object` | ✅ | ❌ **defined only, never called** | ❌ |
| SetCardWritingMode | 0x9004 | `ptp_pentax_set_card_writing_mode` | ✅ | ✅ (config.c cardwritingmode) | ❌ |
| GetLiveViewFrameData | 0x9006 | `ptp_pentax_get_live_view_frame` | ✅ | ✅ (library.c preview) | ❌ |
| GetSubImage | 0x9007 | `ptp_pentax_get_sub_image` | ✅ | ❌ **defined only, never called** | ❌ |
| GetMainImage | 0x9008 | `ptp_pentax_get_main_image` | ✅ | ❌ **defined only, never called** | ❌ |
| SetWarningMessageFlag | 0x9009 | — | ❌ **no wrapper** | — | ❌ |
| InvokeCameraTask | 0x900a | — | ❌ **no wrapper** | — | ❌ |
| GetTransferCandidateFileInfo | 0x900b | `ptp_pentax_get_transfer_candidate_info` | ✅ | ✅ (library.c reconciliation) | ❌ |
| GetCamFileOperationCommand | 0x900c | `ptp_pentax_get_file_operation` | ✅ | ✅ (library.c transfer) | ❌ |
| GetTransferFileDataBlock | 0x900d | `ptp_pentax_get_transfer_block` | ✅ | ✅ (library.c transfer) | ❌ |
| DeleteTransferCandidate | 0x900e | `ptp_pentax_delete_transfer_candidate` | ✅ | ✅ (library.c reconciliation) | ❌ |
| GetAllConditions | 0x900f | `ptp_pentax_get_all_conditions` | ✅ | ✅ (library.c admission + verification) | ❌ |
| InitiateCapture | 0x9011 | `ptp_pentax_initiate_capture` | ✅ | ✅ (library.c capture + config.c autofocusdrive) | ❌ |
| TerminateCapture | 0x9012 | `ptp_pentax_terminate_capture` | ✅ | ✅ (library.c bulb finalize) | ❌ |
| InterruptFunction | 0x9013 | `ptp_pentax_interrupt` | ✅ | ✅ (library.c line 7887) | ❌ |
| SetLightMeteringMode | 0x9014 | — | ❌ **no wrapper** | — | ❌ |
| FocusControl | 0x9016 | `ptp_pentax_focus_control` | ✅ | ✅ (config.c old-focus drive) | ❌ |
| FocusControlNew | 0x9017 | `ptp_pentax_focus_control_new` | ✅ | ✅ (config.c new-focus drive) | ❌ |
| SetCompositionAdjustmentOffset | 0x9018 | — | ❌ **no wrapper** | — | ❌ |
| SetKeepAperturePosition | 0x9019 | — | ❌ **no wrapper** | — | ❌ |
| MeasureWhiteBalanceGain | 0x9021 | — | ❌ **no wrapper** | — | ❌ |
| ExecuteDustReduction | 0x9022 | — | ❌ **no wrapper** | — | ❌ |
| GeneralCommand | 0x97ff | — | ❌ **no wrapper** | — | ❌ |

**Key finding:** Capture (InitiateCapture/TerminateCapture) and focus control (FocusControl/FocusControlNew) ARE implemented in libgphoto2 ptp2. My earlier review incorrectly claimed they were absent. The genuine gaps are the 8 opcodes with no wrapper at all, plus 3 wrappers that exist but are never invoked.

---

## 2. IT2 device properties — all 30 defined

| Prop | Hex | Name | Config widget in libgphoto2? | Called from stage2? |
|------|-----|------|------------------------------|---------------------|
| LiveViewAreaInfo | 0xd009 | ✅ `_get_Pentax_LiveViewControls` | ✅ | ❌ |
| ShutterSpeed | 0xd00f | ✅ Direct shutter | ✅ | ❌ |
| DriveMode | 0xd013 | ✅ `_get_Pentax_DirectDriveMode` | ✅ | ❌ |
| ExposureBracketingMode | 0xd014 | ✅ `_get_Pentax_BracketMode` | ✅ | ❌ |
| ExposureBracketingStep | 0xd015 | ✅ `_get_Pentax_BracketStep` | ✅ | ❌ |
| ColorTemperature | 0xd018 | ✅ `_pentax_prop_get/put` | ✅ | ❌ |
| WritingFileFormat | 0xd01b | ✅ `_pentax_wff_read/verify` | ✅ | ❌ |
| ExtendedISO | 0xd01e | ✅ generic INT | ✅ | ❌ |
| CustomImageMode | 0xd020 | ✅ `_get_Pentax_CIMode` | ✅ | ❌ |
| CISaturation | 0xd021 | ✅ PENTAX_DEFINE_PROP_ACCESSORS | ✅ | ❌ |
| CIHue | 0xd022 | ✅ PENTAX_DEFINE_PROP_ACCESSORS | ✅ | ❌ |
| CIKey | 0xd023 | ✅ PENTAX_DEFINE_PROP_ACCESSORS | ✅ | ❌ |
| CIFilterEffect | 0xd024 | ✅ PENTAX_DEFINE_PROP_ACCESSORS | ✅ | ❌ |
| CIMonotoneToning | 0xd025 | ✅ PENTAX_DEFINE_PROP_ACCESSORS | ✅ | ❌ |
| CIToning | 0xd026 | ✅ PENTAX_DEFINE_PROP_ACCESSORS | ✅ | ❌ |
| CIFineSharpness | 0xd027 | ✅ PENTAX_DEFINE_PROP_ACCESSORS | ✅ | ❌ |
| CIHighlightContrast | 0xd028 | ✅ PENTAX_DEFINE_PROP_ACCESSORS | ✅ | ❌ |
| CIShadowContrast | 0xd029 | ✅ PENTAX_DEFINE_PROP_ACCESSORS | ✅ | ❌ |
| CompositionAdjustment | 0xd02a | ✅ `_get_Pentax_CompositionAdjust` | ✅ | ❌ |
| FocusPeaking | 0xd02b | ✅ `_get_Pentax_FocusPeaking` | ✅ | ❌ |
| CustomImageCrossProcess | 0xd02c | ✅ `_get_Pentax_CrossProcess` | ✅ | ❌ |
| CustomImageUserFilter | 0xd02d | ❌ **no widget** (probe table only) | — | ❌ |
| UsbLiveViewMode | 0xd035 | ✅ `_get_Pentax_UsbLiveViewMode` | ✅ | ❌ |
| LiveViewAFPosition | 0xd036 | ✅ `_get_Pentax_LiveViewAFPosition` | ✅ | ❌ |
| LiveViewZoom | 0xd037 | ✅ `_get_Pentax_LiveViewZoom` | ✅ | ❌ |
| MovieMode | 0xd039 | ✅ `_get_Pentax_MovieMode` | ✅ | ❌ |

**Key finding:** 29 of 30 properties have config widgets. Only CustomImageUserFilter (0xd02d) lacks one. None are wired into stage2.

---

## 3. Capture and focus — verified present

### Capture
`camera->functions->capture = camera_capture` → `camera_pentax_capture()` → `camera_pentax_capture_internal()` which:
1. Reads `GetAllConditions` for admission gating (activity flags, capability bits, candidate state)
2. Calls `ptp_pentax_initiate_capture(params, release_mode=0, focus_mode, 0, 0, 0)` — **0x9011**
3. Polls `GetAllConditions` until candidate appears (+32==1, +36=handle)
4. Transfers via `GetTransferFileDataBlock` (0x900d) with block-by-block streaming
5. Calls `ptp_pentax_delete_transfer_candidate` (0x900e) to finalize

Bulb path: `ptp_pentax_initiate_capture(params, release_mode=2, ...)` then `ptp_pentax_terminate_capture(params, release_mode)` — **0x9011 + 0x9012**.

### Focus control
`_put_Pentax_ModelAwareFocusDrive` dispatches by model family:
- **New-focus (K-3 III):** `ptp_pentax_focus_control_new(params, displacement)` — **0x9017** with image-plane displacement from `openAvNum`
- **Old-focus (K-1/K-1 II):** `ptp_pentax_focus_control(params, amount, direction)` — **0x9016**

Autofocus widget calls `ptp_pentax_initiate_capture(params, release_mode, focus_mode=1, ...)` — **0x9011 with focus_mode=1** (IT2's CamAutoFocus).

---

## 4. stage2 patcher — Pentax support (verified)

| Feature | File | Status |
|---------|------|--------|
| SHIM #4: keep-live-view (`pentaxpclvkeep=1`) | `stage2_loader.c` | ✅ Model gate matches any Pentax/Ricoh/GX10 |
| SHIM #5: preview backoff + cooldown | `stage2_loader.c` | ✅ 3 timeouts → 30s cooldown, on-demand 2s gate |
| Issue #121: preview settle window | `stage2_loader.c` | ✅ 5s bounded window when session pre-open |
| Issue #125: monotonic clock | `stage2_loader.c` | ✅ `CLOCK_MONOTONIC` |
| Issue #127: capability-disable | `stage2_loader.c` | ✅ Permanent NOT_SUPPORTED stops preview |
| Issue #127: transport failure separation | `stage2_loader.c` | ✅ I/O errors return terminal code |
| Issue #213: cooldown log suppression | `stage2_loader.c` | ✅ Log once per window |

**Not in stage2:** PTP vendor command passthrough, GetAllConditions integration, live view frame acquisition, custom image, white balance, focus control, composition adjustment, aperture keep, bulb timer, movie mode, shutdown, dust reduction, metering, dual SD card slot management.

---

## 5. Accurate gap summary

| Category | IT2 supports | libgphoto2 ptp2 | stage2 patcher | libgphoto2 pentax (SCSI) |
|----------|-------------|-----------------|----------------|--------------------------|
| Shutter release (InitiateCapture) | ✅ | ✅ | ❌ | ✅ |
| Capture termination (TerminateCapture) | ✅ | ✅ | ❌ | ❌ |
| Focus drive (0x9016/0x9017) | ✅ | ✅ | ❌ | ❌ |
| Autofocus (0x9011 focus_mode=1) | ✅ | ✅ | ❌ | ❌ |
| Live view frame acquisition | ✅ | ✅ | ❌ (shim only) | ❌ |
| Keep live view toggle | ✅ | ✅ | ✅ | ❌ |
| GetAllConditions polling | ✅ | ✅ | ❌ | ❌ |
| Custom Image mode + params | ✅ | ✅ | ❌ | ❌ |
| White balance / color temp | ✅ | ✅ | ❌ | ❌ |
| Drive modes | ✅ | ✅ | ❌ | ✅ (basic 6) |
| Exposure bracketing | ✅ | ✅ | ❌ | ❌ |
| Composition adjustment switch | ✅ | ✅ | ❌ | ❌ |
| Focus peaking | ✅ | ✅ | ❌ | ❌ |
| Cross process | ✅ | ✅ | ❌ | ❌ |
| Live view AF position | ✅ | ✅ | ❌ | ❌ |
| Live view zoom | ✅ | ✅ | ❌ | ❌ |
| Movie mode | ✅ | ✅ | ❌ | ❌ |
| Writing file format compound | ✅ | ✅ | ❌ | ❌ |
| Card writing mode | ✅ | ✅ | ❌ | ❌ |
| Capture target alias | ✅ | ✅ | ❌ | ❌ |
| Post-view / main image | ✅ | ⚠️ wrappers only | ❌ | ❌ |
| Block-streaming file transfer | ✅ | ✅ | ❌ | ❌ |
| Dual-format reconciliation | ✅ | ✅ | ❌ | ❌ |
| Orphan candidate recovery | ✅ | ✅ | ❌ | ❌ |
| Bulb timer (start/stop) | ✅ | ✅ | ❌ | ❌ |
| Camera shutdown | ✅ | ⚠️ wrapper only | ❌ | ❌ |
| Dust reduction | ✅ | ❌ (no wrapper) | ❌ | ❌ |
| Light metering mode | ✅ | ❌ (no wrapper) | ❌ | ❌ |
| Interrupt/Green button | ✅ | ✅ (wrapper called) | ❌ | ❌ |
| Composition adjustment offset | ✅ | ❌ (no wrapper) | ❌ | ❌ |
| Aperture keep | ✅ | ❌ (no wrapper) | ❌ | ❌ |
| WB gain measurement | ✅ | ❌ (no wrapper) | ❌ | ❌ |
| General command | ✅ | ❌ (no wrapper) | ❌ | ❌ |
| Custom image user filter | ✅ | ❌ (no widget) | ❌ | ❌ |
| ReceivedCreatedObject ack | ✅ | ⚠️ wrapper only | ❌ | ❌ |

---

## 6. Validation obligations — read before developing

**Every absence listed in this document must be validated by the owning agent before being treated as a confirmed gap.** Specifically:

### For libgphoto2 ptp2 camlib changes (driver repo, #1xx issues)

1. **8 opcodes with no wrapper** — Before implementing SetWarningMessageFlag (0x9009), InvokeCameraTask (0x900a), SetLightMeteringMode (0x9014), SetCompositionAdjustmentOffset (0x9018), SetKeepAperturePosition (0x9019), MeasureWhiteBalanceGain (0x9021), ExecuteDustReduction (0x9022), or GeneralCommand (0x97ff), verify against a direct libgphoto2 build on the target body that the opcode is accepted and behaves as IT2 describes. Do not infer support from the ptp.h define alone.

2. **3 wrappers defined but never called** — `ptp_pentax_received_created_object` (0x9003), `ptp_pentax_get_sub_image` (0x9007), `ptp_pentax_get_main_image` (0x9008). Before wiring these into capture/post-view flows, prove on hardware that the camera responds correctly and that the data phase parsing matches IT2's payload contract.

3. **1 property with no widget** — CustomImageUserFilter (0xd02d). Before adding a widget, verify the camera's descriptor for 0xd02d and the valid value domain from IT2 source or direct measurement.

4. **Capture and focus are present** — Do not re-implement InitiateCapture, TerminateCapture, FocusControl, or FocusControlNew. They are wired into `camera->functions->capture` and the model-aware focus dispatch. Any change to these paths requires physical camera regression testing on K-3 III and K-1 II.

5. **Research gate** — Pentax capture/preview is gated behind `LIBGPHOTO2_ENABLE_PENTAX_RESEARCH_CAPTURE`. Any change to this gate or to the research-capable model list requires explicit justification and hardware qualification.

### For stage2 patcher changes (patcher repo, #2xx issues)

1. **No PTP vendor command passthrough** — stage2 trampolines `gp_*` boundary calls but does not add vendor opcode passthrough. Before adding Pentax vendor command support at the stage2 layer, verify that the pgphoto binary's boundary symbols can be intercepted and that the vendor opcode payloads can be marshaled through the existing trampoline mechanism.

2. **No GetAllConditions integration** — The stage2 preview/capture gate does not poll `GetAllConditions`. Before integrating, verify that condition state (battery, exposure, drive mode, SD state) is needed at the stage2 layer and that polling does not interfere with the ptp2 camlib's own condition reads.

3. **No live view frame acquisition at stage2** — The keep-live-view shim preserves PC-LV but does not acquire frames. Frame acquisition lives in the ptp2 camlib. Do not duplicate frame acquisition in stage2 without coordinating with the driver repo.

### Cross-repo rules

- A claim that something is **correct** is the review agent's to confirm; a claim that something **builds and passes the gate** is the development agent's. Do not upgrade the second into the first.
- Before changing any packaged libgphoto2 component, read and follow `docs/LIBGPHOTO2-UPGRADE-PROCESS.md`.
- Before installing any candidate on the device, read and follow `docs/FIRMWARE-INSTALL-PROCESS.md`.
- Every libgphoto2 upgrade must rerun all previously physically qualified cameras (K-3 III, K-1 II at minimum). Never optimise only for the camera that motivated the change.
- If required hardware is unavailable, mark the candidate unqualified for that camera; do not silently downgrade a previous PASS to untested.

---

## 7. Source anchors

- IT2 opcodes: `LibGphoto2/libgphoto2/camlibs/ptp2/ptp.h` lines 272–296
- IT2 properties: `LibGphoto2/libgphoto2/camlibs/ptp2/ptp.h` lines 346–370
- ptp2 wrappers: `LibGphoto2/libgphoto2/camlibs/ptp2/ptp.c` lines 1919–2163
- Capture implementation: `LibGphoto2/libgphoto2/camlibs/ptp2/library.c` `camera_pentax_capture_internal` (~line 6771) and `camera_pentax_capture` (~line 7781)
- Focus dispatch: `LibGphoto2/libgphoto2/camlibs/ptp2/config.c` `_put_Pentax_ModelAwareFocusDrive` (~line 11860) and `_put_Pentax_GenericManualFocusDrive` (~line 11900)
- Autofocus widget: `LibGphoto2/libgphoto2/camlibs/ptp2/config.c` `_get_Pentax_AutofocusDrive` / `_put_Pentax_AutofocusDrive` (~line 11918), registered at line 14059
- stage2 Pentax shims: `BenroPolarisPatcher/container/stage2_loader.c` lines 354–580 (SHIM #4) and 583–750 (SHIM #5)
- stage2 model gate: `BenroPolarisPatcher/container/stage2_policy.c` `stage2_model_uses_pentax_keep_lv` (~line 35)

---

## 8. Related issues

- libgphoto2 #113: Pentax protocol and implementation research
- Benro #149: Cross-layer programme and regression acceptance
- Benro #180: Physical scenario matrix
- Benro #182: Session wedge
- Benro #251: Bulb cancel (release-blocking)

---

**End of document.** This is a findings record. Any implementation decision based on it must be validated against the exact source and, where hardware-dependent, against physical camera evidence.