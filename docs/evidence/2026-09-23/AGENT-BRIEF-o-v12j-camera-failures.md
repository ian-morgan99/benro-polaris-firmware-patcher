# Agent brief — o-v12j camera failures + TA comment review (2026-09-23)

Prepared for the next agent. Everything below is verified state as of 2026-09-23 ~19:40 UTC.

## 1. Firmware currently on the Polaris
- **o-v12j** `6.0.0.54.20-o-v12j-lifecycle-lvoff` (installed today via `scripts/release/release-fwpkt.sh`, all six on-card MD5s verified, `SP_EVENT_UPGRADE_SUCCESS`).
  - libgphoto2 source: `6da9612a6` (ptp2/pentax async capture lifecycle fix; successor to `6aa3e4e66`)
  - patcher commit: `a710c09` — stage2 defaults Pentax PC Live View OFF at connection (`STAGE2_PENTAX_KEEP_LV=0`, `STAGE2_PENTAX_PREVIEW_BACKOFF=1` in wrapper)
- No-camera canary PASSED (processes, listeners 22/80/8080/9090, stage2 maps, no fatal signatures). Registry row updated + pushed (`41b01ec`).

## 2. New operator-reported failures on o-v12j (K-3 III, USB 25fb:0189, serial 8093033)
Logged as GitHub issues in `ian-morgan99/benro-polaris-firmware-patcher`:
- **#134** REGRESSION: enabling Live View causes **continuous shutter release** (seen "many versions ago" — regression of an older continuous-shutter mode).
- **#132** BUG: shutter release **hangs the system**; device evidence shows pgphoto in a restart loop.
- **#133** BUG: K-3 III **drops off the USB bus** after shutter release.

