# Autonomous session record — 2026-11-11

Continuation of the v105 field-test triage. Worked unattended. Everything below is either
pushed or explicitly marked as not done.

## Shipped (pushed)

| Repo | Commit | What |
|---|---|---|
| patcher `main` | `9a49b07` | #329 apply-last contract: new module + node tests + gate registration |
| patcher `main` | `ca58501`, `28d7e60`, `6ee1d81` | v106 change summary, twice corrected |
| patcher `feature/astro-native-platesolve` | fast-forwarded to `main` | builder requires this branch by name |
| libgphoto2 `main` | `96cb7b8b4` | #148 — route generic `exposurecompensation` to the Pentax EV handler |

Candidate built: `astro-v106-appliance-fixes-20261111`, display fwver `6.0.0.54.106`.
**GATE: GREEN (23 passed, 0 failed, 3 skipped)**, artifact verdict
`ARTIFACTS_INTERNALLY_CONSISTENT_WITH_UNKNOWN` (21 checks, 0 fail, 1 unknown), candidate
identity `PASS (deployable)`. Not published, not installed — see boundary below.

## 1. #329 — implemented, and two of its asks deliberately refused

`#solve-apply` posted an empty body, showed nothing on success, and on failure showed only a
bare error string. The user wrote a mount alignment from a solution whose RA/Dec, roll and
pixel scale were never displayed, even though `/api/state` already returns the whole solver
JSON and `/api/apply` already reports `age_sec`.

