# The ~60 s notification delay — static search, and why the obvious hypothesis is wrong

Goal (from #191): find the fixed ~60 s constant that delays the 773 file-list
notification while the file is already on the card. No hardware required.

Binaries: `out/o-v15j-.../ubifs/bin/polestar_app` (24 MB, ARM EABI5, not
stripped, with debug_info) and
`out/stage2-ondisk/ondisk/pgphoto.stage2ondisk` (7.8 MB, same). Tooling:
`arm-linux-gnueabi-objdump` (host `objdump` has no ARM target and silently
disassembles ARM as x86 — see `docs/evidence/bulb-root-cause-20261005/SUMMARY.md`).

## 1. Where the notification comes from

The 773 payload format string is `type:%d;path:%s;size:%d;cTime:%s;duration:%d;`
at `0xa47f74` in `polestar_app`. The emitters are:

```
SP_MediaSendFileListToApp  0x31338   -> NormalFileListSend / NestFileListSend
  called only from:
MediaMsgProcTask           0x31ed8
```

`MediaMsgProcTask` is a message-dispatch loop: it `sscanf`s a request, calls the
matching `SP_*Send*ToApp`, and loops.

## 2. The task waits on an UNTIMED condition variable — so it cannot be the 60 s timer

At `0x32114`, the wait the notification task blocks on:

```
32114:  mvn  r1, #0            ; r1 = -1
32118:  ldr  r3, [pc, #112]    ; &media_msg_cond
3211c:  add  r3, pc, r3
32120:  add  r0, r3, #24
32124:  bl   33e54 <SP_ThreadCondWait>
```

`SP_ThreadCondWait` @ `0x33e54` branches on exactly that argument:

```
33e7c:  cmn  r3, #1            ; timeout == -1 ?
33e80:  bne  33ea4
33e9c:  bl   pthread_cond_wait ; <-- untimed, taken for -1
        ; else: clock_gettime + ms->tv_sec/tv_nsec math -> pthread_cond_timedwait
```

**The notification task waits forever.** A lost wakeup there would hang
indefinitely, not for 60 s. So the delay is *not* a timeout in the notifier —
whatever rescues it fires elsewhere and then signals this task.

## 3. Every 60000 constant in both binaries is unrelated

| binary | site | owner | verdict |
|---|---|---|---|
| `polestar_app` | `movw r1,#60000` @ `0x71bd0` | `LapseTask` | timelapse, not capture |
| `polestar_app` | `movw r1,#60000` @ `0x78be0` | `PanoramaTask` | panorama, not capture |
| `polestar_app` | `.word 0xea60` ×4 | `Curl_init_userdefined`, `ftp_timeleft_accept`, `AllowServerConnect`, `ftp_done` | libcurl timeouts |
| `pgphoto` | `.word 0xea60` ×3 | `xmlNanoHTTPRecv`, `xmlNanoHTTPConnectAttempt`, `xmlNanoHTTPSend` | libxml2 HTTP |

No 60 s constant exists in the capture or notification path, and no `#60`
seconds-scale immediate anywhere in `polestar_app`.

## 4. What the capture path does have: a 1-second poll and a computed deadline

`action_camera_wait_event` @ `0xf0800` in `pgphoto` polls on a 1 s cadence:

```
f0874:  movw r3, #16960 ; movt r3, #15   ; 0xF4240 = 1 000 000 us = 1 s
f0d40:  movw r3, #16960 ; movt r3, #15   ; elapsed = (now-start) in us / 1e6 -> seconds
```

and compares against a caller-supplied deadline. Separately, and already
documented, `SP_SetPhotoRecodeState` @ `0x57ac8` computes a capture deadline:

```
ctx+0x180 = bulb_ms + 30048                      ; bulb request
ctx+0x180 = f(ctx+0x11c) * K + 30000 + 48        ; normal capture
```

Neither is 60 s. The 1 s poll granularity is, however, consistent with the
observed 61 s landing on a whole-second boundary: a rescuer driven by this loop
would fire on a tick, not at an arbitrary offset.

## 5. Verification that the file really was ready early (not a clock artefact)

The concern was that `cTime` might be stamped when the notification is built,
which would make the whole "file was ready at +3 s" inference collapse. It is
not: `SP_MediaSendFileListToApp` calls only `SP_GetNormalAttr` /
`SP_GetHdrAttr` / `SP_GetLapseAttr` / … — it reads attributes recorded at
capture time. Had `cTime` been "now", the stalled runs would have reported
`15:07:09`, not `15:06:11`. They report `15:06:11`, i.e. **state:4 + 3 s**,
while the notification is delivered at 14:07:09 UTC. The file was ready early and
the client was told late. That part of #191 stands.

## 6. Revised conclusion

- **Refuted:** "a fixed ~60 s timeout in the download/notification path." The
  notification task has no timeout at all.
- **Confirmed:** the file is ready ~3 s after `state:4`; only the notification is
  late; the delay lands on whole seconds (61.0 s), consistent with the 1 s poll
  loop in `action_camera_wait_event`.
- **Narrowed:** the delay is in whatever *signals* `MediaMsgProcTask` — i.e. the
  capture-completion path in `pgphoto`/libgphoto2, not the app-side notifier.
  The next static step is to find the callers of `action_camera_wait_event` and
  the deadline they pass; it is reached only through a function-pointer/vtable,
  so a plain `bl` scan does not find it.

## 7. Practical consequence, unchanged and now stronger

Because the fix is not a one-line constant, the client-side mitigation is the
fastest route to stability: **on a `state:4` timeout, check whether the expected
file appeared before declaring failure, and do not retry blindly.** That converts
a ~7 % false-failure rate into a correct result without touching firmware, and it
also covers the unrelated 19 s no-reply window (#182).
