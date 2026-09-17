# v9g regression test plan — K-3 III Benro Connect crash (issue #71)

Date: 2026-09-12
Status: DRAFT for hardware execution
Owner: patcher/runtime + libgphoto2 (cross-stack)

## 1. What we know

### Regression window (libgphoto2, `a96aa9f..15b8f6d`)

| Build | libgphoto2 SHA | Content | Status |
|---|---|---|---|
| **v9f** | `a96aa9fc4` | bounded K-3 III autofocus drive (`0x9011`) + model-aware manual-focus dispatch (`0x9016`/`0x9017`) | **KNOWN GOOD** on K-3 III (Connect does not crash) |
| **v9g** | `90736a1ac` | dual-format capture reconcile (#73) **+ generic `imageformat`/`imagequality` widgets on `0xd01b`** | **suspected first-bad** — two defects confirmed in source |
| v9h | `90736a1ac` + Polaris runtime/backoff delta (patcher-side) | same libgphoto2 as v9g | unknown |
| **v9i** | `15b8f6d89` | adds generic `capturetarget` (#59) on top of shutter/ISO | **KNOWN BAD** — Connect crashes immediately |

### Confirmed v9g defects (verified in source at `90736a1`, still present at HEAD `15b8f6d`)

Both live in `camlibs/ptp2/config.c`, introduced by `90736a1` (the first post-v9f
commit), and are gated to the K-3 III family
(`pentax_model_supports_writing_file_format()` → `pentax_model_is_k3iii_family()`),
so they apply exactly to the reported body.

**D1 — `imagequality` SET encodes "fine" as `0xff`.**
Old code: `quality_byte = (uint8_t)(2 - stars)` with fine=3, normal=2, basic=1.
That yields `0xff` for fine and is off-by-one for the other two, contradicting the
documented IT2 intent (`0=fine, 1=normal, 2=basic`). A client that reads "fine"
then writes it back (a settings sync on connect) issues an invalid `0xd01b` byte 7.

**D2 — `_pentax_wff_read_payload()` fails open.**
A short/missing `0xd01b` GET was zero-filled and returned `GP_OK`, so both setters
could write a syntactically complete but semantically malformed 10-byte payload
(byte-0 length marker becomes `0` instead of `6`, unrelated bytes erased).

**Why it fits the crash:** these paths need only generic config access — no capture.
If Benro Connect enumerates the config tree and syncs settings on connect (it already
polls `capturetarget`), a SET of `imagequality`/`imageformat` fires immediately after
connect, before the user touches Live View or capture. That matches "crashes
immediately, every time."

### Fix applied — committed as the v9j candidate

- New unit-testable helper `pentax_wff_quality_byte()` in `pentax-utils.[ch]`
  returns `0/1/2` for fine/normal/basic and `-1` for unknown labels.
- `_put_Pentax_ImageQuality()` now uses the helper and fails closed on unknown labels.
- `_pentax_wff_read_payload()` now returns `GP_ERROR_CORRUPTED_DATA` on a short/missing
  payload instead of zero-filling (fail-closed, per #72 B05/B06).
- Regression unit test added to `tests/test-pentax-utils.c`; **builds and passes**
  (`ninja tests/test-pentax-utils` → exit 0), and the full ptp2 camlib links clean.

**v9j candidate libgphoto2 SHA: `054be266b`** (= v9i `15b8f6d89` + this fix).
Full CI suite on `054be266b`: **10/10 pass** (incl. `test-pentax-utils`,
`test-pentax-reconcile`, `test-pentax-aperture-alias`). The two `no-ci` tests
(`test-filesys`, `test-gp-port`) fail identically on clean HEAD — pre-existing
environment issues, not caused by the fix.

## 2a. Full audit of every change since v9f (`a96aa9f..054be266b`)

| Commit | Build | Change | Risk assessment |
|---|---|---|---|
| `a96aa9f` | v9f | bounded K-3 III autofocus drive (`0x9011`) + model-aware MF dispatch (`0x9016`/`0x9017`) | known-good baseline; focus work lives here, **not** in v9g |
| `90736a1` | v9g | dual-format reconcile (#73) **+ generic imageformat/imagequality on `0xd01b`** | **D1+D2 defects (fixed in v9j).** Reconcile loop is bounded + unit-tested; new public API reuses reserved `CameraFunctions` slot (struct layout unchanged) |
| `9bad88d` | — | re-register generic `shutterspeed` → guarded `_get/_put_Pentax_DirectShutter` (prop 0 + GetDevicePropDesc) | low: routes an existing verified handler; only makes the generic name reachable on bodies that omit the vendor prop from DeviceInfo |
| `220fcaa` | — | re-register generic `iso` → guarded `_get/_put_Pentax_DirectISO` (same pattern) | low: same as shutter |
| `15b8f6d` | v9i | generic `capturetarget` alias → SD-card writing mode (`0x9004`), gated to dual-slot models, fail-closed on error | medium: a compatibility alias, not proven K-3 III/IT2 wire semantics (see #71 suspect #1); get reports session cache, put maps 2 choices onto the `0x9004` bitmask. Must be covered by B04 |
| `054be26` | **v9j** | D1/D2 fix + regression test | the candidate under test |

Conclusion: the only *new client-visible config surface* that changed between known-good
v9f and the crash is the v9g `imageformat`/`imagequality` widgets (D1/D2) plus, in v9i,
the `capturetarget` alias. Shutter/ISO are low-risk re-registrations of already-verified
handlers. The dual-format reconcile only runs on capture, so it cannot explain an
immediate-on-connect crash. **v9j (`054be26`) is the build to test first.**

## 2. Test plan

Run on the **K-3 III** (reported body) with **Benro Connect** as the primary client,
and repeat the functional layers with **OpenPolaris** as a second client so we do not
optimise for one UI/protocol interpretation. Record camera firmware, Polaris candidate,
patcher SHA, libgphoto2 SHA, client version, lens, AF/MF switch and SD-card state.

A failure in an earlier layer blocks all claims above it (per #72 release rule).

### Layer 0 — Provenance / clean boot (gate everything)

- L0.1 Power Polaris off fully; attach K-3 III in PTP/USB mode; power on.
- L0.2 Verify `/app/openpolaris-libgphoto2-provenance.txt` shows the exact candidate
  libgphoto2 SHA and build_id. **Do not proceed on a misattributed build** (see the
  o-v9d window in `docs/evidence/k1ii-ov9f-2026-09-11/SUMMARY.md`).
- L0.3 Verify 8080 + 9090 LISTEN and pgphoto stays alive (single PID, no restart loop).

**PASS:** correct provenance, listeners up, daemon stable.

### Layer A — v9f survival baseline (must pass before testing anything newer)

These are the behaviours proven in o-v9f that a later build must not regress.

- A01 Camera detect/state: exact model `pentax k-3 mark iii`, `state:1`, storage info;
  hold connected ≥60 s with no disconnect/re-enumeration loop.
- A02 **Benro Connect immediate compatibility (the #71 reproducer):** 5 cold connection
  cycles — force-stop Connect, start/connect, enter camera-control screen, idle 30 s,
  close normally. **PASS: 5/5 with no Connect process crash, no camera-session loss,
  no Polaris process crash.** This is the single most important check; it directly
  protects the v9f behaviour regressed in #71.
- A03 Baseline focus/config discovery: `manualfocusdrive` query path returns `ret 0`,
  `getFocusInfo ret 0`; no uncontrolled repeated error loop or connection loss.
- A04 Baseline live-view safety: start/stop preview, observe frames, repeat 3×; a failed
  preview returns a bounded normal error, not an unbounded retry loop.

### Layer B — v9g new config surface (the regression window)

These protect the code that changed the client-visible config surface in `90736a1`.

- B01 Read-only enumeration of `imageformat`, `imagequality` (and, on v9i,
  `shutterspeed`/`iso`/`capturetarget`). For each record: return code, widget type,
  current value, choices/range. **PASS:** no malformed widget/value, no client crash,
  no session loss, no rapid uncontrolled retries.
- B02 **`imagequality` round-trip (regression for D1):** read current value; SET each of
  fine/normal/basic; GET/read back; confirm the camera agrees; restore original.
  **PASS:** exact round-trip and restore, and the outgoing `0xd01b` byte 7 is
  `0/1/2` (never `0xff`). Capture the outgoing payload bytes in debug logging.
- B03 **`imageformat` round-trip (regression for D2):** before any SET capture the full
  `0xd01b` payload; exercise one safe format change then restore. **PASS:** only the
  intended format bytes (4,5) change; every unrelated byte (size, quality, RAW kind,
  slot, length marker) is preserved; a short/missing GET fails closed rather than
  zero-filling and writing.
- B04 `capturetarget` (v9i only): GET generic value; record card-writing state
  separately; do not treat `0x9004` as proven capture-target semantics merely because
  the widget resolves.

### Layer C — preview / capture functional regression

- C01 Still capture completes once, file transferred/published, camera returns ready.
- C02 10 sequential captures: 10/10, no stale candidate blocks, no duplicate/missing
  transfer, no process/session failure.
- C03 RAW+JPEG dual-candidate path (the #73 reconcile): set RAW+JPEG without corrupting
  unrelated settings; capture; verify primary + extra-candidate handling; capture again.
  **PASS:** all candidates for exposure 1 reconciled, exposure 2 starts cleanly.
- C04 Preview → capture → preview: full sequence succeeds with no stale live-view state.

### Layer D — manual focus (the v9f focus work that must survive v9g)

The model-aware manual-focus dispatch and bounded autofocus drive landed in **v9f**
(`a96aa9f`) and are present unchanged at v9g. These tests prove v9g did not regress them.

- D01 Generic manual-focus discovery: `manualfocusdrive` resolves for the K-3 III.
- D02 Near movement: one bounded near step; lens moves once, no capture, no repeated
  movement.
- D03 Far movement: same for far.
- D04 Repetition/bounds: 10 alternating near/far steps; each command bounded, session
  stable, no growing latency/retry storm.
- D05 **Model-family dispatch assertion (K-3 III):** debug evidence must show the
  K-3 III uses the new-focus path (`0x9017`, displacement from openAvNum via
  `ptp_pentax_focus_control_new`). No accidental one-opcode-for-all-bodies behaviour.
  (Cross-check on a K-1 II if available: it must use `0x9016`.)

### Layer E — real autofocus (v9f bounded AF drive)

- E01 `autofocusdrive` resolves for the K-3 III; unsupported state fails cleanly.
- E02 Single AF action: defocus, invoke once; one bounded AF operation via `0x9011`,
  no still capture, session alive.
- E03 Already-in-focus case: clean completion, no retry storm or lens hunting.
- E04 Low-contrast failure: bounded failure/busy result, no crash/capture/infinite retry.
- E05 AF soak: 10 invocations with settle time; no leak, stuck-busy, latency growth.
- E06 AF → capture: defocus → AF → exactly one capture, camera returns ready.
- E08 **AF vs MF semantic separation:** under debug logging, `autofocusdrive` and a
  manual near/far command take clearly distinct paths; AF is not a disguised manual move.

### Layer F — compatibility / recovery / soak

- F01 Benro Connect workflow soak ≥10 min mixing config reads, preview, focus, captures:
  no app/process crash, disconnect or uncontrolled retry traffic.
- F02 Repeat the equivalent through OpenPolaris.
- F03 USB/camera disconnect recovery: bounded failure and clean recovery without reboot.
- F04 App reconnect: 5/5 sessions establish cleanly.
- F05 Polaris reboot recovery: repeat A01/A02 plus one focus and one capture.

## 3. Bisection order (fastest path to first-bad)

Test on the same K-3 III / Benro Connect combination, in this order:

1. **v9g** (`90736a1`) — if bad, first regression is v9g; instrument/disable
   `imagequality` first, then `imageformat`, before touching the larger dual-capture
   reconcile part of the same commit.
2. **v9h** — if v9g good and v9h bad, isolate the Polaris runtime/backoff delta.
3. If both good, test firmware built at each libgphoto2 SHA: `9bad88d` (shutter),
   `220fcaa` (shutter+ISO), `15b8f6d` (capturetarget).

With the D1/D2 fix applied, build a **v9j candidate** from `90736a1` + the fix and run
Layer A (especially A02) first: if Connect no longer crashes on connect, the defect is
confirmed as the config-surface sync, not the capture reconcile.

## 4. Mandatory evidence per candidate

Per #72: candidate/version name; exact patcher SHA; exact libgphoto2 SHA; camera body +
firmware; lens and AF/MF state; client versions; PASS/FAIL/N/A for every test ID;
timestamped logs around every FAIL; before/after/read-back values for config writes;
full `0xd01b` payload bytes before/after; focus opcode evidence; client crash log or
process-exit evidence. A bare "camera works" is not qualification evidence.

## 5. Cross-links

- #71 v9i K-3 III immediate Benro Connect regression (this plan's target)
- #72 standing release gate / mandatory Pentax regression suite
- #59 model-aware capability probe / capturetarget
- libgphoto2 #54/#55 imageformat/imagequality compound property (D1/D2)
- libgphoto2 #73 dual-format capture reconcile
- `docs/evidence/k1ii-ov9f-2026-09-11/SUMMARY.md` — v9f K-1 II baseline
- `docs/evidence/fwpkt-install/v9e-k3iii-qualification-2026-09-11/SUMMARY.md` — v9e K-3 III focus/AF evidence
