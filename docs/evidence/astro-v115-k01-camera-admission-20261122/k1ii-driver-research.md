# K-1 II driver research — root causes + performance (v115, 2026-11-23)

Body: PENTAX K-1 Mark II fw 2.51, USB 25fb:0183, "Pentax K-1 Mark II (PTP mode)".
Driver: host x86 build of exact v115 pin 0f2f34e00040. Exposure mode Manual.
All findings reproduced direct-PC with PTP traces captured.

## R1 — imageformat/imagequality -102: EXACT root cause (fixable, driver-side)
The Pentax imageformat write is a compound read-modify-write of DPC 0xd01b
(WritingFileFormat). Flow in _put_Pentax_ImageFormat (config.c):
  1. _pentax_readiness_preflight -> GetAllConditions 0x900f (OK)
  2. _pentax_wff_read_payload -> GetPropValue 0xd01b, then a fail-closed guard
  3. pentax_wff_set_format -> ptp_pentax_set_device_prop_raw (0x1016 write)

The K-1 II returns 0xd01b as a **6-byte** payload:
    06 00 50 03 00 01 01   (size field 0x06, then 50 03 00 01 01)
But pentax_wff_payload_is_valid() hard-requires size == 10 or 11:
    if (!payload || (size != 10 && size != 11)) return 0;
So _pentax_wff_read_payload returns GP_ERROR_CORRUPTED_DATA (-102) and step 3
never runs. Trace confirms ZERO 0x1016 ops were sent — the failure is entirely
local, before any write.

