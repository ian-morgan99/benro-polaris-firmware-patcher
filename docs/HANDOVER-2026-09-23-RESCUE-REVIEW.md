# Polaris rescue review and o-v12g handover — 2026-09-23

## Review result

The intervening implementation did not follow the agreed TA/GitHub design for
issues #67/#123. Commit `c370c4f` described a persistent serialized scheduler,
but added unsynchronised Stage-2 globals and a preview-call-driven three-second
timer. It had no consumer ownership, session generation, serialized request
lane, last-consumer event, or positive camera-side STOP proof. It also stated
thermal causality before the required controlled A/B. Patcher commit `769b54b`
therefore reverts it without removing the useful capture-correlation work.

## Shutter continuation

o-v12f proved first-capture publication but correctly refused capture two while
`recovery_required` remained unproven. Libgphoto2 commit `252b98d57` adds only
the requested raw evidence at that recovery probe: PTP result, payload length,
fields +32/+36/+104, and the unsafe mask. It does not change the predicate or
weaken stale-candidate/unknown-state protection.

## o-v12g artifact

- Build id: `6.0.0.54.17-o-v12g-recoverydiag`
- Patcher: `769b54b` (`rescue/final-shutter-20260923`)
- libgphoto2: `252b98d5740480206756c3f1cd39f2302c0b312a`
- ZIP MD5: `459a29aff9e58f90c903ac6e3bac98c7`
- ZIP SHA-256: `8ae8c884aaff7dbdf5df604e8fa04877ac2b7d460bbb06c3f905a950031a2a74`
- appfs MD5: `661bf2810be6d0ac23946e1b56d5689c`
- Private artifact commit: `8b98a9a`
- Patcher review: PR #131
- libgphoto2 review: PR #81

The clean matched-stack build passed architecture, ABI, symbol, runtime-path,
package structure, firmwareInfo, and corresponding-source gates. The full-mode
launcher records that its legacy stock-core QEMU selftest is inapplicable; the
new core/port/camlib/iolib set was checked as a matched stack.

## Live status and next exact step

At build time the host was not associated with the Polaris AP: route to
`192.168.0.1` resolved through the home-router Ethernet interface and SSH was
refused. Repeated documented Bluetooth wake attempts did not expose BSSID
`48:E7:DA:D4:B5:73`. Consequently installation was correctly held at the
identity gate; no bytes were staged to an unverified target.

Once the AP returns: prove BSSID, Wi-Fi route, and `/app/FwVer`; stage the full
extracted tree to `/app/sd/FwPkt`; verify all six MD5s on-card; reboot with
`/sbin/reboot`; prove installed hashes and loader maps; then run one first shot
and one delayed second shot. The decisive evidence is the `recovery-probe` log.
Change the predicate only after those raw fields show which condition is stale.

## Qualification

- Unsafe Live View pseudo-scheduler: **REVERTED / NOT DEPLOYED**.
- o-v12g source/build/private publication: **PASS**.
- Device identity/install: **BLOCKED (Polaris AP unavailable)**.
- Repeated K-3 III shutter: **NOT TESTED on o-v12g**.
- K-1 II and Canon R5 II regressions: **NOT TESTED**.
- Thermal causality: **NOT PROVEN**; controlled LV residency A/B remains open.
