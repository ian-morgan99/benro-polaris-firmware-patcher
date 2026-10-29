# v90 post-deployment regression gate

This is the mandatory acceptance sequence for candidate
`o-v18m-k1ii-pgphoto-readiness-20261029` (`6.0.0.54.90`). A published ZIP or a
successful flash is not a regression result. The result must be tied to the
exact installed identity and recorded per camera and per layer.

## Current candidate identity

| Item | Required value |
| --- | --- |
| Display firmware | `6.0.0.54.90` |
| Build ID | `6.0.0.54.90-o-v18m-k1ii-pgphoto-readiness-20261029` |
| libgphoto2 | `63a894b0821a510fc40244c5cc4ef84a5220a91c` |
| patcher used for the artifact | `f344e41261a886f8f6107b9467095bc90b3835a1` |
| ZIP SHA-256 | `829fd30e79a52b2155bd865e1fb584fc82f7785bfad31d4878de7fe31a01ab34` |
| ZIP MD5 | `4c005b0acf50676fa7e1d32ffbac9cd6` |
| Publication | [PrivateResearch v90 packet](https://github.com/ian-morgan99/PrivateResearch/tree/main/firmware-packets/6.0.0.54.90--o-v18m-k1ii-pgphoto-readiness-20261029) |

If any identity value differs, stop. Do not interpret the test as v90
evidence. v90 is now installed-verified on Polaris using the documented
Bluetooth/Wi-Fi wake and `release-fwpkt.sh` process. The receipt is published
with the packet; physical camera qualification is still pending.

## Gate 0 — exact runtime identity

From the canonical patcher checkout, after deployment:

```sh
python3 scripts/verify-candidate-identity.py \
  out/o-v18m-k1ii-pgphoto-readiness-20261029 --require-deployable
scripts/verify-installed-build.sh \
  out/o-v18m-k1ii-pgphoto-readiness-20261029 --host 192.168.0.1
```

Save the installer receipt, the complete installer log, the device `FwVer`,
the on-device provenance file, uptime before/after, and the firmwareInfo
verification. No camera operation is allowed before this gate passes.

Subsequent operator testing reported a K-1 II physical failure on v90: B-mode
initiation crashed Benro Connect, and M-mode testing showed reconnects, very
slow controls and capture, and unreliable writes. The earlier no-camera result
at installation remains a separate observation. v90 is **not K-1 II qualified**
and must not be promoted on the strength of its verified installation.

## Gate 1 — repeat the offline and packaged regression gate

Run the gate against the exact candidate directory and the exact libgphoto2
source tree used to build it:

```sh
bash tests/run_deterministic.sh
bash tests/run_prerelease_gate.sh \
  --build out/o-v18m-k1ii-pgphoto-readiness-20261029/FwPkt \
  --libgphoto2-src .buildtmp/libgphoto2-v90-src
```

Expected v90 result is zero failures. The known stock `firmwareInfo` check may
remain a prerequisite skip when the stock firmware is held in
`PrivateResearch`; record that skip and do not describe it as a pass.

The v90 baseline at build time was 24 deterministic checks and 393 Python
tests, with 16 pre-release checks passing, zero failing, and one stock-manifest
prerequisite skip. A repeat must not silently run fewer tests.

## Gate 2 — direct libgphoto2 (Layer A)

With the camera connected directly to the test PC, use the exact libgphoto2
SHA from the candidate. Record `CAMERA`, `ATTACHMENT=PC`, `LAYER=A`, and the
actual loaded camlib/core/port paths. For each available body, run:

1. cold detection and model/USB identity;
2. complete widget/config enumeration;
3. one safe setting read, write, independent read-back, and restoration for
   shutter, ISO, aperture, EV, white balance, and focus where advertised;
4. preview start, valid frame, stop, and restart;
5. ordinary capture and download integrity;
6. reconnect, process restart, and camera power-cycle checks.

The direct run is the library boundary. A Polaris or OpenPolaris result must
not be copied into this record.

## Gate 3 — packaged Polaris local path (Layer B)

The standard qualification runner is **BLOCKED**: it includes an automatic
Bulb shot and the v89/v90 Bulb dispatch and cancellation paths have unresolved
defects ([#251](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/251)).
Do not run Bulb capture or cancel on these builds. Record the Bulb cases as
BLOCKED, not passed. A replacement runner requires a verified clearance bound
to the exact build before it can make a Bulb request.

Offline disassembly of v90 also shows that the common Bulb stop callback
overwrites the saved result after the cancel branch enters it. Correcting the
branch condition alone therefore does not establish that cancellation remains
visible to the caller, or that the physical shutter closes. Review the complete
stop, error and file-publication lifecycle before clearing this block.

After Gate 0 passes, perform the read-only checks and any separately approved
ordinary M-mode checks below without invoking the blocked round. Keep the
per-case evidence and do not repeat a shutter after an ambiguous result merely
to obtain a green line.

Run the following control matrix separately for each attached body, recording
PASS, FAIL, BLOCKED, or UNRUN:

| Area | K-1 II | K-3 III | Required evidence |
| --- | --- | --- | --- |
| cold connect/readiness | required | required | startup time, pgphoto restarts, USB identity |
| widget tree and advertised values | required | required | full config output and descriptor comparison |
| setting round-trips | required | required | old value, advertised new value, fresh read-back, exact restore |
| white balance | required, including WB widget | required | named widget and raw/property evidence where applicable |
| shutter list | required | required | live list, model-specific encoding, no fabricated entries |
| live view | required | required | start/frame/stop/restart, no crash |
| focus and AF-with-live-view/StarAF | required | required | model-gated path, movement/result, cleanup |
| ordinary M capture | required | required | lifecycle, file publication, downloaded file, idle state |
| repeated capture | required | required | bounded multi-shot run, stable process/USB identity |
| Bulb/timed-B | only where the camera advertises and preconditions are safe | separate controlled test | duration, file, terminal cleanup, no battery/thermal fault |

For every setting write, use the camera's advertised descriptor and verify the
changed value before restoring the original. For K-1 II, allow for the known
asynchronous `GetAllConditions` update and record the later live condition
read-back; a stale descriptor value is not proof of application.

## Gate 4 — retained camera and consumer regressions

The mandatory no-regression matrix also includes any body previously claimed as
physically supported, especially:

- Canon EOS R5 Mark II reference camera;
- Pentax K-3 III;
- Pentax K-1 II;
- any subsequently qualified K-1, K-3 III Monochrome, or K-5 II.

For each available body repeat detection, config, safe write/restore, preview,
capture/download, repeated capture, reconnect, USB replug, power-cycle, and
model-specific controls. Run OpenPolaris/Benro Connect separately as Layer C;
do not promote a Layer C result to direct-library evidence.

## Gate 5 — health and failure review

Before and after every body/session:

- pull Mlog and Clog before rotation;
- record camera and battery temperature if Polaris exposes it;
- record pgphoto/polestar PIDs, RSS/fd counts, USB identity, and kernel faults;
- confirm no unexpected restart, crash, camera disconnect, stale output, or
  unclosed capture;
- check the card/output inventory and remove no evidence until it is copied;
- stop on a crash, thermal warning, invalid payload, empty widget, or
  unexplained timeout.

Classify the first divergent layer using the A/B/C rules in
`docs/LIBGPHOTO2-UPGRADE-PROCESS.md`. Open or update the issue for the first
failure; do not paper over it with a retry or a consumer-only workaround.

## Release decision and records

The candidate remains **GATED** or **INSTALLED-VERIFIED** until the exact
evidence exists. It becomes **PHYSICALLY-QUALIFIED** only for the camera rows
that pass, and **RELEASE-QUALIFIED** only when the mandatory available-camera
matrix, rollback/provenance checks, and required consumer layer have passed.

Update all of the following with the exact build ID and commit:

- `docs/RELEASE-VERSION-STATE.md`;
- `docs/TESTED.md`;
- `docs/PENTAX-CAPABILITY-RETENTION.md`;
- `docs/evidence/<candidate>-install-<date>/`;
- the relevant GitHub upgrade/qualification issue.

Never mark an unavailable camera `PASS`, silently turn a historical `PASS` into
`N/A`, or call an offline gate a hardware qualification.
