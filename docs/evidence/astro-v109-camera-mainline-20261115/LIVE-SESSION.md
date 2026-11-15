# v109 deployment and camera session — 2026-11-15

Status: IN PROGRESS from 11:54 UTC. This is a later, explicitly authorized
hardware round; PUBLICATION.md describes the earlier build/publication boundary.
Artifact bytes and build/driver SHAs remain unchanged.

## Boundaries and preflight

K-1 II is on Polaris; K-3 III is on the PC. The user authorized captures and
deployment, but cannot physically reach the K-3 III to power-cycle it. The
user's connected app is a keep-alive owner and stays connected. Do not equate
an established app socket or code-286 camera presence with an active exposure.

Polaris before installation: 6.0.0.54.108, K-1 II USB 25fb:0183, identity and
installed provenance recorded. Battery query 778 returned capacity:100;charge:2.
Current-session camera log at 11:41 reports mode 9, shooting=no, processing=no,
drive 0, bulb-timer=yes, bulb-seconds=30/1, ISO 6400. No later capture request
was present in the preserved current tail. These are preflash observations,
not a postflash mode or battery claim. SD/app free-space and empty staging
targets passed. All existing Mlog/Clog generations were saved before reboot.

## Source-defined test contract

The IT2 2625 source was traced, without copying proprietary code here:
RemoteAssistant/MtpDevice.cs Model (K-1 II, extension 1), Connect/Disconnect,
ConditionRefreshTask (100 ms), GetAllConditions release-mode selection,
CamRelease, MtpInitiatePentaxCapture/MtpTerminatePentaxCapture, and candidate
transfer/finalization; MainWindow.cs SendReleaseCommand and mouse-up/timer gate.
In B with the camera timer enabled, IT2 selects natural release mode 0, not
the application-held mode 2. A bulb:0 request alone does not prove exposure
duration, manual Bulb start/stop, or camera-timer control.

Start with the existing canary, no shutter/ISO/format writes. Require matching
firmware, ready camera, no unresolved capture, bounded completion, new published
output, downloaded full-image validation, and control afterward. Expected one
JPEG is the existing appliance publication contract, not RAW+JPEG qualification.
If safe, follow with consecutive captures in one session; stop on first error.
Do not run the full setting matrix or unattended held-Bulb/cancel sweep.

Prepared commands (execute only after installation is verified):

```sh
python3 scripts/canary-probe.py --probe --expected-sw 6.0.0.54.109
python3 scripts/canary-probe.py --shot --expected-files 1 --expected-sw 6.0.0.54.109 --shot-timeout 180 --result-json /tmp/v109-k1ii-shot1.json
python3 scripts/canary-two-shot.py --expected-files 1 --expected-sp-prefix /app/sd/normal/SP_ --shot-count 2 --expected-sw 6.0.0.54.109 --shot-timeout 180
```

The direct gphoto conditions helper cannot claim USB while pgphoto owns it;
retain that limitation rather than restarting the owner or labelling it a
camera/PTP failure. Obtain in-process condition evidence from preserved Clog.

## PC result: startup blocked

Exact clean driver e4840f4290ad5acc4df5c228dc9520b044366b87; isolated research
build passes 26/26. Runtime core/port and camlib paths verified. Camlib SHA-256
db73c7d9bed43bd85df7603283f8b5d67f69da9b1aa01dad3ea1fbc558e7ef6a.
K-3 III firmware 2.20 reports an already-open session. First failed observation:
d035 read -> 0x2017; GetAllConditions -> 0x2017; vendor enable -> 0x2002.
One --summary exits 1, before settings/preview/capture. No recovery/reset sent.
No fresh-session reproduction or restoration verified; old restoration
obligations remain. User cannot power-cycle now. Driver records committed in
4ef07e920; issue #33 updated with the exact boundary and physical prerequisite.

## Deployment result

Canonical release-fwpkt.sh started 11:56:31, with default Astro kit installation.
Transfer/verification/reboot/result still pending. No success claimed yet.

## Evidence and qualification

Raw logs, USB debug, original image bytes and installation transcript belong in
the private v109 release directory under evidence/v109-live. Keep archive bytes
unchanged and update SHA256SUMS after adding records. #251 and all unrun camera,
RAW+JPEG, setting-restoration, physical-focus and non-Pentax gates remain open.
