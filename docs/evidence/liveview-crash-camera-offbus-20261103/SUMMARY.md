# LiveView died mid-session, pgphoto SIGSEGV'd on a capture file event, and the K-3 III left USB

Date: 2026-11-03 (device clock is UTC; `date` on device returned `Tue Nov 3 12:26:03 UTC 2026`)
Status: **DIAGNOSED. Camera is physically off the USB bus and needs a replug. The crash is a recurrence of the known mid-capture death, now captured by our own handler for the first time.**
Build under test: `pgphoto.stage2ondisk version 1.3.4 build 1.3.9`, `libgphoto 0562e8a`, Stage-2 loader with the uncommitted empty-choice guard present on device.

## 1. What the user saw

LiveView stopped, and afterwards the camera never came back — the app reports no camera at all.

## 2. Timeline (device clock, UTC)

| time | source | event |
| --- | --- | --- |
| 12:00:12–12:03:00 | `Clog_000355` | `[stage2] config-safety: exposurecompensation widget has 0 choices; returning CAMERA_BUSY` ×87 — the pending guard fired and held |
| 12:12:32–12:12:40 | `Clog_000355` | healthy control reads: ISO (15 choices), shutter, aperture, whitebalance (18 choices) all `ret 0` |
| 12:12:41:799 | `Clog_000355` | `updateCameraAutoFocus enable:1 ret:0` |
| 12:12:41:841 | `Clog_000355` | `---- add file` / `New file is in location /store_00010001/DCIM/510_1103/IMGP4050.DNG` / `captureImageEvent:0 Path:IMGP4050.DNG` |
| ~12:12:4x | `/app/stage2-crash.log` (mtime 12:12) | **pgphoto SIGSEGV**, `si_addr=0x00000000 pc=0x00000000`, last checkpoint `slots filled` |
| 12:12:52:038 | `Mlog_000355` | `ERROR checkGphotoTask[3315]: pgphoto is exit,reboot it` — stock watchdog |
| 12:12–12:16 | `Clog_000355/356` | six restart clusters (`mmap slot page @0x30000000`) |
| 12:14:13 | `Clog_000355` | `spGphotoRest` → camera **still on bus** (`scanUsb` lists `25fb 0189` at `/dev/bus/usb/001/003`) but `Pentax session already open from a previous connection; observing camera state.` / `Pentax state is busy or unknown; refusing session close and USB reset.` → `gp_camera_init ret -110` |
| 12:15:36:960 | `Mlog_000355` | `WARN SP_MsgSysFromAppProc[995]: setting usbmode to 1` |
| 12:15:38:418 | `Mlog_000355` | `SP_MsgCameraFromAppProc[603]: HDMI_REBOOT` (app code 302 `confirm:1`) |
| 12:16:29 | `Clog_000356` | post-reboot pgphoto: `scanUsb` finds **no** `25fb`; `--- list count = 0`; still uses cached port → `The port you specified ('usb:001,003') can not be found.` → `sp_Gphoto_Init ret -5` |
| now (12:26) | live `/sys/bus/usb` | **no Pentax on the bus at all** (polled 3× over 12 s): only `1a40:0101` hub and the two xHCI controllers |

## 3. Why LiveView died

The death is **not** in the LiveView path. It lands immediately after a completed capture's file event:

```
[12:12:41:799] updateCameraAutoFocus enable:1  ret:0
---- add file
New file is in location /store_00010001/DCIM/510_1103/IMGP4050.DNG on the camera
[12:12:41:841] captureImageEvent:0  Path:IMGP4050.DNG
<-- process dies here (SIGSEGV, pc=0)
```

That is the same fault as `docs/evidence/pgphoto-dies-mid-capture-20261005/SUMMARY.md`: pgphoto dies after the shutter fires and after the camera announces the file, but before the download half completes. LiveView was running on the same process, so when it died the stream stopped with it. The 2026-10-05 investigation saw this as `SIGILL`/`wait_status=132` observed from outside; here our in-process handler caught it directly as `SIGSEGV`.

**The crash handler's own classification is wrong and must not be trusted here.** It printed:

```
pc classify: NULL jump (an unfilled slot == 0 was called -- exactly the pre-fix race)
last checkpoint reached: slots filled
```