Note byte0 = 0x06 = size-4, so the driver's OWN invariant (payload[0]==size-4)
already holds for this body; only the fixed 10/11 window is wrong. The guard was
written for a different Pentax payload form (#54/#55).

FIX: accept the K-1 II's actual 0xd01b shape. Either widen the size window to
include the 6-byte form (and map its byte layout), or special-case model_no for
K-1 II fw 2.51. Must preserve unrelated bytes per #54/#55 intent. This unblocks
JPG+RAW (#386) on both K-1 II and likely K-3 III (same -102).

## R2 — MF drive 0xa00c: EXACT code identity (needs one hardware check)
Both bodies reject the focus op with vendor response 0xa00c:
  - K-3 III: PTP_OC 0x9017 (FocusControlNew) -> 0xa00c
  - K-1 II:  PTP_OC 0x9016 (FocusControl, old family / #303 path) -> 0xa00c
0xa00c is DEFINED in the driver itself as PTP_RC_NIKON_MfDriveStepEnd ("MF drive
reached its step/limit end"). Pentax reuses that vendor code. translate_ptp_result
has no mapping for it, so it reports "unmapped PTP result code 0xa00c reported as
generic error" and the widget write returns -1.

Two possibilities, not yet distinguishable headlessly:
  (a) 0xa00c means "already at limit / nothing to do" -> the drive is actually
      working and #381 is partly a false-positive reporting bug.
  (b) 0xa00c is a genuine reject for this payload shape.
pentaxconditions has no focus-position field, so lens movement cannot be read
back over PTP. Needs either a focus-distance proxy or a visual/physical check on
the mount. Regardless, the driver should map 0xa00c to a meaningful message
instead of "generic error" — that alone improves BenroConnect UX and diagnosis.

## R3 — Performance: full widget tree rebuilt on EVERY command (7.85s / 62 ops)
Measured direct-PC on K-1 II:
  - one --list-config:            7.85 s
  - one --get-config (single):    7.86 s   <-- identical cost for ONE widget
PTP ops issued for a SINGLE get-config:
    30 x GetDevicePropDesc (0x1014)
    18 x GetPropValue      (0x1015)
     5 x GetAllConditions  (0x900f)
     3 x GetObjectHandles  (0x1007)
     2 x GetDeviceInfo     (0x1001)
     1 each Open/Close session, GetStorageIDs, 0x9001
Total ~62 round-trips to answer one question. The driver builds the entire widget
subtree on every gp_camera_get_config regardless of which widget is requested.

This COMPOUNDS #369 (Stage-2 enumerates one property at a time): Stage-2 calls
get_single_config per property, and each such call re-pays the full 62-op tree
build. That is the dominant K-1 II latency source, larger than #369 alone.

FIX directions (perf):
  - Cache GetDevicePropDesc results per session; do not refetch all 30 descriptors
    on every get_config. The driver has devprop caching but it is flushed (see
    "cached devprop should have been flushed" comments in library.c).
  - Build the widget tree once per session and reuse across get/set calls.
  - For Stage-2, batch reads via GetAllConditions 0x900f where a value is derivable
    from conditions instead of a per-property GetPropValue (#369).
Expected: single-widget read drops from ~7.8s to sub-second once descriptors are
cached; UI refresh round-trips drop from 30-50+ to a handful.

## R4 — Confirmed working on K-1 II (do not regress)
iso, whitebalance, shutterspeed, aperture: write + readback + body-state proof via
GetAllConditions (ISO=400 seen in conditions, not just gphoto cache). 51 widgets,
zero empty arrays. Live-view zoom writes WORK here (2x/off round-trip), unlike K-3
III (#384 is K-3 III-specific).

## R5 — Capture/preview unavailable direct-PC (body limit)
--capture-image and --capture-preview both -6; body advertises no 0x4006. #316/#317
must be qualified on the Polaris lane via wire code 264 after v115 installs.

## Open items to exhaust tonight
- Confirm R2(a) vs R2(b) with a focus-position proxy or physical check.
- Measure live-view frame fetch cost and whether pclvkeep reduces per-frame setup.
- Enumerate advertised-but-unpublished properties (missing widgets).
- Test pentaxdrivemode 23-choice writes for silent no-ops like K-3 III peaking.

## R4 — Exact perf fix site (located in source; NOT yet implemented or tested)
Per-widget cost comes from `_get_Pentax_DirectProperty` (config.c ~9615). For each
property it issues:
  1. `ptp_generic_getdevicepropdesc()` — **cached** via `params->dpd_cache` with
     `params->cachetime` TTL (ptp.c:4901).
  2. `ptp_pentax_get_device_prop_desc_raw()` — **uncached**, a fresh
     `PTP_OC_GetDevicePropDesc` transaction every call (ptp.c:1980).
  3. `ptp_pentax_get_device_prop_raw()` — **uncached**, a fresh
     `PTP_OC_GetDevicePropValue` every call (ptp.c:1966).

Steps 2 and 3 bypass the cache entirely, which is why ops scale linearly with
widget count (63 -> 489 for 1 -> 10 widgets) instead of being paid once.

### Why a naive cache would be WRONG here (do not "optimise" this blindly)
Pentax descriptor *contents* are mode-dependent, proven by this same round: in
Bulb the shutter enum contains only `mm:ss` values (00:01..20:00) and **zero**
fractional entries, while other modes expose fractions. Caching a raw descriptor
across a mode change would hand clients a stale choice list — the exact class of
"slider shows values the body rejects" bug this project already tracks (#316).

Therefore any caching must be keyed on, or invalidated by, shooting mode /
drive state. Step 3 (the *value*) must never be cached: it is live body state.

### Status
Located and reasoned only. No patch applied, no measurement of improvement,
because both bodies went unresponsive (every PTP op times out) before a build
could be validated. Implementing without a responsive camera would ship an
unverified change to the packaged driver, which the release-integrity rules
forbid. Requires: responsive body -> build in the registered worktree
(exp/k1ii-driver-perf) -> measure ops+wall-clock before/after -> confirm choice
lists still track mode changes.

## R5 — "Unresponsive camera" was actually PTP_RC_DeviceBusy (0x02fa), not sleep
Earlier I described the bodies as "asleep or powered off". That was wrong. With a
long-enough timeout the K-1 II answers, and the driver reports:

    Pentax init stage OpenSession attempt 1, session 1, returned 0x02fa.
    Pentax state is busy or unknown; refusing session close and USB reset.

`0x02fa` is `PTP_RC_DeviceBusy`. The body is powered and on the bus; it is
declining a new session. Per docs/pentax-mode-aware-liveness.md, busy is a
legitimate post-capture state (dark-frame NR, pixel-shift processing, RAW/JPEG
production, Bulb/astro) and must not be treated as a failure. The driver's
refusal to force-close the session or reset USB is deliberate safety behaviour,
so polling within an expected envelope is the correct response — not a reset.

### Consequence for my earlier measurements
The runs I misread as "fast" (low op count, high wall clock) were sessions that
never completed because OpenSession was refused/timed out. That is exactly why
op counts looked small. Recorded here so the reasoning error is not repeated:
**a low PTP op count alongside a high wall clock means the session failed, not
that the driver was efficient.** Always check gphoto2's own exit code and look
for `returned 0x02fa` / `Timeout` before interpreting timing.

### Also corrected: my perf attribution
The raw Pentax descriptor fetch is a *fallback* (only when the generic call
fails), so it is not the source of the 30 descriptor ops. The source-confirmed
mechanism is `params->cachetime` defaulting to 2 s (library.c:12086) while one
full widget walk spans ~7.95 s, so cached descriptors expire mid-walk and are
refetched. Not every refetch is explained by TTL expiry — gaps as short as
+1.409 s occur inside the window, implicating the `timestamp = 0` invalidation
sites (ptp.c:3744, 5032, 6111), which I have not yet traced.

## R5 - Perf root cause: RESOLVED as far as source allows (no patch applied)
Mechanism confirmed from source + retained healthy logs:
- `params->cachetime` defaults to 2 s (library.c:12086); cache test is
  `timestamp + cachetime > now` (ptp.c:4901). One full widget walk spans ~7.95 s,
  so descriptors expire *during* the walk and are refetched. Propcode 0xd01e in one
  process: 2.603 / 4.958 / 6.367 s (gaps +2.355, +1.409).
- All three `timestamp = 0` invalidation sites are event/set-driven and do NOT fire
  on a read-only walk: handle_event_internal (PTP_EC_DevicePropChanged),
  ptp_generic_setdevicepropvalue, ptp_fuji_getevents. `ptp_check_event` is only
  called from camera_canon_capture / camera_sony_capture - never the get_config path.
- `duplicate_DevicePropDesc` (ptp-pack.c:965) is a DEEP copy, so the cache is not
  corrupted by callers freeing their copy. It also copies CurrentValue, which means
  cached descriptors carry live values - another reason naive caching is unsafe here.

### Still unexplained (recorded, not guessed)
One refetch in the 10-widget run (t=6.508 after t=5.257, gap 1.251 s < TTL) should
have been a cache HIT. I could not identify the cause from source and have NOT
invented one. Needs a responsive body plus a `cachetime` A/B to characterise.

### Cheapest experiment when hardware is available (no code change)
`cachetime` is read from the gphoto2 settings file (`ptp2/cachetime`). Set it to 30
and compare `0x1014` counts + wall clock for 1 vs 10 widgets. If ops drop, TTL expiry
is the dominant cost and a mode-keyed cache is the real fix; if not, the unexplained
invalidation matters more.

## R6 - Multi-model review outcome (LM Studio)
Roster: `qwen3-coder-next` and `qwen3.8_4b_distilled_gguf` load and respond. Every
`qwen3.8-flash-next` variant SIGABRTs on model load in this install, so it could not
be used as primary despite being the requested choice. The coding model's top
hypothesis (cache invalidation during walk) was REFUTED by my own source reading
above; its secondary point (deep-copy semantics) was confirmed. Model output is used
only to generate candidates - nothing is published without independent verification.

## R7 - Perf A/B: VALIDATED, and my earlier A/B was invalid (corrected)
My first cachetime A/B was worthless for two independent reasons, both mine:
1. I edited `~/.gphoto/settings`, but libgphoto2 prefers `$XDG_CONFIG_HOME/gphoto/settings`
   and only falls back to the legacy path if the XDG file does not exist.
2. I wrote INI syntax `[ptp2]\ncachetime=30`. `verify_settings()` (gphoto2-setting.c:245)
   requires **two** `=` per line (`section=key=value`) and *unlinks* the file when format
   is wrong - which is why the file disappeared mid-session.
Correct form is a single flat line: `ptp2=cachetime=30`.

### Valid A/B (isolated XDG_CONFIG_HOME=/tmp/gpconf, live K-1 II fw 2.51, pin 0f2f34e00040)
| cachetime | 10 widgets, one process | 0x1014 fetches | driver confirmed read |
|---|---:|---:|---|
| 2 (default) | 49.66 s | 263 | `read cachetime 2` |
| 30          | 27.12 s |  72 | `read cachetime 30` |

Descriptor expiry accounts for **22.5 s of 49.7 s** (~45%) and 191 of 263 fetches.
This independently reproduces codex's result (8.26->6.62 s single, 58.5->30.3 s ten,
278->74 fetches). Codex's numbers stand; my invalid A/B is retracted.

### Right approach for K-1 II performance (ordered, evidence-based)
1. **Session reuse first.** Every cost above is paid per process. A persistent pgphoto-style
   daemon pays vendor-enable + one descriptor walk once, then ~0 s per control. This is the
   single largest win and needs no libgphoto2 change.
2. **Raise cachetime for read-only enumeration**, but NOT globally: descriptors carry
   `CurrentValue` (duplicate_DevicePropDesc copies it) and Pentax enums are mode-dependent
   (Bulb shutter enum has zero fractional values). A blanket long TTL serves stale choice
   lists - the #316 failure class. Correct fix is a **mode-keyed cache**: invalidate on
   shooting/drive/exposure-mode change, not on wall clock.
3. **Then** trace the residual 72 fetches / 222 non-descriptor requests that remain at
   cachetime=30 - that is the next target codex identified and I agree with it.

## R8 - v115 install: radio cannot sustain bulk transfer (measured tonight)
- Control plane healthy: `ssh 'echo ok'` and `df` return in <2 s; polestar answers 9090.
- Bulk writes fail at every scale: 20 MB to `/dev/null` = 1041 s then `send disconnect:
  Connection timed out`; 1 MB chunks each hit a 90 s timeout (~0.01 MB/s).
- Chunking does NOT help - this is bcmdhd TCP bookkeeping exhaustion under sustained load
  (see memory summary k1ii-wireless-clog-bcmdhd-pool-exhaustion), not tar/vfat/ssh keepalive.
- Therefore the installer's single 86 MB `tar czf - | ssh 'tar xzf'` stream cannot succeed
  while the K-01 starves the radio. 12 attempts, all INSTALL_EXIT=255 at staging.
- **Route A is the answer** (docs/FIRMWARE-INSTALL-PROCESS.md:202): place `FwPkt/` on the SD
  card and reboot - the watcher consumes it with zero network transfer. Requires one physical
  action; no marker file needed, the reboot alone is the trigger.

## R9 - "Did we change the upload and cause these failures?" - NO (git-proven)
Question raised by the owner after 12 failed staging attempts. Answered from history, not guess:

- `scripts/release/release-fwpkt.sh` staging block is **byte-identical** to the version that
  installed v109 successfully on 2026-11-15 (`docs/evidence/astro-v109-camera-mainline-20261115/
  LIVE-SESSION.md:66` - "started 11:56:31 and exited 0"):
      tar czf - -C "$BUILD_DIR" FwPkt | ssh -o BatchMode=yes \
        -o ServerAliveInterval=10 -o ServerAliveCountMax=60 "$SSH" 'tar xzf - -C /app/sd && sync'
  Compared `git show 53e624d5:...` against current HEAD: same command, same keepalive flags.
- There is no chunked/resumable staging path in any version of the installer - it has always
  been one stream. So "the original process streamed in chunks" is not what the script does.
- Later commits touched only *budgets and guards* (85800c79 raise SSH budget, b1cc438e keepalive
  gate, 53e624d5 ServerAliveCountMax + staged-size verify). None changed the transfer itself.

### Actual cause: known open device defect, issue #171
"Polaris AP-mode WiFi driver permanently exhausts dhd tdata_psh_info pool (~230 errors/min while
associated)" - OPEN, labels bug/area:network-wifi. Evidence on that issue:
- 2026-11-21 camera-off bulk transfer grew DHD failures 83 -> 115 with **no camera enumerated**,
  sender showing TCP retransmissions and >100 KB send queue. So it is not camera workload.
- "permanently exhausts ... while associated" implies the pool does not recover without a
  re-association/reboot - consistent with every attempt tonight failing at the same point.

### My own transfer experiments tonight (all failed, recorded so nobody retries them)
| method | result |
|---|---|
| installer's single 86 MB tar stream | 12 x INSTALL_EXIT=255 mid-staging |
| 20 MB to /dev/null (no disk write) | 1041 s then `send disconnect: Connection timed out` |
| 4 x 1 MB chunks, fresh SSH each | all 4 hit timeout; one took 990 s |
| paced ~0.5 MB/s bursts | 1095 s, rc=124, disconnected |
Throttling and chunking do not help, which rules out "too fast" and points at pool exhaustion.

### Conclusion and route forward
Not a regression. Route A (SD card + reboot, docs/FIRMWARE-INSTALL-PROCESS.md:202) needs no
network at all and is the reliable path. Secondary option worth one test: reboot the device to
reset the DHD pool, then stage immediately in the fresh window before exhaustion re-accumulates.

## R10 - Drive-mode cache invalidation: WIP patch, NOT validated (recorded honestly)
While preparing to ship the cachetime=30 win I found an asymmetry in source:
`_put_Pentax_DirectDriveMode` calls `ptp_setdevicepropvalue` (no cache invalidation),
whereas `_put_Pentax_DirectShutter` / `_put_Pentax_DirectISO` call
`ptp_generic_setdevicepropvalue`, which does reset the entry. So a drive-mode change
can leave mode-dependent descriptors cached.

I wrote a 15-line patch invalidating `PTP_DPC_PENTAX_ShutterSpeed` on a successful
drive-mode SET (mirrors `handle_event_internal`'s `PTP_EC_DevicePropChanged` path).
It builds clean (`ninja`, rc=0). Preserved at
`k1ii-drive-mode-cache-invalidation-WIP.patch` (sha256 9a04e55bd1e56db4...).

### Why it is NOT claimed as a fix, and was reverted from the worktree
The staleness test never ran. `--set-config /main/status/pentaxdrivemode=bulb` failed
with gphoto2's "sufficient quoting" error, so drive mode never changed: conditions read
`drive-mode-raw=0` before and after, exposure-mode Manual throughout. My earlier
"both reads identical -> bug reproduced" observation therefore proves nothing - there was
no state change to invalidate. Camera left untouched; nothing to restore.
To validate properly the write must be quoted and confirmed by a `drive-mode-raw` change,
then the shutter enum compared before/after. Until then this is a hypothesis with a
compiling patch, not a fix.

## R10 - Repository cleanliness audit (verified, not assumed)
Checked every repo with `git status --porcelain` + `git log -1` rather than trusting memory.

| repo | branch | HEAD | dirty | disposition |
|---|---|---|---|---|
| BenroPolarisPatcher | main | 9aea6118, == origin/main | 0 | clean, pushed |
| .libgphoto2-v115 (v115 pin) | detached | 0f2f34e00040 | 0 | pristine as required |
| .lpg-experiment-k1ii | exp/k1ii-driver-perf | 0f2f34e00 | 0 (build-exp ignored) | patch reverted, WIP preserved as hashed file |
| benro-polaris-test-harness | exp/pentax-ptp-pc-gate | 64db8e8, == origin | 0 | clean, pushed; main untouched at 3ad4197 |
| LibGphoto2/libgphoto2 | test/k01-ability-pid-shadowing-gate | 232ac8c99 | **2** | **NOT MINE - preserved** |
| OpenPolaris | main | a4847ebc, == origin | **2** | **NOT MINE - preserved** |

### Why the two dirty repos were left alone (AGENTS.md: preserve others' WIP)
- `LibGphoto2/libgphoto2`: modified `DEVELOPMENT_PLAN.md` and
  `docs/pentax/REAL_HARDWARE_TEST_LOG.md`. These are the hardware-ledger edits another agent
  reported making; reverting them would destroy recorded evidence. Not touched.
- `OpenPolaris`: `gradle/wrapper/gradle-wrapper.properties` (8.10.2 -> 9.7.1) carries a
  `#Wed Nov 18 11:35:14 GMT 2026` stamp and matching mtime - **five days before this session
  started**, so it is pre-existing, not session output. Plus an untracked 377 MB `.codex-next-21/`
  tool directory. Three older stashes also exist here, confirming ongoing work by others.
  Not touched, not deleted.

### Documentation completeness (this round)
- `k1ii-driver-research.md` R1-R10: root causes, corrected perf numbers, invalid-test retraction,
  MF-drive state-dependence, install blocker, regression question, cleanliness audit.
- Preserved artifacts with recorded hashes: `wff-diagnostic.patch` (d1b46ca6...),
  `k1ii-drive-mode-cache-invalidation-WIP.patch` (9a04e55bd1e56db4...).
- `docs/IT2-2625-FEATURE-REVIEW.md` is tracked and contains **zero** code fences - no proprietary
  source copied.
- Handoff disambiguates the two same-named `FwPkt.zip` files: the on-disk candidate matches
  `RELEASE-IDENTITY.md` (68409600 B, sha256 7c621152...) and is the gated artifact; the flagged
  do-not-use one is 68409670 B / a9bc2a83...

### Still open, stated plainly (nothing here is done-but-claimed)
1. **v115 not installed.** Device still `FwVer:6.0.0.54.114`. Blocked by issue #171; needs Route A
   (SD card) or a pool-reset reboot, both requiring one physical action.
2. **Drive-mode cache-invalidation patch is UNVALIDATED.** My staleness reproduction was invalid:
   the `--set-config pentaxdrivemode=continuous` write never took effect (drive-mode-raw stayed 0),
   so no mode change occurred and the identical choice lists proved nothing. The patch compiles but
   is reverted and unproven - it must not be shipped on current evidence.
3. **MF drive (#381)** remains state-dependent: cold -> 0xa00c, primed -> 0x2001 on K-3 III. Cause
   not established.
