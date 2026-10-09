# o-v16c-context-lifetime-20261009 — 6.0.0.54.62

Candidate carrying the merged #190 context-lifetime fix. Built, gated, installed
and identity-proven on hardware. **Physical capture test not yet run** (§6).

## 1. Identity

| field | value |
|---|---|
| id | `o-v16c-context-lifetime-20261009` |
| build_id | `6.0.0.54.62-o-v16c-context-lifetime-20261009` |
| display_fwver | `6.0.0.54.62` (auto-derived; `.61` was previous) |
| libgphoto2 source | `main` @ `67843d2248e7e37cfa58c15cc52e0a47bc13d952` |
| patcher tree | `d5b9461` / `main` |
| stock base | `firmware/FwPkt.zip` (`90bdad511f556f25a2904ae9d2980102`) |
| FwPkt.zip md5 | `94b6b25fcb38be833176d3cd765ee918` |
| FwPkt.zip sha256 | `73d04ff813e40a35096c09bb3d41ef4dc7ee8be9aad7c416af14225586ced123` |
| appfs md5 | `06169c8d9b731544bec104a385f6fb98` |
| published | `ian-morgan99/PrivateResearch` → `firmware-packets/o-v16c-context-lifetime-20261009/FwPkt.zip`, status `candidate` |