Decision table moved to `container/astro/webui/solve-apply.js`, DOM-free like `shutter.js`
(#309), asserted under node by `tests/test_astro_solve_apply.js` (17 groups) through the
pytest wrapper, registered in `PY_TESTS`.

Refused deliberately, with reasons recorded on the issue and in the module header:

- **Focal length is not threaded into apply.** Focal selects the search space at *solve* time;
  a solved frame's RA/Dec are already resolved and applying them writes no focal anywhere.
  `polaris-httpd.c` runs every solve as `--focal auto` on purpose — "Forcing g_focal here would
  reintroduce the bug that cost a whole night". Sending a UI focal through apply recreates it.
- **The align checkbox is not consulted by this button.** `/api/apply` always writes the
  alignment, so honouring an unticked box would mean silently doing nothing.
- **No client-side staleness gate.** `/api/state` does not report frame age — only `/api/apply`'s
  reply carries `age_sec` — so a UI-side refusal would be guessing, and duplicating the server's
  rule creates a second source of truth that can disagree with it. Same class as #309, where the
  WebUI tried to decide shutter subtype itself.

The part I would argue matters most: `applyOutcome()` treats a missing body, a non-object, an
array, or an object with no `ok` field as **not confirmed**. Previously all of those fell through
to a generic failure line that read as though the head had refused the write — a different event
that must be said differently.

## 2. #323–#328 — checked against shipped bytes, not inferred

Six issues asked pgphoto to call Pentax guards before forwarding config writes. Three independent
blockers, each verified:

1. `_pentax_readiness_preflight`, `_pentax_verify_property_value` and
   `_pentax_verify_rational_in_conditions` are all `static`, declared in no header, so not
   exported from `ptp2.so`. pgphoto cannot link to them.
2. `params->pentax.vendor_mode_enabled` lives inside `PTPParams`, internal to the camlib. pgphoto
   only ever holds the public `gp_camera_*` API.
3. Both public entry points already funnel into the guarded `_put_` handlers:
   `camera_set_config`/`camera_set_single_config` → `_set_config` (config.c:16498/16504) →
   `cursub->putfunc` (:16316) → `_put_Pentax_DirectShutter` (:15352).

So pgphoto is not an unvalidated pass-through; it calls a path that validates. Our own
`stage2_shim_gp_camera_set_single_config` is deliberately pure pass-through for config writes, so
nothing short-circuits the camlib either.

**What is genuinely broken** (in #328): on verification failure the driver does not revert the
widget it was handed — `continue` at config.c:16333 with no value restore, then
`gp_widget_set_changed(widget, FALSE)` at :16339 anyway. `_put_Pentax_DirectShutter` contains zero
`gp_widget_set_value` calls (232 exist elsewhere in `config.c`). A consumer caching from
`gp_widget_get_value()` on a widget it already holds therefore caches the *attempt*, not the state.
The read path is unaffected: `_get_config` calls `cur->getfunc` per widget, so a fresh
`get_single_config()` re-queries the camera.

#324 closed as duplicate of #325. #328 given a proposed retitle and driver-side scope. #323/#326/#327
corrected in place. No libgphoto2 change made for these: `_set_config` is generic across every
vendor in the file, and driver `AGENTS.md` forbids changing it for a consumer-discovered failure
without a repo-boundary reproducer plus impact statement.

Also noted: #328's own environment block cites libgphoto2 `0562e8a`, which is upstream and **930
commits behind** the pin v105 ships (`49b67fa44`). The analysis was done against a library not in
the build being tested.

## 3. #148 — recovered, and its recorded blocker proven gone

`0ca7c9205` (tag `archive/pre-consolidation/fix/k1ii-benro-controls`) was never landed during the
2026-11-09 consolidation. It adds one `PTP_VENDOR_PENTAX` row routing the standard name
`exposurecompensation` to `_get/_put_Pentax_DirectEV`.

Its recorded blocker was:

```
FAIL line 298: ret == GP_OK && ev != NULL
```

That no longer reproduces. Established by control, not assumption, in an isolated worktree at
`49b67fa44` with a meson build in a separate prefix:

| State | Result |
|---|---|
| EV row absent, test's EV assertions present | `FAIL line 298` — reproduces #148 exactly |
| EV row present | passes |
| assert `count_choices == 99` instead of 3 | `FAIL line 303` |

The last row is what makes this worth landing: a green test that never reached the EV block would
have looked identical to a fixed one. Full suite unchanged at 24 passed / 1 failed; the failure is
`test-gp-port` in the `no-ci` suite, present on plain main, excluded by
`tests/run-pentax-host-check.sh`.

## 4. v106 built via the documented process — and what that took

`docs/ASTRO-CANDIDATE-RELEASE.md` specifies a clean clone of the pushed Astro branch, not the dirty
worktree. Three failures before it succeeded, each a real gap rather than a flake:

1. **Gate RED** — `check_bulb_cancel_return` needs an immutable v90 binary under `out/`, which is
   gitignored. Located it, verified its sha256 against the pinned value
   (`8973d948…eaac`) before supplying it, rather than substituting a similar file.
2. **Release identity failed** — my change summary used component names outside the validator's
   vocabulary `{libgphoto2, patcher, packaging, tests, docs}`. Fixed by running
   `create-release-change-manifest.py` *directly* before rebuilding, instead of discovering it 15
   minutes into another cycle.
3. **`--libgphoto2-commit` requires a full SHA**, not an abbreviated one.

The builder independently corroborated the #323–#328 analysis: `libgphoto2 commits since baseline:
0` at the v105 pin, and `patcher commits since baseline: 31`.

## 5. New issue filed: #331 — GPL source ships in the tarball but never reaches a user

The archive gate reported 5 licence files outside `COPY-TO-SD-CARD-ROOT`, so a user following the
bundle's own README copies binaries built from GPL-2/LGPL-2.1 components with none of the licences
or corresponding sources. Not a v106 regression — the check arrived with #292, so v105 and earlier
were never examined by it. Filed rather than fixed: whether to copy licence texts plus a written
offer, ship the tarballs on the card, or change the README is a distribution decision I should not
make unilaterally, and verifying any of them needs a supervised window.

## 6. Methods I got wrong, and how they were caught

Worth recording because each produced a confidently wrong answer.

- **Claimed the built binary did not contain the #329 change.** Searched `polaris-httpd` for raw JS
  bytes; found none. Ran a control with `shutter.js`, a known-good pre-existing asset, which also
  returned nothing — because `embed_webui.py` **gzips** every asset into `.rodata`. Inflating the
  embedded streams showed all five assets present and correct. The first conclusion was an artefact
  of the method, not a build defect.
- **Reported "OLD empty-body handler gone: FAIL" on the inflated assets.** The string appears in
  `solve-apply.js`'s own header comment describing what the old code did. Checked per-asset and the
  live handler is correctly `post('/api/apply' + req.query, {})`.
- **First #148 control was invalid.** `git stash` reverted the test file as well as `config.c`, so
  plain main "passed" trivially with no EV assertions to run. Redone by reverting only `config.c`
  and keeping the assertions, which then failed at line 298 as expected.
- **String-count comparison cannot prove a table row exists.** `exposurecompensation` appears 3× in
  both parent and fixed builds because `.rodata` deduplicates literals. The behavioural control is
  the proof; the byte-level check was decorative.
- **Wrong date in a path** (`20261111` for the v105 dir, which is `20261110`) made `find` return
  nothing and briefly suggested v105 had shipped no `ptp2.so`.

## 7. Verification that actually landed

- **WebUI change is in the shipped ARM binary.** Inflated all five embedded gzip assets from the
  built `polaris-httpd`: `solve-apply.js` present, `describeSolution` and `applyOutcome` present,
  `app.js` calls `SOLVE_APPLY.applyRequest`/`applyOutcome`, `S.solveState = st` present,
  `/solve-apply.js` referenced by the embedded `index.html`, and the bare empty-body post absent
  from `app.js`. Control: `shutter.js`'s `decideDispatch` still present.
- **Driver change is in the shipped ARM binary.** v105's `ptp2.so` md5 is `b18d45a8bc1dcde29dad4151091608cc`
  — byte-identical to the md5 recorded from the device, which independently confirms the "the driver
  on the device is ours" claim used in the #323–#328 corrections. v106's is `83ea3baf01df…`, 28 bytes
  larger.
- **Patcher suite**: 697 passed, 15 skipped (was 694 before the three new tests).
- **Mutation-checked both directions** for #329: restoring the old empty-body post fails exactly one
  test; making `applyOutcome()` accept a missing reply fails exactly one group.

## Not done / not claimed

- **Nothing was installed, flashed, staged, rebooted or published.** No Polaris reachable at
  `192.168.0.1` or `192.168.1.1`, and no Pentax/Benro device on USB — checked before concluding.
  `docs/ASTRO-CANDIDATE-RELEASE.md` additionally forbids staging until the camera owner accepts the
  baseline, #251 is resolved or waived, and a supervised test window is scheduled. All three are
  outstanding, so publishing would have been wrong regardless of connectivity.
- **No hardware verification of anything this session produced.** The #329 fix is verified by
  execution under node; "alignment written" reflects what `/api/apply` reported, not independently
  confirmed mount state. The #148 fix is an offline seeded-descriptor fixture result — per the
  driver's own rules, "the build passes" is not "this is correct". Whether a real K-1 II answers
  `0x5010` the way the seeded descriptor does is untested, as is the `GP_WIDGET_TEXT` fallback for
  bodies advertising no enumeration.
- **The widget-not-reverted defect behind #328 is not fixed.** It needs its own offline fixture test
  first; `tests/test-pentax-aperture-alias.c` already demonstrates the pattern needed (seeded
  `Camera`, no wire I/O). Proposed scope is on the issue.
- **#331 not fixed** — distribution/licensing decision, left for the owner with three options.
- **The `licence-reachability` check still reports `UNKNOWN`.** Left unsilenced deliberately; it
  should become decidable once a route is chosen.
- **Three gate skips remain**: firmwareInfo manifest gate (no stock FwPkt.zip in repo),
  shipped-artifact differential (no previous candidate with a manifest to compare), provenance
  registry hash check (no built artifacts to compare). Recorded here as required by the gate output.
- **#297 root cause still unknown.** This cut carries read-only diagnostics only; layer 3 remains
  unfixed.
- **`test-gp-port` fails on plain main** in the `no-ci` suite. Pre-existing, unrelated to Pentax,
  excluded by the documented host check. Not investigated.

---

# Continuation, same day — #273 shipped, and a test that silently tested nothing

Second autonomous block after the record above. Everything below is pushed or explicitly
marked as not done.

## 8. #273 — auto-join toggle was a silent no-op; settings page had no credential entry

`app.js` posted `{autojoin:1}`. `/api/wifi` reads `action` and matches `autojoin_on` /
`autojoin_off`. The request matched no branch, fell through into the status block, and answered
HTTP 200 with `{"ok":true,...,"autojoin":false}` — success reported for a change that never
happened. The handler was correct all along; only the client had drifted. The embedded fallback
page already posted the right verb, so two clients disagreed about one endpoint and the page most
people use was the wrong one.

Established by **executing** the server rather than reading it:

| build | `POST autojoin=1` response |
|---|---|
| unfixed | `{"ok":true,"ap_ip":"","sta_ip":"","ssid":"","configured":false,"autojoin":false}` |
| fixed | `{"ok":false,"error":"unknown or missing action (expected save, autojoin_on, …)"}` |

Second half of the issue: the card had a "Join my network at power-up" switch and no SSID or
password field — those lived only in the fallback page, so turning auto-join on from Settings
joined whatever was configured elsewhere, or nothing. Added SSID/password fields, save
(`action=save`, same verb the fallback page uses), and join-now (`action=up`, which runs the exact
boot script rather than a second implementation that could drift).

The server-side rejection is the part worth keeping even though the client is fixed: an endpoint
that answers `ok:true` to a request it did not understand will reproduce this bug silently the
next time a client drifts. Enumerated every `/api/wifi` caller first — only two exist, both send
a valid action, so nothing regresses.

## 9. My own regression test skipped in the gate — the exact failure mode I criticised

`tests/test_wifi_api_contract.py` passed locally and **skipped inside the prerelease gate**.
`polaris-httpd.c` includes `webui.h`, which `embed_webui.py` generates and `.gitignore` excludes
at line 62. My working tree had a stale copy from an earlier build, so gcc found it here; the gate
builds from a fresh clone where it does not exist, gcc failed with "No such file or directory",
and the fixture skipped.

The gate reported **GREEN** while three of five tests were skipped, and the skip was invisible
because the suite only prints a passed count. This is precisely the #292/#299 failure mode I
documented in section 4 — a check that exists, is registered, and runs on nothing. I criticised
that pattern and then shipped it myself.

Fixed by generating `webui.h` into the fixture's own tmp dir and compiling with `-I` at it, so the
test needs nothing absent from the repository. Verified where it previously failed — in the build
clone with no `webui.h`: **5 passed** (was 2 passed / 3 skipped). The rebuild's gate count moved
from 700 to **703**, which is the +3 executing tests that were being skipped.

The two source-assertion tests were the only ones the gate had actually been running; the three
that distinguish "answered ok" from "answered ok because nothing matched" were the ones silently
absent.

## 10. A contract audit that produced three false positives

I scripted a comparison of every key `app.js` posts against every key each handler reads, and it
flagged `/api/astro/align`, `/api/astro/goto` and `/api/astro/track` as sending unread
parameters. All three were artefacts: the regex matched the first occurrence of the path, which is
a `post_only[]` list, not the handler. Confirmed by posting real requests to a natively built
server — all three returned domain errors ("control link is down", "set your observing location
first"), i.e. they parsed their parameters and proceeded. `/api/wifi` was the only genuine
mismatch. Reported as false positives rather than filing three bugs.

## 11. #142 — premise partly wrong; two of its three open questions answered offline

- **The capture path does not emit `GP_EVENT_FILE_ADDED` at all.** `camera_pentax_capture_internal`
  (library.c:6757) fills the `CameraFilePath *path` out-parameter, including
  `strcpy (path->folder, "/")` at :7444, and returns. No emission anywhere in 7300–7800. So the two
  announcements are two different APIs — `gp_camera_capture()`'s return value and a later
  `gp_camera_wait_for_event()` — not two events to deduplicate. Producer-side suppression has
  nothing to suppress against; it would require new state, not consulting existing state.
- **Q2 (fork or upstream): both.** The generic folder `/` at :4737 is upstream — Marcus Meissner,
  2014, `c013a23996`, *"…to handle that CaptureComplete comes before the ObjectAdded event"*. Our
  Pentax site at :7444 is `342c053ae4` "Add guarded Pentax tethering core". Not a regression we
  introduced; upstream's capture contract meeting a consumer that treats the two channels as two
  files.
- **Q3 (handle-based suppression): not directly implementable.** `params->pentax.candidate_handle`
  is set at :7432 and **cleared to 0 at :7746 before the function returns**, and is never read in
  the event path. At ObjectAdded time it is 0. Suppression keyed on it would never fire, or would
  need the handle retained past capture end — colliding with the clearing logic and with the
  reconciliation path that reuses the same field.

Recommended folder normalisation instead of suppression. **No code pushed**: Q1's live trace is
the decisive one (does pgphoto fire `captureImageEvent` off both channels, or only the event?), it
needs a device with `GP_LOG_D`, and I cannot reproduce a SIGSEGV in a closed-source ELF offline.

## 12. #138 — already fixed on main; verified rather than reimplemented

The issue is written against baseline `63a894b08` (v90). On current main,
`ptp_pentax_camera_shutdown` is no longer called anywhere in `library.c`; fixed by `6fe00aeb6`
(2026-10-30), an ancestor of main. The mock-transaction test the issue demands already exists —
`tests/test-pentax-camera-exit.c`, registered at `tests/meson.build:36-41` — and passes on the
commit v106 pins:

```
PASS: real camera_exit, no shutdown, ordered cleanup, error precedence, non-Pentax controls
```

Its assertion is the right shape: the stub still *records* `PTP_OC_PENTAX_CameraShutdown`, and
`finish()` asserts an exact transaction count (`operation_count == restore + disable + close`), so
a stray `0x9002` fails rather than being tolerated. Only the hardware half (bounded read timing,
idle-reconnect qualification on K-1 II / K-3 III) remains, and I did not claim #138 closed on the
offline half alone.

## 13. v106 rebuilt — final state

`astro-v106-appliance-fixes-20261111`, fwver `6.0.0.54.106`: **GATE GREEN (23 passed, 0 failed,
3 skipped)**, python regression suite **703 passed**, drift guard **48 suites all listed**,
artifact verdict 21 checks / 0 fail / 1 unknown, candidate identity **PASS (deployable)**.
Manifest `declared_changes` carries 8 entries including #273; lifecycle is
`built: true`, everything else false.

Verified in the **shipped ARM binary** by inflating the gzip-embedded assets: posts
`action=autojoin_on`; old body-less payload absent; `#wifi-ssid`/`#wifi-psk` wired; `action: 'save'`
and `action: 'up'` present; `id="wifi-ssid"`/`id="wifi-save"` in the embedded HTML; controls for
the earlier work still present (`applyOutcome`, `decideDispatch`). Server rejection string present
in the binary. Driver unchanged from the previous build at md5 `83ea3baf01df…` vs v105's
`b18d45a8bc1d…`.

One gate-adjacent finding: `offline_gated` in the release manifest is a **hardcoded literal**
(`create-release-change-manifest.py:238`), not derived from the gate result. It reads `false` on a
candidate whose gate is green. Not corrected here — changing what a release record asserts is the
owner's call, and it may be deliberate (meaning "gated offline *and* hardware-qualified").

## 14. Mistakes in this block, recorded plainly

- **Marked the #328 reproducer complete in my todo list when I had not written it.** What I had
  actually produced was an executing test for #273; the #328 work was a feasibility investigation.
  Caught while re-reading the list and corrected immediately. #328 remains unwritten.
- **Shipped a test that skipped silently in the gate** (section 9) — the failure mode I had
  criticised two hours earlier in the same document.
- **First `app.js` edit broke the file's syntax.** The replacement swallowed the closing braces of
  `wireSettings()` and the following section header; `node --check` reported "Unexpected end of
  input". Reverted, inspected exact bytes with `cat -A`, redid it minimally. Final diff is one line
  replaced plus additions.
- **Wrote a UI message referencing a "Join now" control that did not exist.** Caught by grepping
  for the id before committing; added the control properly on `action=up` rather than deleting the
  sentence.
- **Reported "changes recorded: 0"** from the manifest. My key guess was wrong — the field is
  `declared_changes`, which holds 8 entries. The record was complete all along.
- **Three false-positive bug claims** from a scripted contract audit (section 10).

## Still not done

- **#328's widget-revert fix and its offline reproducer.** Investigated for feasibility, never
  written. The blocker identified: `params->pentax.candidate_handle` is cleared before return and
  the write path needs a stubbed transport; `test-pentax-keep-live-view-toggle.c` shows the
  precedent for driving `camera_set_single_config` offline, but it covers a virtual toggle, not a
  property write that fails verification.
- **#331** (GPL/LGPL licences never reach the user) — still open, distribution decision.
- **No hardware verification of anything.** No Polaris reachable, no Pentax on USB. #273's actual
  file write (`/app/sd/polaris-wifi/autojoin`) and a real association are unexercised; whether
  joining succeeds on the device is still a hardware question. Nothing installed, flashed or
  published.

---

# Third autonomous block — #302 shipped, three issues found un-implementable as written

## 15. #302 — a false security claim in shipped code, fixed honestly

`setup-wifi.sh` said *"the file is chmod 600 -- treat it as a credential"* and wrote
*"contains a PSK hash; keep it private"* **into `wpa.conf` itself**. `/app/sd` is vfat
mounted `fmask=0022`, which has no per-file permission model: `chmod 600` returns success
and changes nothing. The reporter proved this on-device (touch, chmod 600, `ls -l` → still
755). `wpa.conf` holds a WPA2 PSK hash — sufficient to join the network without the
passphrase — so it is readable by every process on the Polaris and by anyone who puts the
card in a PC.

The in-file line is the worse of the two: it is what a user sees with `cat`, and it tells
someone to keep private a file that cannot be made private, on the exact medium they are
being asked to carry. A false security claim is worse than none — reading it reasonably
concludes the secret is protected and stops thinking about it.

**Fixed the claim, not the exposure.** Both texts now state the real situation (vfat,
`fmask=0022`, readable by any process or card-holder); the summary prints the mode actually
stored and warns when world-readable. The chmod is kept — harmless, and correct on a
filesystem that honours it — with a comment saying plainly not to read it as protection.

Deliberately **not** done: option 1 from the issue (move the config to `/var/lib/polaris`,
UBIFS where chmod works). It needs a read-fallback so existing cards keep working and
touches four consumers (`setup-wifi.sh`, `polaris-autojoin.sh`, `polaris-apsta.sh`, the
httpd handler). That is a distribution decision with a compatibility surface.

Checked for the same lie elsewhere before committing: `polaris-httpd.c` stages the key at
`/tmp/.wpa-psk`, which is tmpfs, so `chmod 0600` there genuinely works — the app.js comment
I wrote yesterday about staging "at 0600" is accurate and was left alone. No response ever
echoes the psk back (grepped the whole handler).

**Why the existing suite missed it:** `test_setup_wifi_psk_not_in_argv.py::
test_config_written_with_private_mode` asserts `mode == 0o600`, and passes — on ext4, where
chmod works. It validated the behaviour on a filesystem that honours chmod rather than the
one the file actually lives on. That test stays (the chmod is still correct where it works),
but it is exactly why the claim survived review, and it is the same class of mistake as
section 9: a check that passes because its environment differs from production.

New suite asserts on the **claims**, not the mode, since the mode can't change without the
relocation decision. Mutation check: script reverted → 4 fail / 1 passes; the survivor is
the cleanup control. Registered in `PY_TESTS` (49 suites). Full suite 727 passed (was 722).

## 16. Three issues whose premises did not survive inspection

**#321 — already implemented.** I was about to add solve logging, found a dead
`g_nfield_for_timeout` variable that looked like a half-finished feature, and started
implementing. Checked `git log -S` first: `b495d70 feat(astro): log solve start, duration
and classified outcome (#321)` already exists **and is in the shipped v106 bundle** (6 hits
in the built `polaris-align.sh`). It logs start/duration/classified outcome with star count
precisely to separate the issue's four hypotheses. No work needed; caught before duplicating
it. The dead variable is real but harmless and I left it rather than churn unrelated code.

**#318 — the mechanism does not exist on our side.** "USB compatibility mode" is a **camera
menu setting**, not a Polaris one. `docs/CURRENT-STATE.md:886-938` records the investigation
of exactly this toggle: *"the menu bit is **not logged**"* and, on the closest log line,
*"This is an app camera-control/connection transition, **not a direct readback of the
camera's USB compatibility menu setting**."* No file, property, PTP descriptor or log line
reveals it; grepping our tree finds no representation at all. No documented intent links the
WebUI to it either. I did not build a best-effort gate on camera presence or the `code 297
mode:0/1` transition: presence changes for many reasons, and the panel is how you diagnose
why a camera is absent — gating it on presence would remove the tool precisely when it's
needed. Offered instead: keep the panel up and state that USB compatibility mode on the body
is a known cause when no camera is reachable. No code pushed.

**#328 — real, mechanism confirmed, but not fixable correctly offline.** Traced it fully:
`_put_Pentax_DirectShutter` (`config.c:12193`) verifies and returns an error on failure with
nothing touching the widget (:12305-12308); `_put_Ricoh_ShutterSpeed` only *reads* the widget
(:5320); the generic core forwards it untouched and keeps no snapshot
(`gphoto2-camera.c:1131-1146`). So after a failed write the widget still holds the requested
value — #328 exactly, and why #325's read-back guard doesn't fix it alone.

The obvious fix is wrong for this camera: refreshing via `_get_Pentax_DirectShutter` calls
`GetDevicePropValue` for 0xd00f, which **this very handler documents the K-1 II refuses**
(:12273-12281). The correct fix — snapshot before write, restore on failure, Pentax-gated —
needs a device to prove the restore branch runs and that restoring a `const char*` into the
widget's own string list survives descriptor refetch. Getting that lifetime wrong is a
use-after-free on every Pentax write. AGENTS.md §110-137 requires an impact statement and
non-Pentax evidence for this path. No code pushed; asked for a device and a decision on
revert-vs-unknown semantics.

Also confirmed pgphoto is a stock Benro binary from the FwPkt, not source we own — so the
consumer side of #328 isn't fixable by us either.

## 17. v106 rebuilt with #302 — final state

Rebuilt through the documented clean-clone process at `571538e`. **GATE GREEN** (23 passed,
0 failed, 3 pre-existing skips), python suite **708 passed** — exactly 703 + my 5 new tests,
which is how I confirmed they *ran* rather than skipped, the failure mode from section 9.
Drift guard **49 suites all listed**. Artifact verdict 21 checks / 0 fail / 1 unknown (#331).
Candidate identity **PASS (deployable)**.

Verified in the shipped bundle: honest text present (5 hits), old false claim absent (0),
in-file "keep it private" absent (0). Earlier fixes still intact — `action=autojoin_on`,
`#wifi-ssid`/`#wifi-psk`, `applyOutcome`, `decideDispatch`, server rejection string. Driver
unchanged at md5 `83ea3baf01df…`. Manifest carries 9 `declared_changes`; lifecycle
`built: true`, everything else false.

## 18. Still not done

- **No hardware verification of anything.** Rig unreachable all session (`192.168.0.1`), no
  Pentax/Benro on USB. #302's warning branch fires only on a real vfat mount and is unexercised;
  #273's actual file write and association are unexercised. Nothing installed, flashed or published.
- **#302 option 1** (relocate to UBIFS) — distribution decision.
- **#328 fix** — needs a device plus a semantics decision.
- **#331** (licences never reach the user), **#297** root cause, **#318** pending the answers above.

---

# Fourth autonomous block — driver issue #140 closed with executable red/green evidence

## 19. #140: an executable regression for the held-Bulb cancellation path

The static contract test asserts source substrings and ordering, which cannot show that a
cancellation actually returns `GP_ERROR_CANCEL` without writing a shutter. Commit `4fba11d81`
added exactly such a guard to the deferred camera-timed fallback and nothing executable proved
it worked. The precedent that makes this worth having is in our own history: the v75 shutter
readback change passed every offline gate and then physically hung every timed capture.

Built `tests/test-pentax-bulb-action.c` on the house pattern — `ptp2_pentax_bulb_action`
extracted verbatim from `library.c` by the same `extract()` helper the camera-exit harness uses,
so no duplicated logic and no test-only symbol in the camlib ABI. `pentax-utils.c` is compiled
directly, so the model gate, `pentax_bulb_hold_to_seconds` and the whole-second wire layout are
production code rather than paraphrases. Only transport, capture path and
`gp_camera_get_abilities` are mocked; the clock is scripted (1000 ms → 25500 ms) so the asserted
shutter value is exactly `(1<<32)|25` instead of depending on wall-clock rounding.

**Red-before / green-after**, which is the whole point:
```
guard removed from library.c -> FAIL case 1 line 171: ... == GP_ERROR_CANCEL; operations=SC
guard restored               -> PASS: 15 cases
```
`operations=SC` makes the bug visible: without the guard the driver writes the shutter **and**
starts a capture on a request the user already cancelled.

**Proved not to duplicate `test-pentax-bulb-lifecycle`**, which #140 explicitly warns against:
with the guard removed that test still passes while mine fails. It drives a fake lifecycle state
machine through a `check_cancel` callback and never runs `ptp2_pentax_bulb_action`, so it cannot
see this path.

## 20. Two traps that each produce a silent PASS

Both were hit for real while building this, not theorised:

1. **`config.h` defines `LIBGPHOTO2_ENABLE_PENTAX_RESEARCH_CAPTURE` to 0** when the meson option
   is off, so an `#ifndef` guard does not catch it — the macro *is* defined, just falsey. The
   function body then compiles to `return GP_ERROR_NOT_SUPPORTED` and every assertion runs against
   a stub that does nothing. Caught by reading `meson.build:230` and `builddir`'s config.h rather
   than assuming. The harness `#undef`s and forces it on, because the appliance build passes
   `-DLIBGPHOTO2_ENABLE_PENTAX_RESEARCH_CAPTURE=1` (`container/build_ptp2.sh:344`) — that is the
   code that actually ships. Worth knowing independently of this test: **the shipped driver's
   Pentax research-capture paths exist only because of that CPPFLAGS line**, and an autotools
   build without it silently compiles them out.
2. **A generated `.inc` left in the source tree shadows the build-dir copy.** A quoted `#include`
   searches the including file's directory first, so my hand-generated `tests/*.inc` won over the
   freshly regenerated one. I removed the guard from `library.c`, rebuilt, and the harness reported
   **PASS against stale code** — exactly the false-green #140 exists to prevent. `.gitignore` now
   covers `/tests/*.inc`.

This is the same failure class as sections 9 and 16: a check that passes because what it actually
examined differs from what was intended. Three instances in one day, all caught by verifying the
mechanism rather than trusting the verdict.

## 21. No rebuild required, and why

`git diff --name-only` outside `tests/` and `.gitignore` is empty — zero production files touched,
so `ptp2.so` is byte-identical to the one already in the v106 candidate (`83ea3baf01df…`). Rebuilding
would have burned ~15 minutes to produce an identical artifact. Recorded rather than done.

`meson test`: 23 ok, 3 fail. All three (`test-gp-port`, `test-gphoto2`, `test-pentax-aperture-alias`)
reproduce with my changes stashed, so they pre-date this commit — verified before claiming it.

Driver `530c879fe` pushed to `origin/main`; tree clean.