Those two lines contradict each other. `resolved 65/65` / `slots filled 65/65` is printed *before* `main()`, and the checkpoint says `slots filled`, so **no slot was unfilled**. `pc == 0` with every slot populated is a null function-pointer call inside the core (or a zeroed target reached some other way), not the pre-fix unfilled-slot race the message names. See §5.

## 4. Why the camera will not reconnect

Two distinct failures, in sequence:

1. **Before the reboot — wedged session, camera present.** At 12:14 the K-3 III was still enumerated (`25fb:0189`), but the PTP/MTP session left by the crashed process was unrecoverable: `Pentax session already open from a previous connection` → `Pentax state is busy or unknown; refusing session close and USB reset.` → `-110`. The refuse-the-reset guard (correct in general) means nothing could clear the stale session, so every retry returned `CAMERA_BUSY`.
2. **After the reboot — camera gone from the bus.** `dmesg` ends the device's life with `usb 1-1.2: USB disconnect, device number 3`, and it never re-appears. Post-reboot `scanUsb` sees only the hub and controllers, `list count = 0`, and pgphoto still tries its cached `usb:001,003`, producing `-5`. Live polling confirms `25fb` is absent.

So the app is behaving correctly now: there is no camera to open. **This needs physical intervention** — power-cycle the K-3 III and re-seat the cable (the same departure mode recorded on #172, "the K-3 III left USB during the first Bulb attempt"). No software path can restore it while the device is off the bus.

## 4b. What the crash dump actually proves (analysed against `ec22f3d`, the build that produced it)

The device provenance gives `patcher_commit=ec22f3da…`, which is on origin but was not in the local checkout. Analysing the dump against *that* source rather than the stale tree:

| register | value | what it rules out |
| --- | --- | --- |
| `pc` | `0x00000000` | a branch/call to address 0 |
| `lr` | `0x00000000` | **not** a linked call (`bl`/`blx`) — LR would hold the return address. So the null branch was a tail-jump (`b`/`bx`), an `ldm…, {…,pc}` epilogue loading a zeroed stack slot, or a computed jump. |
| `r12` | `0x00000020` | **not** our trampoline. The Stage-2 trampoline is `ldr r12,[pc,#0]; ldr pc,[r12]`, so on entry `r12` must be the slot address `0x300000xx`. `0x20` is not a slot address, so this fault did **not** originate in a patched boundary entry. |
| `sp` | `0xb690f6a0` | inside `b6113000-b6912000 rw-p` — an 8 MB pthread stack (guard page `b6112000-b6113000`). So the fault is on a **worker thread**, not `main`. |
| `sp` vs stack top | `0x2960` = 10.6 KB below the top | **not** stack exhaustion / runaway recursion. A genuine overflow would be at the guard page, not 10 KB from the top. |
| slot state | `resolved 65/65`, checkpoint `slots filled` | no unfilled slot could have been called. |

So four candidate causes are eliminated outright: the pre-fix unfilled-slot race, a Stage-2 trampoline fault, stack overflow, and a linked call to null. What remains is a **non-linking branch through a zeroed pointer inside an already-resolved target** — i.e. inside the 2.5.34 core / `ptp2` / `pentax` camlib, or pgphoto's own code.

**What was in flight.** The last three lines before death are the file event for a completed capture:

```
[12:12:41:799] updateCameraAutoFocus enable:1  ret:0
---- add file
New file is in location /store_00010001/DCIM/510_1103/IMGP4050.DNG on the camera
[12:12:41:841] captureImageEvent:0  Path:IMGP4050.DNG
```

The next operation in that path is the download (`gp_camera_file_get` → `gp_file_get_data_and_size`). LiveView was running concurrently on a different thread — which is consistent with the fault being on a pthread stack, and with `STAGE2_PENTAX_PREVIEW_BACKOFF=1` being active in `/proc/1063/environ`.

**Leading hypothesis at time of writing (RETRACTED — see §4e-2).** Concurrent `gp_camera_capture_preview` (LiveView) and the capture-download path operating on the **same** `Camera*` session. This was disproved by tabulating all ten capture events: LiveView frames were equally present around surviving captures. The real discriminator is an in-flight focus/AF command (code 262), documented in §4e-2.

**Handler coverage caveat.** `/app/stage2-crash.log` is opened `O_WRONLY|O_CREAT|O_APPEND` and contains **exactly one** entry (leading `\n`, 9690 bytes, mtime 12:12). So this is the first fault this handler has ever recorded on this build — yet the two Clog files contain 29 process starts in one boot, and the 2026-10-05 investigation recorded deaths as `SIGILL`/`wait_status=132` with no handler output. The handler covers SIGSEGV/SIGBUS/SIGILL only, so most of these deaths remain invisible. Do not read "one crash entry" as "one crash".

## 4c. Why the reboot did not bring the camera back — re-checked live at 13:09

The hub is alive and host mode works: `lsusb` shows `1d6b:0002`, `1d6b:0003` and the `1a40:0101 USB2.0 HUB` at `1-1`. But **all four hub ports (`1-1-port1..port4`) have no child device**, and there is no Pentax anywhere on the bus. So this is not a controller or role failure — nothing is attaching to the hub at all.

One anomaly worth checking, though it does not explain the current state: the reboot control did more than reboot.

```
[12:09:40] code[814] val[cellular:0;cellhwver:0;usbmode:0;]   <- usbmode was 0
[12:15:33] code[814] val[cellular:0;cellhwver:0;usbmode:0;]   <- still 0
[12:15:36] rcv from App type:2;code:813;val:usbmode:1;        <- app SETS usbmode=1
[12:15:36] WARN SP_MsgSysFromAppProc[995]: setting usbmode to 1
[12:15:36] SP_SaveUserParamToFlash success                     <- PERSISTED TO FLASH
[12:15:38] code:302 val:confirm:1 -> HDMI_REBOOT
```

`usbmode` went `0 → 1` and was written to flash two seconds before the reboot. If mode 1 selects a non-host/gadget role for that port it would permanently prevent camera attachment across boots. The hub enumerating fine argues against a full role flip, but the persisted value is unverified — read it back with app code `814` (or find the param blob) before concluding. It is also possible mode 1 is simply "USB on / charging" and unrelated.

**Flash check performed at 13:20.** `SP_SaveUserParamToFlash` targets MTD partition `mtd2` (`userParam`, 1 MiB). A read-only `dd` of the whole partition yields **no printable strings at all** and only a handful of non-`0xFF` bytes (`aa 55 5a a5`, i.e. markers) — so the value cannot be decoded from flash directly, and this neither confirms nor rules out persistence. `mtd1` (`factoryParam`) is readable and contains `hw:1.1;date:2021.11.29;pcb:1.20;modif:usb;`. The authoritative read-back is app IPC code `814`, which reports `usbmode:<n>` — ask for it from the app/UI, or send code `813` with `usbmode:0` to restore the pre-incident value.

**Conclusion: the camera side is not presenting.** Power-cycle the K-3 III and re-seat the cable; then confirm `25fb:0189` appears under `/sys/bus/usb/devices/`. If it does not appear even after a known-good cable and a powered hub, set `usbmode` back to `0` — that persisted change is the only software-side difference between before and after your reboot.

## 4d. How to attribute the next occurrence

The dump has no caller: both `pc` and `lr` are zero, so the fault cannot be resolved to a function from the handler output alone. Two things close that gap:

1. **Core dumps are available.** `pgphoto`'s rlimit is `Max core file size unlimited`, and `kernel.core_pattern = core` (a relative path, so the core lands in the process CWD). The shell's own `ulimit -c` is 0, but the daemon inherits `unlimited`. Setting up a writable CWD or an absolute `core_pattern` before the next test will capture a full stack.
2. **Thread identity.** pgphoto runs 7 threads: `pgphoto.stage2o` (main), `ipc_msg_loop`, and five `sp_async_functi…`. The faulting stack is an 8 MB pthread stack, so it is one of the workers — most likely an `sp_async_function` worker doing the capture download while `ipc_msg_loop` serves LiveView. A core dump resolves this immediately; without one, adding the faulting thread's `comm`/TID to the crash handler would.

Note the handler only covers SIGSEGV/SIGBUS/SIGILL, and `/app/stage2-crash.log` held one entry at the time of writing despite 29 process starts in this boot — most deaths go unrecorded.

## 4e. Second crash captured at 13:35 — identical signature, same call depth

Pulled at 14:09 (`raw/stage2-crash-2entries.log`, log grew 9,690 → 19,298 bytes). The file is `O_APPEND`, so this is a genuine second fault:

| | crash 1 (12:12) | crash 2 (13:35) |
| --- | --- | --- |
| `sig` / `si_addr` / `pc` | 11 / 0 / 0 | 11 / 0 / 0 |
| `lr` | 0 | 0 |
| `r12` | `0x20` | `0x20` |
| faulting stack region | `b6113000-b6912000 rw-p` (8 MB pthread, guard `b6112000`) | `b6109000-b6908000 rw-p` (8 MB pthread) |
| **`sp` below stack top** | **`0x2960`** | **`0x2960`** |

Two different stack allocations, **identical depth below the top** — the same call chain reaching the same instruction. This is a deterministic fault at one site, not random corruption.

Both deaths occur in the same place: after the file event, before the download completes.

```
crash 1 @12:12:41  updateCameraAutoFocus enable:1 ret:0 → add file IMGP4050.DNG
                   captureImageEvent:0 Path:IMGP4050.DNG        <-- dies
crash 2 @13:35:22  updateCameraAutoFocus enable:1 ret:0 → add file IMGP4053.DNG
                   captureImageEvent:0 Path:IMGP4053.DNG
                   code[264] val[state:4;IMGP4053.DNG]          <-- dies
```

**LiveView is NOT the discriminator — an earlier draft of this section was wrong.** LiveView frames were streaming around surviving captures too, so their presence near both crashes proves nothing:

| capture event | LV frames in prior 10 s | last frame before | outcome |
| --- | --- | --- | --- |
| 12:00:38 | 4 | 2.6 s | survived, downloaded |
| 12:00:57 | 1 | 8.8 s | survived, downloaded |
| 12:12:41 | 5 | 4.2 s | **CRASH** |
| 13:33:15 | 0 | 17.3 s | survived, downloaded |
| 13:34:39 | 2 | 5.0 s | survived, downloaded |
| 13:35:22 | 3 | 6.0 s | **CRASH** |

The concurrency hypothesis (preview + download sharing one non-thread-safe `Camera*`) is **not supported** and has been retracted on #176.

## 4e-2. The actual discriminator: an in-flight focus/AF command (code 262)

Across all ten `captureImageEvent` occurrences in both sessions, the state of the app's focus/AF command (IPC code `262`, `val[mod:0;f:0;]`) at that instant separates crashes from survivors perfectly:

| session | event | pgphoto issued this capture? | code 262 unanswered? | download reached? | outcome |
| --- | --- | --- | --- | --- | --- |
| T1 | 12:00:38 | yes | no | yes | survived |
| T1 | 12:00:57 | yes | no | yes | survived |
| T1 | 12:03:00 | yes | no (cmd 12:01:36 / reply 12:01:42) | yes | survived |
| T1 | 12:08:40 | yes | no | yes | survived |
| T1 | 12:09:29 | yes | no | yes | survived |
| **T1** | **12:12:41** | **no — spontaneous** | **YES (cmd 12:12:41, last reply 12:01:42)** | **no** | **CRASH** |
| T2 | 13:33:15 | yes | no | yes | survived |
| T2 | 13:33:44 | yes | no | yes | survived |
| T2 | 13:34:39 | yes | no (cmd 13:34:28 / reply 13:34:34) | yes | survived |
| **T2** | **13:35:22** | **no — spontaneous** | **YES (cmd 13:35:22, last reply 13:34:34)** | **no** | **CRASH** |

**Crashes 2/2 had an unanswered code-262 in flight; survivors 0/8.** Code 262 is not instantaneous — it spans `enable:1 … enable:0` plus its own reply, roughly 6 s.

The decisive detail is **arrival order relative to `camera_autoFocus_enable 1`**:

```
SURVIVOR 13:34:28 — file event lands BEFORE enable:1, and is swallowed:
  recv code[262] val[mod:0;f:0;]
  --- change focus mode ret 0
  ---- add file  (IMGP4052.DNG)
  ---isClearEvents new file name IMGP4052.DNG     <- consumed, no captureImageEvent
  camera_autoFocus_enable 1
  updateCameraAutoFocus enable:1 ret:0
  updateCameraAutoFocus enable:0 ret:0
  send code[262] val[mod:0;f:0;ret:0;]            <- handler closed cleanly

CRASH 13:35:22 — file event lands AFTER enable:1 ret:0, handler still open:
  recv code[262] val[mod:0;f:0;]
  camera_autoFocus_enable 1
  updateCameraAutoFocus enable:1 ret:0
  ---- add file  (IMGP4053.DNG)
  captureImageEvent:0 Path:IMGP4053.DNG           <- PROCESSED, not consumed
  *** SIGSEGV pc=0 lr=0 ***                       <- enable:0 and the 262 reply never happen
```

Both crashes were also **spontaneous** file events — no pgphoto-initiated capture was pending (the last pgphoto capture had completed 3 min 12 s and 3 min 43 s earlier). Every pgphoto-initiated capture survived. So this is a re-entrancy window inside the AF handler, not a capture-path bug.

**Confidence.** High: the fault is deterministic (identical registers, identical `sp` offset `0x2960` below stack top on two different 8 MB pthread stacks) and correlates perfectly with an in-flight code-262 handler. Not proven: that the handler *causes* it — n=2 crashes, and `pc=0`/`lr=0` give no caller. The `isClearEvents` path may be doing genuine protective work and should be understood before any change.

**Where to look (for discussion; no fix written).** (1) pgphoto's AF/focus handler — stock/closed-source, window is between `enable:1 ret:0` and `enable:0`; `container/analyze_pgphoto.py` already locates structural sites inside pgphoto functions, which is the precedent. (2) Our Stage-2 shim layer — we hook `gp_camera_init`, `capture_preview`, `get_single_config`, `set_config`, `set_single_config`; none is on the AF path, so a fix here means serialising session use at a boundary we do control. (3) libgphoto2 pentax/ptp2 — we own that fork and fixed a real UAF there (`ab0de090c`, companion-buffer ownership, see `docs/HANDOVER-2026-09-23-O-V12M-COMPANION-UAF.md`), but that crash had `si_addr=0xae579008 pc=0xb6c50878` — a freed pointer, not null, so likely a different root cause.

**Needed before choosing:** a core dump (pgphoto rlimit is already `unlimited`; only `kernel.core_pattern` needs an absolute writable path) plus the faulting thread's TID/`comm` in the handler output.

## 4e-3. Strongest candidate: a duplicate "new file" announcement for an already-downloaded file

Tabulating every `New file is in location` line gives a cleaner predictor than §4e-2. Each capture is announced **twice** — once shortly after the shutter (usually short path `/IMGPxxxx.DNG`), then again later with the real folder path `/store_00010001/DCIM/510_1103/IMGPxxxx.DNG`. The second is a re-announcement of a file pgphoto has **already downloaded**.

```
T1  3147 /IMGP4046.DNG                          -> captureImageEvent 12:00:38 -> download ret=0
T1  3583 /store_.../IMGP4047.DNG                -> captureImageEvent 12:00:57 -> download ret=0
T1  3971 /store_.../IMGP4048.DNG                -> captureImageEvent 12:03:00 -> download ret=0
T1  4487 /IMGP4049.DNG                          -> captureImageEvent 12:08:40 -> download ret=0
T1  5739 /store_.../IMGP4049.DNG  <-- DUPLICATE -> ---isClearEvents (consumed)     SURVIVED
T1  5750 /IMGP4050.DNG                          -> captureImageEvent 12:09:29 -> download ret=0
T1  6629 /store_.../IMGP4050.DNG  <-- DUPLICATE -> captureImageEvent 12:12:41      *** CRASH ***

T2  2321 /IMGP4051.DNG                          -> captureImageEvent 13:33:15 -> download ret=0
T2  2441 /IMGP4052.DNG                          -> captureImageEvent 13:33:44 -> download ret=0
T2  2899 /store_.../IMGP4052.DNG  <-- DUPLICATE -> ---isClearEvents (consumed)     SURVIVED
T2  3002 /IMGP4053.DNG                          -> captureImageEvent 13:34:39 -> download ret=0
T2  3720 /store_.../IMGP4053.DNG  <-- DUPLICATE -> captureImageEvent 13:35:22      *** CRASH ***
```

| announcement | count | outcome |
| --- | --- | --- |
| first time for that filename | 8 | all survived, all downloaded `ret = 0` |
| duplicate, swallowed by `---isClearEvents` | 2 | both survived |
| **duplicate, processed via `captureImageEvent`** | **2** | **both crashed** |

This subsumes §4e-2: the AF-handler correlation is a side-effect, because whether `isClearEvents` fires depends on arrival order relative to `camera_autoFocus_enable 1`. Both crashes re-announce a file whose download had already completed (`IMGP4050.DNG ret = 0` at 12:09:29; `IMGP4053.DNG ret = 0` at 13:34:39), so processing it a second time plausibly walks an already-released handle/buffer — consistent with a null branch target and `lr = 0`.

**Caveats.** n = 2 crashes; the predictor is perfect on available data but the sample is small. Mechanism (which pointer is null, and where) is unproven. Path form alone is not the discriminator — T1's IMGP4047/4048 were full-path *first* announcements and survived; duplicate-ness is what matters. Where the duplicate originates (a second `wait_for_event` source, a folder rescan, or the camera re-sending) is unknown and should be established before choosing a fix.

**Fix options (none written).** (1) Deduplicate in pgphoto's file-event path — smallest conceptual change, but stock closed-source, needs a binary patch; `container/analyze_pgphoto.py` already locates structural sites inside pgphoto functions. (2) Make the existing `isClearEvents` guard robust so duplicates are always consumed regardless of arrival order — arguably restores intended stock behaviour. (3) Stop the duplicate at source once its origin is identified. (4) libgphoto2 pentax/ptp2 only if the null pointer lives there; the earlier companion-buffer UAF (`ab0de090c`) died after `captureImageEvent` too but with `si_addr=0xae579008 pc=0xb6c50878`, a freed pointer not null, so likely a different root cause.

**Blocking unknown:** which thread faults and the call chain. Get a core dump (absolute writable `kernel.core_pattern`; pgphoto's core rlimit is already `unlimited`) plus faulting TID/`comm` in the handler output before choosing between 1–3.

Also visible immediately before crash 2: a failed Bulb set (`Failed to set new configuration value 1 for configuration entry bulb`, `captureBulbImage ret -6`) followed by repeated `config-safety: exposurecompensation widget has 0 choices; returning CAMERA_BUSY`. The empty-choice guard is doing its job, but the camera is clearly in a degraded config state at the time of death.

## 4f. Astro WebUI did not autostart after the reboot — cause and fix

`/app/astro` was empty and nothing was listening on `:8090`. Root cause: **the Astro boot hook lives at `/app/network_telnetd.sh`, and flashing v94 replaced `/app`, deleting it.** The installer (`install_astro.sh`) copies `polaris-astro-boot.sh` to that path, so any reflash silently removes the autostart hook.

Manual restart (verified working — `polaris-httpd --port 8090` came up):

```sh
setsid sh /app/sd/polaris-astro/polaris-astro-boot.sh </dev/null >/tmp/astro-boot.out 2>&1 &
```

To restore autostart, re-run the installer or simply copy the hook back:

```sh
cp /app/sd/polaris-astro/polaris-astro-boot.sh /app/network_telnetd.sh
chmod 755 /app/network_telnetd.sh
```

Worth adding to the release process: any step that replaces `/app` must reinstall `/app/network_telnetd.sh`, or Astro silently stops starting on boot.

## 4g. Log-loss mitigation now in place

`/app/Clog.txt` truncated to 0 bytes at 13:44 when the watchdog restarted pgphoto — the death scene is only recoverable because it had already been copied off. Added `scripts/tail-polaris-logs.sh`, which mirrors `Mlog.txt`, `Clog.txt` and `stage2-crash.log` into numbered snapshots every N seconds and flags the snapshot in which a new crash entry appears. It fetches each file with `dd` rather than tarring the directory, because the SD card's FAT chain has a bad cluster that aborts whole-directory tars (`fat_bmap_cluster: request beyond EOF`).

## 5. Diagnostic defect found while reading the crash log

`container/stage2_loader.c` classified `pc == 0` as an unfilled-slot null jump unconditionally:

```c
if (pc == 0) {
    s_write("NULL jump (an unfilled slot == 0 was called -- exactly the "
            "pre-fix race)\n");
}
```

Two things were wrong with that. First, it never consulted the slot words, so it could not tell an unfilled-slot call from a null call made *inside* an already-resolved target. Second, since Session 18 the fail-closed baseline seeds **every** slot with `&stage2_abort_stub` before `dlopen`, so a call to a slot that was never resolved lands on the stub (`pc == stub`) and is reported by the existing `== stage2_abort_stub` branch — a literal `0` slot word is only observable in the window before that seeding pass publishes. The message therefore named a condition that, in this build, could not have produced `pc == 0` at all.

**Fixed in this session.** The handler now scans the slot words (plain volatile loads, signal-safe) and reports which case it found:

```
pc classify: NULL jump with ALL slots non-zero -- NOT the pre-fix unfilled-slot
race; the null call is inside a resolved target (upstream/core fault). Resolve
pc/lr against the maps below.
```

or, if a slot really is still zero, names it and counts how many. Verified by host-side `gcc -fsyntax-only -std=gnu11 -Wall -Wextra`: the edited file produces exactly the same diagnostics as `HEAD` (the seven pre-existing `unused variable 'lr/sp/r0..r12'` warnings that appear only under `-DSTAGE2_NO_CONSTRUCTOR`, where the ARM register prints are compiled out). The real gate, `container/test_stage2_loader_compile.sh`, reports `SKIP: arm-linux-gnueabi-gcc not found` in this environment and still needs to run on a machine with the ARM cross-toolchain.

## 6. Secondary observation: Wi-Fi driver buffer exhaustion

`dmesg` contains **422** occurrences of:

```
_tdata_psh_info_pool_deq 200: Out of tdata_disc_grp
dhd_tcpdata_info_get 1056: No more free tdata_psh_info!!
```

This is the SoftAP TCP buffer pool running dry — the signature behind #55, where LiveView streaming starves the radio. `STAGE2_PENTAX_PREVIEW_BACKOFF=1` is set in the live process environment (`/proc/1063/environ`), so the backoff is active and still did not prevent exhaustion in this session.

## 7. Positive result: the pending guard works

The uncommitted `stage2_reject_empty_choice_widget()` change is deployed on the device and fired **87 times** for `exposurecompensation` returning `GP_OK` with a zero-choice RADIO widget, between 12:00:12 and 12:03:00. Every one was converted to `-110 CAMERA_BUSY` instead of being serialised as `RD:0;V:;R:;` for `polestar_app` to index blindly. The firings stop at 12:03:00 and the session then becomes healthy (ISO/shutter/aperture/whitebalance all return populated choices at 12:12:32). This is the first on-hardware confirmation that the empty-choice path occurs in the wild and that the guard suppresses it.

## 8. Live state at capture time

```
249 root  ./polestar_app
1063 root /app/lib/stage2/pgphoto.stage2ondisk      (owns :8080)
USB: 1a40:0101 hub, 1d6b:0002, 1d6b:0003            (no 25fb:0189)
/app/Clog.txt                                        0 bytes, mtime 12:22
/app/sd/system/log                                   readable per-file; whole-dir copy fails (bad FAT chain)
```

## 9. Next steps

1. **Physical**: power-cycle the K-3 III, re-seat the cable, confirm `25fb:0189` returns to `/sys/bus/usb/devices/*/idVendor`. Nothing else can proceed until then.
2. ~~Fix the §5 misclassification~~ **Done in this session** (`container/stage2_loader.c`). Needs a rebuild and reinstall before the next physical test, and `container/test_stage2_loader_compile.sh` still has to pass on a machine with the ARM cross-toolchain.
3. The wedged-session path (§4 step 1) has no recovery that works: refusing the USB reset is correct for a healthy camera but leaves a crashed-process session permanently stuck. Needs a bounded, state-verified recovery distinct from the blanket refuse.
4. Re-run the capture that triggered this (IMGP4050.DNG, `captureImageEvent` → download) with the corrected handler in place to see whether the null call is reproducible and which core function owns it. The `maps` dump plus the new classification line should attribute it directly.

## 10. Raw files

| file | contents |
| --- | --- |
| `raw/stage2-crash.log` | SIGSEGV dump: registers, slot-region classification, checkpoint, full `/proc/self/maps` |
| `raw/Clog_000355.log` / `.clean.txt` | gphoto side, 11:58–12:15 incl. crash and the 87 guard firings (`.clean` = ANSI stripped) |
| `raw/Mlog_000355.log` | app side to 12:15:38 `HDMI_REBOOT`, incl. `pgphoto is exit,reboot it` |
| `raw/Clog_000356.log` | post-reboot pgphoto start, `-5` port-not-found, restart-successful |
| `raw/Mlog_000356.log` / `.clean.txt` | app side after reboot |
| `raw/Mlog-current.txt` | live `/app/Mlog.txt` tail |

Fetched with per-file `dd` over SSH: a whole-directory copy from `/app/sd/system/log` aborts on a bad FAT chain, so each file is pulled individually.