### Device-side evidence captured (o-v12j, camera attached)
- `/app/Clog.txt`: **20 consecutive full pgphoto init cycles** (`dlopen core ok` x20; 64/64 slot resolution each) before truncation → pgphoto crash/restart loop. Current PID 23233 up ~10 min at capture time.
- `/app/Mlog.txt`: `SP_MsgFromCameraProc ... code[286], val[manufacturer:none;model:none;state:-10;storage:0;photoFormat:0]` — Polaris reports camera state **-10 (not connected)** while the K-3 III is physically on the bus.
- `dmesg`: `usb 1-1.2: reset high-speed USB device number 3 using xhci-hcd` (K-3 III, 25fb:0189) — host-side reset of the camera interface.
- Likely cascade: LV-on → repeated shutter releases (#134) → hang/restart loop (#132) → USB reset / camera off bus (#133).

### Hypotheses to investigate (unverified)
1. o-v12j's LV-off connection default (`STAGE2_PENTAX_KEEP_LV=0`) + the async capture lifecycle fix (`6da9612a6`) interact badly: enabling LV from the app re-arms PC-LV and each preview frame / LV re-activation is treated as a capture trigger → continuous shutter.
2. The restart loop may be the fail-closed recovery probe refusing/retrying after a wedged session (cf. #122, #127 preview-governor backoff collapse).
3. `state:-10` while on-bus suggests pgphoto's camera state machine lost the device after the USB reset; check whether the supervisor re-fingerprints (cf. #126) or wedges.

## 3. TA comments reviewed (most recent, all @ian-morgan99 = TA/owner)
No comments in any repo since **2026-09-20**; the actionable set is from 09-06 → 09-19:

### libgphoto2 #49 (WB/aperture/capture verification fix, `6aa3e4e66`)
- Direct-host PASS recorded for K-1 II + K-3 III with `pentax_research_capture=true` (WB SET via 0x5005 wire property; aperture timeout 500→1000 ms + FNumber/10 fix; capture succeeds on both bodies).
- **TA qualification bar (open item):** current evidence is a *post-fix PASS*, not complete validation. Required before closure/upstream: same-boundary A/B — exact pre-fix parent SHA vs `6aa3e4e66240d4b4d68a65b75631e0f6aadf308a`; same body/FW/USB mode, fresh power-cycled session; one property per run (GET-before → SET → GET-after for WB and aperture); full `gphoto2 --debug` traces showing the first differing PTP/verification op; enough repeats to rule out K-1 II session-wedging. Keep `pentax_research_capture` constant across both sides.

### libgphoto2 #44 (direct-host qualification matrix)
- At fork `38780d88` (2026-09-10): K-3 III init/summary PASS; preview PASS 5/5 valid JPEGs (81–87 KB, 16–31 ms); focus init PASS; directional focus FAIL-safe (`0x9017` ±23 → `0xa00c`, no retry/escalation). K-01 detect/summary PASS; safe-preview correctly refused (unsupported model).
- LV zoom gate: advertised 2x write failed `SetDevicePropValue(0xd037) -> 0x201c`; run was in a reconciled/reused session (init reported already-open Pentax session; d035/GetAllConditions `0x2017` before vendor enable) → record as FAIL-in-reused-session; require physical cold/fresh-session discriminator before calling it a serialization defect.
- Repeated open/read/exit baseline: K-3 III 10/10, K-01 10/10 — basic detect/connect/disconnect stability qualified at `38780d88`.

### libgphoto2 #42 (upstream-readiness / cleanup series)
- `append_folder_from_handle()` now treats `PTP_HANDLER_SPECIAL` (`0xffffffff`) as root terminator in the **generic** PTP2 path — needs a deterministic test/fixture (MTP object with parent `0xffffffff` terminates folder reconstruction; non-Pentax/plain-PTP root semantics unchanged) + documentation that this hunk is a generic MTP correctness fix, separate from Pentax functional changes.
- Maintainability findings (IT2 reconciliation): duplicate `pentaxliveviewafposition` menu registration in `camlibs/ptp2/config.c` (#69); questionable `0x9013` Green-button branch in research capture gate (#45 reopened; real family is `0x9011`/`0x9012`); `ptp2_pentax_aperture_alias_present()` production-exported test hook for #53 should be removed/reworked; `CAPABILITY_MATRIX_AUDIT.md` stale (#70).
- **Latest (2026-09-19):** commit `7e165a9e3` needs a provenance-cleanup pass before upstream-ready: production comments/commit rationale cite research path + internal filenames (`MtpDevice.cs`, `MainWindow.xaml.cs`, offsets) instead of independently testable protocol facts. Rewrite public comments/docs to state only the observable contract (exposure-mode value selects Astro Tracer; reported AstroTracerTimeLimit bounds exposure; capability flag is not live state); keep research provenance private; require direct hardware confirmation on the affected body before promoting as hardware-verified.

### benro-polaris-firmware-patcher #35 (K-3 III embedded MTP umbrella)
- Root cause isolated 09-07: **stage2 deployment defect** — `/app/lib/stage2/libgphoto2_port.so.12` was a 38,620-byte stripped stub always returning "no iolibs found" → `sp_Gphoto_Init` -2 → runtime `state:-2`; same camera/SHA worked via direct embedded CLI. Fix: ship a libgphoto2_port matching the core ABI (`LIBGPHOTO2_5_0`, correct iolibs path). (o-v12j now ships the real port lib — canary maps confirm `/app/lib/stage2/libgphoto2_port.so` loaded.)
- Ownership rule: observed limited-control/preview state is **presumed patcher/runtime-owned** until a clean rebuilt FwPkt fixes #38/#39 and is retested; only residual ops that also fail direct clean libgphoto2 move to source issues. Cross-record direct results in libgphoto2#44.

### OpenPolaris handoff doc (referenced by libgphoto2 #48)
`OpenPolaris/docs/evidence/2026-09-07/agent-handoff/HANDOFF-LIBGPHOTO2.md`: if repo-local reproduction fails the same way as Polaris, ownership moves to libgphoto2 (open PR vs `origin/master`, even draft). Key question for WB/aperture: **which exact PTP transaction first produces the error** (not just final -6). Test commands:
```
gphoto2 --set-config /main/status/pentaxdirectwb=daylight
gphoto2 --get-config /main/status/pentaxdirectwb
gphoto2 --set-config /main/status/pentaxdirectaperture=f/4
gphoto2 --get-config /main/status/pentaxdirectaperture
```

## 4. Suggested next actions for the incoming agent
1. **Reproduce #134 first** (LV-on → continuous shutter) on o-v12j with `POLARIS_TRACE`/Clog capture; confirm whether each preview frame triggers a capture (check `gp_camera_capture` shim hit-rate in Clog).
2. Check the LV-off default path: does enabling LV from the app push `pentaxpclvkeep` ON and re-arm the high-rate preview loop despite `STAGE2_PENTAX_PREVIEW_BACKOFF=1`? (cf. #127 governor backoff collapse.)
3. For #132/#133: capture Clog across a full hang→restart cycle; verify whether the 20-cycle loop is pgphoto self-restarting or polestar_app respawning it; check `state:-10` origin (supervisor vs pgphoto state machine) and whether the USB reset (`dmesg`) precedes or follows the restart loop.
4. Keep #123 demand-owned LV/thermal experiment OUT of any capture-side fix candidate.
5. When a fix candidate is built: K-3 III + K-1 II baselines — connect (verify no persistent PC-LV starts), preview, config reads, two consecutive dual-format captures; compare against v10 as behavioural control.

## 5. Repo/issue map (quick reference)
- Patcher repo open & relevant: #122 (shutter uncontrollable), #127 (preview governor backoff collapse), #126 (USB supervisor fingerprinting), #125 (wall-clock cooldowns), #130 (evidence: rescue shutter completion + thermal), #132/#133/#134 (new, this session), #128 (closed, o-v12b state:-1005 hang — same family).
- libgphoto2: #42 (upstream cleanup series), #44 (direct-host matrix), #49 (WB/aperture/capture verification; A/B bar open), #48 (handoff), #45 (reopened, 0x9013 green-button), #69/#70 (cleanup).
- OpenPolaris: handoff doc at `docs/evidence/2026-09-07/agent-handoff/HANDOFF-LIBGPHOTO2.md`.
