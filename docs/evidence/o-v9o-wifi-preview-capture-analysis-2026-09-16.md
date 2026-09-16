# o-v9o Wi-Fi, preview, and capture-notification analysis

Date: 2026-09-16

## Current live result

The K-3 III remains attached as USB `25fb:0189`. `polestar_app` and
`pgphoto.stage2ondisk` retain their PIDs, and ports 8080 and 9090 remain
listening.

Preview is currently ON because the `192.168.0.2` client re-enabled and owns an
8080 stream. Over a 30-second passive sample:

- 15 valid Pentax preview frames completed: approximately 0.5 frames/s;
- typical frame size was 70-72 KiB;
- each sampled camera frame used one attempt and took 15-16 ms at the Pentax
  get-frame stage;
- wlan0 transmitted 1,138,199 bytes: approximately 37.9 KiB/s;
- the Broadcom error counters remained fixed at 936
  `No more free tdata_psh_info!!` and 935 `Out of tdata_disc_grp` events.

This is a current preview data-plane PASS at modest cadence. It is not a clean
single-client soak: active connections were:

```text
192.168.0.4 -> 9090
192.168.0.2 -> 9090
192.168.0.2 -> 8080
```

The previous shutter release also produced and retained
`/app/sd/normal/SP_0042.dng` at 28,198,130 bytes. The physical exposure and file
write therefore hold up. The notification/reconciliation path remains
incomplete: wire states were `1 -> 4 -> 0`, not the roadmap's expected
`1 -> 4 -> 2 -> 3 -> 5`.

## Wi-Fi failure mechanism

The two kernel messages are from Broadcom DHD TCP ACK suppression bookkeeping,
not camera or PTP errors. Upstream DHD source defines only four tracked TCP data
flows and a pool of 32 PSH records (`8 * 4`). Each received PSH segment consumes
a record. Records are returned when outgoing ACK progress covers the stored end
sequence; inactive flow entries are aged after 5,000 ms. Exhaustion makes
`dhd_tcpdata_info_get()` return an error and produces the observed log pair.

Multiple long-lived and reconnecting 8080/9090 clients increase flow churn and
PSH pressure. Preview is a load trigger because it is the largest sustained TCP
stream, but it is not proven to be the sole cause. The current 30-second sample
shows healthy preview traffic without new errors; the 1,871 historical messages
show that the same boot previously crossed the pool boundary.

The deployed `bcmdhd` module exposes no TCP-ACK-suppression parameter under
`/sys/module/bcmdhd/parameters`. Disabling or resizing this subsystem is
therefore a kernel/module rebuild, not a safe runtime tuning change.

Primary-source references:

- Google Android bcmdhd `dhd_ip.h`: four flows, 32 PSH records, 5,000 ms aging.
- Google Android bcmdhd `dhd_ip.c`: allocation, ACK-based reclamation, aging,
  and the exact pool-exhaustion path.

## Other failure and performance findings

### 1. Code 266 is not capture state on this live firmware

OpenPolaris sends 266 every two seconds and labels it `CAM_GET_STATE`. On this
device, the live response is a complete white-balance/config result:

```text
266@RD:0;V:0;R:Automatic,Daylight,Cloudy,...,Tungsten,;
```

Clog confirms `camera_control_handler command 29 info whitebalance ret 0` and
`getCameraConfig configType 1 ret 0`. This poll:

- adds avoidable camera/PTP work every two seconds;
- cannot supply the `state:` field the client expects;
- must not be used to declare capture completion;
- competes with preview and still capture through the global camera scheduler.

Highest-priority client fix: remove periodic 266 polling for this firmware and
drive capture lifecycle from unsolicited 264 events plus 773 file events. If a
fallback poll is needed, first live-map a real capture-status opcode and gate it
by firmware/build identity.

### 2. Preview needs one explicit owner

The transport correctly validates complete JPEGs and conflates UI state to the
latest frame. It does not coordinate ownership between desktop, phone, probes,
or reconnect generations. Performance testing must use one 9090 owner and one
8080 owner. Product behavior should enforce one local preview job, close the old
HTTP stream before reconnect, and prevent hidden/background panes from retaining
preview.

### 3. Pause preview and camera/config polling around still capture

Preview and capture share the proprietary pgphoto scheduler. A still sequence
should explicitly stop 291/8080, wait for confirmed preview-off, suspend camera
parameter polling, release the shutter, observe 264/773 lifecycle completion,
then restore preview once. This reduces simultaneous PTP and TCP pressure and
makes failures attributable.

### 4. The 9o preview and capture guards share state

`container/stage2_loader.c` uses the same
`g_pentax_preview_timeouts` and `g_pentax_preview_backoff_until` globals for
preview and still capture. A successful preview resets both, which can erase a
capture-failure cooldown; capture failures can also suppress preview. Split the
counters/cooldowns and add separate log labels and tests.

### 5. Poll less and prefer pushes

The desktop app currently sends 284 and 517 every second, 266 every two seconds,
and 286 every five seconds. The small control frames are not the dominant byte
load, but retries and camera-backed polls add scheduler work. Recommended:

- remove the invalid 266 loop;
- use pushed 284/517 data where available;
- back off unchanged status polling while preview/capture is active;
- jitter or coalesce periodic reads rather than issuing synchronized bursts;
- retain a low-rate liveness ping independently of camera configuration reads.

## Recommended implementation order

1. OpenPolaris: remove/gate 266 capture polling and base completion on 264 + 773.
2. OpenPolaris: single-owner preview lifecycle; stop preview and camera-backed
   polling during capture, then restore once.
3. Patcher: split preview and capture backoff state and instrument counters.
4. Qualification: single-client preview-off capture, then one-client preview
   soak, then labelled multi-client stress; record DHD counter deltas and frame
   cadence for each phase.
5. Only if workload control still exhausts the pool, investigate a provenance-
   controlled bcmdhd rebuild that disables delayed ACK suppression or increases
   the pool. This is the highest-risk option and requires radio regression
   testing; printk suppression only hides console cost and is not a repair.
