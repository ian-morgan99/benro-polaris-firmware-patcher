# o-v18j (`.87`) K-1 II deployment and canary — 2026-10-28

Candidate: `o-v18j-k1ii-mainline-20261028-r2` → `6.0.0.54.87`

libgphoto2 `d03a948180592337337782858c6a72064b0938ab`

patcher `7f0a3887cdbac23633dde2e3bf4408e062749ed8`

Stock base: `/home/ian/Documents/VSCodeProjects/PrivateResearch/openpolaris-research/BenroPolarisPatcher/firmware/FwPkt`
Candidate output: `out/o-v18j-k1ii-mainline-20261028-r2/`

## Verdict

**DEPLOYED and RUNTIME-VALIDATED. K-1 II physical canary PASS.** The build is
not a full camera-matrix qualification: the controlled test covered liveness,
read-only control population, preview close, and one ordinary capture. Bulb,
live-view persistence, focus, writes/restoration, and the complete widget tree
remain unqualified on this candidate.

## Build and provenance

| check | result |
|---|---|
| reproducible source | PASS — exact libgphoto2 and patcher commits above |
| deterministic libgphoto2 regression | PASS — 18 passed, 0 failed; one host serial-port test skipped because no DTR/CTS fixture was available |
| Python regression suite | PASS — 393 passed |
| pre-release gate | PASS — 16 passed, 0 failed, 1 prerequisite skip |
| ZIP MD5 | `2ec045f6fc9ba860c7ebb2a2c293fbc6` |
| ZIP SHA-256 | `8fb41c4cddae0483dac8ca960937e38ecb495d9b8bf8e225c1296c580138a4a9` |
| appfs MD5 | `643bf6cdee085b309d59e10663e0ca51` |

The first `.87` attempt was rejected before publication because its release
manifest used numeric issue values. It was not installed or published. The
published and tested artifact is the `-r2` candidate above.

## Installation and runtime identity

The extracted `FwPkt/` tree was staged through the canonical installer. All six
on-device `firmwareInfo` MD5s matched the candidate. The device rebooted, with
uptime resetting from 5270 seconds to 14 seconds, and reported:

```text
FwVer:6.0.0.54.87;date:2026.10.28;
build_id=6.0.0.54.87-o-v18j-k1ii-mainline-20261028-r2
libgphoto2=d03a948180592337337782858c6a72064b0938ab
patcher=7f0a3887cdbac23633dde2e3bf4408e062749ed8
```

The packet is published in PrivateResearch under the matching candidate
directory. Its README is marked `installed-verified`.

## K-1 II physical canary

Body identity was read from the Polaris control protocol as Pentax K-1 Mark II,
with `state:1` and `photoFormat:1`. Direct read-only control queries returned:

- ISO: 12 advertised values;
- shutter: 56 advertised values, including the camera's zero sentinel at the end;
- aperture: a populated advertised list.

The normal capture canary then passed with the expected software identity:

- preview was stopped and confirmed idle (`291 state:0;ret:0;`, then code 292 idle);
- one ordinary capture completed with lifecycle `[1,4,0]`;
- one file arrived: `/app/sd/normal/SP_0479.jpg`, 2,023,069 bytes;
- completion took about 20 seconds;
- no terminal error or process crash was observed.

The result is intentionally recorded as a JPEG capture because that is the file
the camera returned in this state. This test does not infer a generic image
format mapping or claim PEF/DNG support.

## Repeat capture — 2026-10-28 23:54 UTC

After the read-only rerun, a second independent ordinary capture also passed:

- software identity remained `6.0.0.54.87`;
- preview was already idle before capture;
- lifecycle was `[1,4,0]`;
- file event reported `/app/sd/normal/SP_0480.jpg`, 2,935,204 bytes;
- the camera returned to idle without an error or process crash.

Transcript and JSON result: `physical/k1ii-v87-capture-rerun.log` and
`physical/k1ii-v87-capture-rerun.json` in the candidate output directory.

Polaris liveness also passed 3/3 read-only attempts. The test did not alter
camera settings and did not run Bulb, persistent live view, focus movement, or
long-duration capture.

## Evidence limitations and tooling findings

- A second `gphoto2` session could not claim the USB camera while the running
  Polaris service owned it. Its generated empty shutter-list report is an
  ownership failure, not evidence that the K-1 II list is empty. The direct
  protocol result above is authoritative for this run.
- The app-burst read-only sweep showed populated ISO, shutter, and aperture
  values. Codes 267, 266, and 823 did not provide usable replies in that sweep;
  this is recorded as an integration observation, not classified as a K-1 II
  control failure. Code 266 has a separate successful liveness path.
- `wait-for-rig.py` falsely reported the wrong network because it parsed the
  route's trailing `cache` token as the interface. Network association,
  routing, SSH, and the device tests were independently confirmed.
- The archived Mlog/Clog pull ended with a device-side tar/SD input-output error.
  Current `Mlog.txt`, `Clog.txt`, process state, and error output were pulled
  manually under `physical/logs-current/`; no application crash was found in
  the available current logs. The full raw build/install and test logs remain
  under the candidate output directory.

This is a Polaris runtime and hardware canary record. It is not a substitute
for direct-PC libgphoto2 qualification or OpenPolaris end-to-end qualification.