libgphoto2 content is PR
[ian-morgan99/libgphoto2#97](https://github.com/ian-morgan99/libgphoto2/pull/97),
merged to `main` at `67843d224`. Its base `678d0dc3a` is exactly the source the
`.61` camera stack was built from, so on the **library** side the functional
delta is that fix alone.

## 2. What changed relative to `.61` — and one confound

`ptp_context_replace()` refs a context on store and unrefs on drop, so a binding
cannot outlive the object it points at. Core refcounting is atomic. The opt-in
`GP_PTP_CONTEXT_PROBE` diagnostics are identity-only and off by default.

| component | `.61` (`o-v16b`) | `.62` (this build) | why |
|---|---|---|---|
| `libgphoto2.so.6` | `4ef64d8950eee70d9200093286fb0f3b` | `5cd64dbd5708aa2228ee0379a9e456d4` | atomic refcounting + `gp_context_ref_count` live in the core |
| `ptp2.so` | `98b210eee15f93e69a27b49c08172856` | `e6a0d8576e74af16a13e8d567bb4b81d` | the #190 fix |
| `libpolaris_stage2.so` | `253cec38ef3742c0ccdb0a704b3c2120` | `95db5d54a0efbf7c02b37b2c73602816` | **see confound below** |

**Confound, stated plainly.** `.62` was built from current patcher `main`
(`d5b9461`), which is 12 commits past the `4be4a5f` tree `.61` was built from.
`7159bb4 fix(stage2): compose capture tracing with enabled protections (#188)`
is **not** an ancestor of `.61`, so the Stage-2 loader differs between the two.
This candidate is therefore **not a single-variable change**: if the physical
test behaves differently from `.61`, the Stage-2 tracing composition is a live
alternative explanation and must be considered before attributing anything to
#190. The core library change is expected and is not an accident — the
refcounting has to live there.

The core's exported symbol set gained `gp_context_ref_count`. Every existing
symbol's ABI is unchanged and `ref_count` keeps its type and offset, which
matters because the closed app statically links its own `gp_context_unref` and
decrements that field directly.

The #183 empty-path check is **retained**: `capture-outcome=empty-path` and
`STAGE2_CAPTURE_EMPTY_PATH_CHECK` are both present in the running
`/app/lib/stage2/libpolaris_stage2.so`.

## 3. Build-time gates

- libgphoto2 deterministic regression pack: **15/15 OK**. Skipped:
  `test-gp-port` — no-CI serial control-line test, host has no supported
  DTR/CTS fixture; skipped on `main` too, same wording as `.61`.
- Parameterised package/display-version regression: PASS.
- `tests/run_prerelease_gate.sh --build`: **GATE: GREEN** (container harness 19,
  python suite 189, polaris-pentax end-to-end, structural + firmwareInfo
  manifest validation, Bulb patch marker present).
- Sanitizer limitation, recorded not hidden: under ASan/UBSan four unrelated
  tests fail (`test-port-list`, `test-pentax-utils`, `test-gphoto2`,
  `test-camera-list`). The identical four fail with these changes stashed in the
  same build directory, so they are pre-existing on this host and sit in
  abilities-list/filesys paths this change does not touch.

## 4. Install (SD-card boot-watcher path)

Remote staging per the verified equivalent in `fwpkt-update-flow`; no direct
NAND edits.

1. `/app/sd` confirmed mounted (`/dev/mmcblk0p1`, vfat, 110 GB free) and
   **without** a pre-existing `FwPkt/` tree — no merge with an unknown partial.
2. Tree streamed with `tar czf - FwPkt | ssh … 'tar xzf - -C /app/sd && sync'`.
3. All six payload MD5+size pairs recomputed **on the device** matched
   `firmwareInfo` exactly (appfs, rootfs, uImage, config, polaris403, polaris413).
4. No local keepalive running. Reboot via `sync; /sbin/reboot` at 13:01:55 UTC.
5. Device answered as `.62` at 13:03:26 UTC.

## 5. Loaded-binary proof (not just the version string)

- `scripts/verify-installed-build.sh out/o-v16c-context-lifetime-20261009` →
  **INSTALLED BUILD IDENTITY: PASS**,
  `build_id=6.0.0.54.62-o-v16c-context-lifetime-20261009`.
- `/app/FwVer` = `FwVer:6.0.0.54.62;date:2026.10.09;`.
- On-disk hashes at both lookup paths match the candidate bytes:
  `/app/lib/libgphoto2.so.6` and `/app/lib/stage2/libgphoto2.so.6` →
  `5cd64dbd5708aa2228ee0379a9e456d4`;
  `/app/lib/stage2/libgphoto2/2.5.34/ptp2.so` → `e6a0d8576e74af16a13e8d567bb4b81d`.
- The running capture daemon (`pgphoto.stage2ondisk`, pid 250) maps
  `/app/lib/stage2/libgphoto2.so.6`, hash-verified as the candidate's.
  `ptp2.so` is dlopened on first camera use and is not mapped until then; its
  on-disk bytes are the candidate's.

## 6. Physical test — NOT run, and why

The K-3 III is absent from USB. It was attached before the reboot (`25fb:0189`,
`state:1`) and disappeared during it. The hub enumerates (`1a40:0101`, 4 ports)
with **no device behind it**; port re-authorise did not restore it and three
polls over 90 s saw nothing. `pgphoto` is running and the rest of the stack is
healthy, so this reads as the camera being powered off or unplugged rather than
a regression in the new stack. Needs a physical check: camera power, then cable.

Plan order once the camera is back:

1. Download an existing DNG with **no** shutter operation — the direct witness
   for the repaired fault.
2. Three Manual captures, each verified by file and by the next shot working.
3. Three Bulb captures, same verification.

Card is RAW+JPEG, so the canary expectation is `--expected-files 2`:

```sh
# camera ON:
./tests/run_prerelease_gate.sh --canary --two-shot
python3 scripts/canary-two-shot.py --expected-files 2 \
  --expected-sp-prefix /app/sd/normal/SP_ --expected-sw 6.0.0.54.62
```

Note for interpretation: `.61`'s bulb qualification failed for an unrelated
reason (camera never actuates — #186). If bulb still does not actuate here,
that is #186, not evidence about #190.

## 7. Status vocabulary

- **fault identified** — yes (forced-teardown reproduction).
- **software regression passes** — yes: fails-before/passes-after, plus an ASan
  witness of the real use-after-free.
- **candidate built, gated, installed, identity-proven** — yes.
- **physically fixed** — **not yet**. Requires §6 on hardware.

patcher#190 stays open until §6 passes.

---

# Physical results (2026-10-09, from 13:25 UTC)

Camera returned on USB (`25fb:0189`) at 13:25. Identity re-verified before any
capture: `verify-installed-build.sh` → **PASS**, `build_id=6.0.0.54.62-…`.

## Loaded-binary proof, corrected and strengthened

The running daemon (`pgphoto.stage2ondisk`, pid 13401) maps:

- `/app/lib/stage2/libgphoto2.so.6` → `5cd64dbd5708aa2228ee0379a9e456d4`
- `/app/lib/libgphoto2/2.5.27.1/ptp2.so` (stock lookup path) →
  `e6a0d8576e74af16a13e8d567bb4b81d`

Both are the candidate's bytes. The stock-path `ptp2.so` carries the same hash
as the stage2 copy `/app/lib/stage2/libgphoto2/2.5.34/ptp2.so`, so the runtime
reaches the fixed driver whichever lookup path it uses. Stale copies exist under
`/app/sd/` (`4d592aad…`, `98b210ee…`) but are not mapped.

Note: the daemon pid changed from 250 to 13401 at ≈13:23–13:25 (from
`/proc/<pid>/stat` start time against `/proc/uptime`), i.e. when the camera was
reconnected — before any capture in this section. The no-restart claims below
cover pid 13401 from that point onward.

## 1. Manual captures — PASS (3/3)

`canary-two-shot.py --expected-files 2 --expected-sp-prefix /app/sd/normal/SP_
--shot-count 3 --expected-sw 6.0.0.54.62` → **MULTI-SHOT PASS shots=3**.

Each shot reached the full lifecycle `[1, 4, 0]`, produced both obligations, and
the next shot worked (no stale/terminal state):

| shot | DNG | bytes | md5 |
|---|---|---|---|
| 1 | SP_0282.dng | 33676223 | `47a86884e744481dc852f549b81abcba` |
| 2 | SP_0283.dng | 34077144 | `22c385b9f5d41752808939752ce1ca2b` |
| 3 | SP_0284.dng | 33596805 | `455cd466825889ef5bdd19f82db4c261` |

## 2. Forced race (the original fault trigger) — PASS (2/2)

Method as first used to prove the fault: start a real capture through the app
socket, then de-authorise the camera (`/sys/bus/usb/devices/1-1.2/authorized`
0→1) while the object download is in flight. A USB disconnect is what drives the
app into `cameraRest` → `gp_params_exit` → `gp_context_unref` — the free the
fix defends against.

- Run 1: yank at +5 s. **PASS**, SP_0285 (DNG 33693707 B,
  `b3d5bccc2a729cd4963370df96c42381`) + JPG.
- Run 2: yank triggered on `state:4` (download phase) rather than on a timer, so
  it lands inside the transfer window. **PASS**, SP_0286 (DNG 33844041 B,
  `f727e84b4cc36b93eb39a6f7ff3b5b0b`) + JPG.

Daemon pid **unchanged at 13401** across both; no `stage2-crash.log` written
today; no segfault/OOM in `dmesg`. `dmesg` shows repeated
`usb 1-1.2: reset high-speed USB device…` / `authorized to connect` cycles on
that device, consistent with the de-authorisations landing (the writes alone do
not prove the device reacted, so this is the check that they did).

This is the same physical trigger that previously produced the identical
`lr`/garbage-callee crash. It no longer crashes.

## 3. Bulb — BLOCKED, not a #190 result

`--bulb-seconds 3` failed before any exposure: shutter selection returned
`261@s:44;ret:-6`. Direct probing shows the camera currently rejects **every**
shutter index — `44`, `33` and plain `21` (1/60) all return `ret:-6` — while
`286` still reports `state:1` and the 268 list is intact (57 entries, max
`00-30`, no `Bulb` entry). Manual captures continued to work immediately
afterwards.

So this is the camera refusing shutter changes, the #186 family, and it happens
before the code path #190 touches. **Bulb is untested here, not failed.**
Needs the camera to accept shutter selection again (power cycle the body /
check mode dial) before bulb can be qualified.

## 4. Plan step 1 (existing-DNG download, no shutter) — NOT RUN

The plan asks for a full PTP object download of an existing file with no shutter
operation, through the failing path. Not achieved:

- The app socket protocol exposes capture (264) and settings, no file-download
  command.
- The on-device `/app/bin/gphoto2` (2.5.27.1) returns `Bad parameters` for
  `--list-files` and finds nothing with `--auto-detect`, so it cannot drive this
  camera here.

The forced race in §2 is a stronger witness for the actual defect — it exercises
the same download path *and* the teardown that frees the context — but it is not
the no-shutter download the plan specified, and is not recorded as such.

## Attribution caveat, restated

`.62` differs from `.61` by the #190 fix **and** by `7159bb4` (#188 Stage-2
tracing composition). The §2 before/after is therefore not cleanly attributable
to #190 alone from this evidence; #188 is not ruled out. The library-side
evidence (fails-before/passes-after, ASan use-after-free) is what isolates the
defect to the context lifetime.

## Status after this session

- fault identified — yes.
- software regression passes — yes.
- built, gated, installed, identity-proven — yes.
- **Manual capture path on hardware: passes, including the previously fatal
  forced teardown race (2/2), with the daemon never restarting.**
- bulb: untested (camera refuses shutter selection — #186 family).
- plan step 1 (no-shutter download): not run; no tooling path found.

#190 stays open: bulb and the no-shutter download remain, and the attribution
caveat above stands.
