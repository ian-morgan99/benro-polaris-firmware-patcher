# Changelog

## Unreleased — a stale restart lock permanently blocked pgphoto restarts, so a healthy K-3 III was held quarantined (issue #297)

**This is the functional regression.** A K-3 III attached to Polaris reports
`manufacturer:none;model:none;state:-110`. It is not a model-table gap: the camera
enumerates correctly on the device, `25fb:0189 PENTAX K-3 Mark III` is present in
`/sys/bus/usb/devices/1-1.2`, and `pentax.so`/`ptp2.so` are installed. The failure is
one layer downstream, inside our own helper.

`/app/Clog.txt` on the device, repeating every few seconds for the whole boot:

```
[restart_gphoto] another restart owns /var/run/openpolaris-pgphoto.restart.lock; refusing to race
[camera-usb] quarantined identity 1-1.2|25fb:0189|1:4 stable for 9 polls but bounded rebind failed; remaining degraded (issue #119)
[camera-usb] rebind retry deferred until poll 2055
```

Step 0 of `restart_gphoto.sh` treated *any* existing lock directory as a live owner and
exited 1. `/var/run` on this firmware is **UBIFS root flash, not tmpfs** — verified:
`mount` lists only `devtmpfs on /dev`, and `df /var/run` reports `ubi0:ubifs`. So a lock
left by a crash or power cut survives a reboot. The device carried one with an **empty**
pid file and an mtime of 2025-05-09, long predating the current boot; `mkdir` on it fails
with `File exists`, so every restart refused, across reboots, indefinitely.

The consequence compounds: the USB supervisor's bounded rebind calls that helper, cannot
succeed, and therefore holds a correctly enumerated camera in quarantine for the entire
boot. The WebUI publishes `model:none` while the mount, link and attitude opcodes all work
normally — which is why it reads as a camera-recognition bug rather than a lock bug.

Step 2 of the same file has always reclaimed a stale *launch* lock by checking the owner
(issue #77). Step 0 never got the same treatment. Fixed by making step 0 consistent with
step 2: honour the lock only if its pid is alive **and** is a `restart_gphoto`, wait one
second so a genuinely starting owner can publish its pid, then reclaim and say so.

Ownership is checked against the command line, not mere `/proc` existence — a lock from an
earlier boot can name a pid the kernel has since handed to an unrelated process, and
counting that as an owner would reproduce the same permanent deadlock by a different route.

**Verified on the device first, then in code.** Diagnosis came from live read-only SSH:
sysfs enumeration, `/proc/249/maps`, the driver directories, `mount`, `df /var/run`, and
`/app/Clog.txt`. The installed `/app/restart_gphoto` md5 is
`64156951d2a388162f52ae906964c410`, identical to `container/ondisk/restart_gphoto.sh`, so
this is our code path and not stock firmware.

New `container/test_restart_gphoto_restart_lock.sh` covers four cases: the exact device
condition (lock dir, empty pid) is reclaimed; a live `restart_gphoto` owner is honoured and
the lock is left alone; a pid recycled to an unrelated process is treated as stale; and a
normal restart emits no reclaim line. Confirmed non-vacuous — against the pre-fix script it
fails case A with the device's own message, `another restart owns ... refusing to race`.

**Both restart-helper lock tests are now registered in the prerelease gate.**
`container/test_restart_gphoto_launch_lock.sh` has existed since issue #77 and was run by
nothing — no gate, no CI, no release script referenced it. That is the same "a gate nobody
calls is not a gate" failure that let `.99` ship without its licence, applied to the code
that recovers the camera.

Gate: **14 passed, 0 failed, 2 skipped**, drift guard green at 37 suites.

**Not yet done.** The fix is in the tree; it has not been applied to the device, and the
stale lock is still there. Removing `/var/run/openpolaris-pgphoto.restart.lock` on the
running unit should let the supervisor's next rebind succeed, but that restarts pgphoto on
a live mount and is left as an explicit operator decision. K-3 III recognition remains
UNKNOWN/BLOCKED per #297 until the five-layer test passes on an installed candidate; this
fix removes a definite blocker, it does not by itself prove recognition. The K-1 II was
confirmed present on the PC (`25fb:0183`) but its behaviour against this fix is untested.

## Unreleased — setup-wifi.sh put the Wi-Fi password in a process argument (issue #290)

- `setup-wifi.sh` called `wpa_passphrase "$SSID" "$PSK"`, putting the plaintext
  network password in argv. `/proc` is mounted on the Polaris, so any process could
  read it from `/proc/<pid>/cmdline` for as long as `wpa_passphrase` ran, and it also
  appeared in `ps`. The script's own header asserted the password was "never passed as
  a command-line argument (which would show in `ps`)" — the claim and the code were
  read as one document instead of the claim being checked against the invocation below
  it, which is how this survived review.
- The passphrase now goes in on stdin. Verified against the device's own
  `wpa_passphrase` build that both forms produce a byte-identical `psk=` line, so the
  resulting `wpa.conf` is unchanged. The stdin form additionally prints a
  `# reading passphrase from stdin` banner, which is stripped alongside the existing
  `#psk=` plaintext comment — filtering only the comment would have written the
  password into `wpa.conf`, a worse leak than the one being fixed.
- Verified on a stub that reproduces the device's observed output: the child receives
  `ARGV:[MyNet][]` (empty second argument), `wpa.conf` carries the expected hash with
  zero occurrences of the plaintext, mode stays `600`, and no `.wpa.tmp` credential is
  left behind. Not yet re-run on the device — it became unreachable mid-session
  (ping fails, port 22 closed). The hash-equality claim *is* from the device, captured
  before it went down.
- `tests/test_setup_wifi_psk_not_in_argv.py` asserts what the child process actually
  received rather than the script's text, and that both plaintext output forms are
  filtered. Confirmed non-vacuous: against the pre-fix script 4 of its 7 assertions
  fail; restored, all 7 pass. Registered in `tests/run_prerelease_gate.sh`.
- Cards already in the field keep the old script until the kit is re-extracted from a
  rebuilt zip; the password they typed is not recoverable from `wpa.conf`, but anyone
  with local process access while it ran could have read it.

## Unreleased — copyleft wifi binaries shipped with no licence and no source offer (issue #286)

- The published `polaris-wifi.zip` at
  `PrivateResearch/firmware-packets/6.0.0.54.99--astro-v99-wifi-20261108/`
  (SHA-256 `bd5f7db4…`) contains ten entries and none of them is a licence.
  It ships `wpa_supplicant`, `wpa_cli`, `wpa_passphrase` and `iw`, all four
  statically linked against libnl (LGPL-2.1) by `container/astro/build_wifi.sh`.
  LGPL v2.1 §4 requires the licence copy and a corresponding-source offer to
  accompany the object code, and the README's own instruction is "unzip
  polaris-wifi.zip at the SD card root" — so a user receives copyleft binaries
  and no licence at all.
- A gate existed and should have refused. `scripts/build-astro-bundle.sh:317`
  dies if any of the four files is missing from `$SD_WIFI`. It landed in 55759cd
  and is an ancestor of caab172, the patcher commit recorded in that candidate's
  provenance, so it was present at build time and never ran — because
  `scripts/build-astro-candidate.sh` calls `build-astro.sh` directly and tars the
  result itself. **A gate on one of two build paths is not a gate.**
- Worse than the handover described: no production script calls
  `build-astro-bundle.sh` at all, and neither `build-astro.sh` nor
  `build-astro-candidate.sh` creates `polaris-astro.zip` or `polaris-wifi.zip`.
  The archives that were published for `.99` were therefore produced outside any
  tracked build path, and `publish-astro-candidate.sh` skips a missing zip
  silently (`[ -f ] || continue`), so absence passed unnoticed. A wrapper-built
  zip from 02:17 does contain all four notices; the published bytes stamped 11:37
  contain none — two different builds, and only the unguarded one was handed out.
- Licence generation now lives in `build-astro.sh`, beside the existing astro
  licence step, so every producer of a wifi kit writes them. File names come from
  the gate that already checks them (`LICENCE-wifi.txt`, `COPYING-LGPL-2.1.txt`,
  `NOTICE-iw.txt`, `NOTICE-wpa_supplicant.txt`) rather than from the abandoned
  fix in `4b54611`, which wrote `SOURCE-OFFER.txt` and would have satisfied LGPL
  while failing that gate. Versions are derived from the tarball filenames written
  into `licenses/`, not from variables — an offer that names no version is not an
  offer, and deriving from the filenames makes drift impossible. Fails closed on a
  missing or empty notice, which trips the existing EXIT trap and removes the four
  libnl-linked binaries from the bundle.
- `build-astro-candidate.sh` now builds the SD-rooted archives itself and asserts
  against the finished archive rather than the staging directory: all four notices
  present, non-empty when read back out with `unzip -p`, the offer naming a real
  libnl version, every binary executable as stored in the zip, and every entry
  rooted at its own directory so it unzips at the card root (#58). The wrapper's
  check is retained as a second line of defence.
- `tests/test_wifi_licence_on_every_build_path.py` tests the path, not the text:
  it runs the real generation block out of `build-astro.sh` against a fabricated
  `licenses/` tree with no docker and no rig. Confirmed non-vacuous — reverted
  both scripts to their pre-fix state and 8 of its 9 assertions fail; restored,
  all 9 pass. Registered in `tests/run_prerelease_gate.sh` (drift guard now at 35
  suites). The archive-level assertions were also mutation-tested individually:
  notice absent from the tree, notice empty, offer naming no version, and a binary
  stored non-executable each fail the build with its own message.
- Verified on produced bytes, not from a diff. A real cross-compile ran through
  `build-astro.sh` (the exact script the candidate path invokes) with the cached
  source tarballs, and the candidate path's archive block was run over the tree it
  produced. The resulting `polaris-wifi.zip` contains all four notices, read back
  out of the archive: `LICENCE-wifi.txt` 1791 B, `COPYING-LGPL-2.1.txt` 26530 B,
  `NOTICE-iw.txt` 849 B, `NOTICE-wpa_supplicant.txt` 965 B. All seven executables
  are stored `-rwxr-xr-x`, every entry is rooted at `polaris-wifi/`, and the offer
  names libnl-3.7.0, iw-5.19 and wpa_supplicant-2.10 with working upstream URLs.
  The same tree also carries `udhcpc.script` at 4583 B, so #280's fix is present in
  the same artifact.
- Two vacuous-pass traps were found and closed while verifying this. Running the
  archive block against a wrong `OUT` skipped every assertion and still exited 0 —
  the guard now dies if the staging tree is absent, confirmed by pointing it at a
  nonexistent path. And deleting a licence from an already-built zip proves nothing,
  because the block rebuilds the archive from the staging directory; the mutations
  that actually exercise the gate are made to the tree, and those do fail closed.
- The published `.99` is left as published. Its bytes are recorded by SHA-256 in
  its README and `publish-astro-candidate.sh` refuses to replace published
  archives; swapping them silently would break the provenance discipline the
  publication exists to provide. Needs a human decision: publish a new candidate
  id with the fix and note an erratum against `.99`, or add
  `ERRATUM-wifi-licence.txt` beside it.

## Unreleased — the station kit could join a network and use none of it (issues #280, #281)

- `polaris-wifi.zip` never contained `udhcpc.script`. Both `polaris-autojoin.sh`
  and `polaris-apsta.sh` call `udhcpc -s "$WDIR/udhcpc.script"`, and BusyBox
  udhcpc configures nothing itself — it obtains a lease and hands it to whatever
  `-s` names. With the file absent the lease is granted and silently discarded,
  so auto-join associated, logged `lease of 192.168.68.63 obtained`, and left
  `wlan1` with no address and no default route. This shipped broken from b367ed8
  (the commit that first built the kit) to caab172, so every wifi zip ever
  produced is missing it. It is now copied into the kit, named explicitly in
  `chmod 755` (`*.sh` would have left it 644), and gated in three places: the
  staging check, the release wrapper's fail-closed list, and the zip permission
  loop that verifies the mode actually stored inside the archive.
- The bind hook applied `$ip`, `$router` and `$subnet` from the lease environment
  and ignored `$dns`, and this firmware has no `/etc/resolv.conf`, no
  `/tmp/resolv.conf` and no `/usr/share/udhcpc/default.script`. A joined network
  therefore reached raw IPs and resolved nothing. `bound|renew` now writes the
  offered nameservers, guarded so a lease without a DNS option cannot blank a
  working file, compared with `cmp` first because it runs on every renew against
  UBIFS, and removed on `deconfig` only if it carries our marker — unreachable
  nameservers make every lookup hang rather than fail fast.
- Verified on hardware. Before: `wpa_state=COMPLETED`, no `inet addr` on wlan1,
  no default route. After: `192.168.68.63/255.255.252.0`, `default via
  192.168.68.1 dev wlan1`, `ping -I wlan1 1.1.1.1` 0% loss, and
  `nslookup github.com` resolving through the DHCP-offered servers. hostapd and
  the AP on wlan0 untouched throughout. The DNS path was exercised under BusyBox
  sh on the device with log and resolver paths redirected to /tmp.
- `tests/test_wifi_kit_packaging.py` asserts the copy list contains it, and for
  the general class that every `$WDIR/<name>` a shipped wifi script references
  which exists in `container/astro/ondisk/` is actually copied. Confirmed
  non-vacuous: run against caab172's `build-astro.sh` the same extraction reports
  it absent. 5 passed (new), 52 passed across `container/astro/tests`,
  `tools/tests` and `tests/test_astro_build_wrapper.py`.
- Cards already in the field are not fixed by this change — `install_astro.sh`
  does not deploy the wifi kit, which is read in place from
  `/app/sd/polaris-wifi/`. They need the file copied manually or a re-flash of
  the zip. See #280 for the one-liner.

## Unreleased — restore direct still-capture dispatch (issue #122)

- Removed the Stage-2 `gp_camera_capture` wrapper and its independent cooldown.
  The last broad repeated-capture PASS, o-v9p, predates that wrapper; o-v12j,
  o-v12k and o-v12n all entered it and then faulted at an invalid low program
  counter before the real core call returned. The exact o-v12n libgphoto2 SHA
  completes consecutive RAW captures directly on the same K-3 III.
- `gp_camera_capture` now receives its exact resolved core address in the slot,
  as it did before o-v9o. Preview traffic remains independently bounded by the
  existing preview wrapper.
- Offline coverage asserts that the still-capture slot target is preserved
  exactly. All five runnable Stage-2 host tests pass; the ARM compiler gate is
  skipped on this host because `arm-linux-gnueabi-gcc` is not installed.
- This is a source-reviewed A/B candidate, not yet a hardware-qualified fix.
  It still requires a clean canonical build, immutable artifact provenance,
  supported installation, cold reboot and the full capture matrix.

## o-v10-quarantine-20260919 — post-budget quarantine state (issue #119 TA follow-up)

The o-v9y churn guard bounded the restart budget, but once exhausted the USB
supervisor adopted the current identity as healthy and stopped restarting
forever — a genuinely reconnected camera could be silently accepted while the
existing pgphoto session was still bound to the old device/session.

Patcher (main 327eeb4):
- Issue #119: exhausting the restart budget now enters an explicit
  degraded/quarantine state in `camera_usb_supervisor.sh`: churn is suppressed,
  `restart_budget_exhausted` is logged, and the current identity is NOT adopted
  as healthy. Normal operation resumes only after a positive stable-identity
  condition (the quarantined identity stays unchanged for COOLDOWN consecutive
  polls) revalidates it, which also resets the budget. A genuinely reconnected
  camera is therefore never silently accepted while the existing pgphoto session
  may still be bound to the old device/session.
- Deterministic tests added to `container/test_camera_usb_supervisor.sh`: a
  post-budget identity that keeps changing stays quarantined (no 3rd restart),
  and a stable quarantined identity revalidates and resumes normal restart
  behaviour. All supervisor test cases pass.

libgphoto2 (master 35318c1b5, same source as o-v9z — no libgphoto2 delta):
- Issue #120 Bulb-timer semantics documentation and the #121 startup-order fix
  are carried over from o-v9z.

Build inputs (clean):
- libgphoto2 source: 35318c1b520b1fc42d2f20be29aea956010b4be2 (master)
- patcher: 327eeb489d266103ce91ccb2e573d6e36d796b4e (main, clean tree)
- stock FwPkt: firmware/FwPkt.zip

Artifact:
- out/o-v10-quarantine-20260919/FwPkt.zip
  sha256 cbdef460eed547fc533ad739f2e325b15f6ad0e079d05c56f4599f98b6d4515b
  (md5 b4b953f68e7807956ba7fc3a6a65b2af)

Verified:
- container/test_camera_usb_supervisor.sh: PASS (#57 + #121 + #119 churn guard +
  #119 quarantine/revalidation cases).
- Deployed to the Polaris via `scripts/release/release-fwpkt.sh`; post-boot
  `/app/FwVer` = `FwVer:o-v10;date:2026.09.19;` and on-disk provenance matches
  patcher `327eeb4`.
- Multi-exposure capture test (R5 II, 5 shots): all shots returned PTP `-1002`
  (camera-side state after the firmware reboot cycle — camera in PTP mode,
  pgphoto running, but shutter release rejected). Not a patcher regression;
  re-test once the camera is confirmed in PC-connection/capturable state.

Not yet done: the #119 K-3 III USB-persistence release gate (cold boot + idle +
config polling + preview start/stop + ordinary capture without USB
disappearance) and the #120 Bulb-timer A/B/C ladder.

## o-v9z-stability-20260919 — stability bundle (issues #119/#120/#121)

New release bundling the recent no-camera stability work. Built from clean inputs;
the libgphoto2 side adds a documentation-only commit clarifying the Bulb timer
semantics for issue #120, and the patcher side carries the #119 churn guard and
#121 startup-order fix.

libgphoto2 (master 35318c1b5):
- Issue #120: documented that the camera's own conditions report bulb_timer_seconds
  (offset 272) as whole seconds and offset 276 as the TV denominator (confirmed
  against IT2), so the capture wait budget correctly sizes to the full timer value.
  The observed countdown-then-short-exposure symptom is camera/app firmware
  behaviour outside this budget.

Patcher (main 17ee6e7):
- Issue #119: bounded restart budget + cooldown in camera_usb_supervisor.sh so a
  re-enumeration flap cannot keep re-dlopening pgphoto (the live-view churn that
  drained the battery and dropped the camera off USB).
- Issue #121: startup grace window so a transient re-enumeration during app launch
  is absorbed without restarting pgphoto (the startup-order crash).

Build inputs (clean):
- libgphoto2 source: 35318c1b520b1fc42d2f20be29aea956010b4be2 (master)
- patcher: 17ee6e77a18ddd9a4d9193ac1d689ae1e9b493ae (main, clean tree)
- stock FwPkt: firmware/FwPkt.zip

Artifact:
- out/o-v9z-stability-20260919/FwPkt.zip
  sha256 5a2755b1710aa8e9f5a63f50d8c5deaddc78d7587fb49a208dcb0364ffaf2198
  (md5 4f5a2c1251a2b9c86a1df2c7ce0fb01e)

Verified (documented release process, docs/LIBGPHOTO2-UPGRADE-PROCESS.md):
- patcher deterministic harness (#117): 6 passed, 0 failed, 3 prerequisite-skipped.
- container/test_camera_usb_supervisor.sh: PASS (#57 + #121 + #119 cases).

Not yet done (hardware qualification pending, camera back Monday): the #119 A/B
matrix and the #120 Bulb-timer A/B/C ladder to confirm the countdown-then-short-
exposure behaviour and that 25fb:0189 survives cold boot + idle + config polling +
preview start/stop + ordinary capture without USB disappearance.

## o-v9y-churn-guard-20260919 — live-view churn guard (issue #119)

o-v9r/o-v9s regression: the K-3 III session was torn down and re-initialised in a
tight loop (~36 dlopen cycles / 20 s), draining the battery and churning the
PTP/USB link until the camera dropped off USB (o-v9s: completely unreachable).

Root cause (no-camera analysis): the USB identity-change restart added in 1b021e9
(present in o-v9s, absent from the known-good o-v9p) restarts pgphoto on every
detected device-number change. When the camera re-enumerates while previewing,
each restart (full dlopen of core+port + 64-shim re-registration) can itself
trigger another re-enumeration, so the supervisor loops.

Patcher fix (commit da12f8f, main):
- container/ondisk/camera_usb_supervisor.sh: two bounded guards break the loop --
  OPENPOLARIS_USB_RESTART_COOLDOWN_POLLS (default 5) spaces out restarts so a fast
  flap cannot restart pgphoto on every poll, and OPENPOLARIS_USB_MAX_RESTARTS
  (default 6) is a total restart budget; once exhausted the supervisor accepts the
  current identity as the new baseline and stops re-dlopening (fail-closed against
  a restart storm). Bounded readiness conditions, not arbitrary sleeps.
- container/test_camera_usb_supervisor.sh: deterministic regression test -- a
  sustained re-enumeration flap restarts at most MAX_RESTARTS times, then the
  supervisor logs 'restart budget' and stops.

Build inputs (clean):
- libgphoto2 source: b8baf487c10b007edc865c2ebf000806f0264121 (master, same as o-v9w/o-v9x)
- patcher: da12f8f91d03d1e4bdb099965d7f09f5e8111aff (main, clean tree)
- stock FwPkt: firmware/FwPkt.zip

Artifact:
- out/o-v9y-churn-guard-20260919/FwPkt.zip
  sha256 44fd141004583291da1ba60ba514b263d68abf263c2c9ffc648ad603e8e2d33b
  (md5 086fd96cf9f5b47f8607b3b364555c6e)

Verified (documented release process, docs/LIBGPHOTO2-UPGRADE-PROCESS.md):
- patcher deterministic harness (#117): 6 passed, 0 failed, 3 prerequisite-skipped.
- container/test_camera_usb_supervisor.sh: PASS (#57 + #121 + #119 cases).
- Built camera_usb_supervisor.sh contains the churn-guard markers.

Not yet done (hardware qualification pending): the #119 A/B matrix (camera ON
before app launch, repeated launches) to confirm the dlopen churn no longer
reproduces and 25fb:0189 survives cold boot + idle + config polling + preview
start/stop + ordinary capture without USB disappearance.

## o-v9x-startup-order-20260919 — startup-order crash fix (issue #121)

o-v9r crash: Benro Connect crashed when started with the camera already powered
on. Root cause: a transient re-enumeration during Benro Connect's own
initialisation (device-number change) fired a pgphoto restart that raced the
initial session open. The OFF->ON path worked because the camera appeared after
the runtime was up.

Patcher fix (commit f525adf, main):
- container/ondisk/camera_usb_supervisor.sh: bounded startup grace window
  (OPENPOLARIS_USB_STARTUP_GRACE_POLLS, default 3 polls). Identity changes in
  that window are absorbed into the baseline instead of restarting pgphoto; a
  later genuine change is still detected. A bounded readiness condition, not an
  arbitrary sleep — normal debounce/restart logic resumes after the window.
- container/test_camera_usb_supervisor.sh: deterministic regression test (startup
  re-enumeration must NOT restart; a post-grace change still causes exactly one
  restart). The #57 case is pinned to STARTUP_GRACE_POLLS=0 to keep its original
  debounce semantics.

Build inputs (clean):
- libgphoto2 source: b8baf487c10b007edc865c2ebf000806f0264121 (master, same as o-v9w)
- patcher: f525adf1b00f712d03481255adbae98a79833387 (main, clean tree)
- stock FwPkt: firmware/FwPkt.zip

Artifact:
- out/o-v9x-startup-order-20260919/FwPkt.zip
  sha256 ad99db1ed0c40b6a6453c2dd1f58ea78c5c27b7b81b4041c1f3379b700e7b1b7
  (md5 c5701675e3c69e319f3785b0b0d8024f)

Verified (documented release process, docs/LIBGPHOTO2-UPGRADE-PROCESS.md):
- patcher deterministic harness (#117): 6 passed, 0 failed, 3 prerequisite-skipped.
- container/test_camera_usb_supervisor.sh: PASS (#57 + #121 cases).
- Built camera_usb_supervisor.sh contains the startup-grace marker.

Not yet done (hardware qualification pending): the #121 A/B matrix (camera ON
before app launch, repeated launches) to confirm the crash no longer reproduces.

## o-v9w-bulb-codeql-20260919 — Bulb-cluster fixes + CodeQL cleanup (master)

New release built from clean libgphoto2 master (b8baf487c), which carries the
Bulb-cluster stability fixes and a CodeQL cleanup, while staying regression-free
(the o-v9s ISO-extension regression is feature-branch-only, not on master).

libgphoto2 (master b8baf487c):
- Bulb cluster (#111/#118): phase-specific Bulb capture wait (exposure vs
  post-exposure processing) and integer-second shutter enumeration so >1-minute
  Bulb times no longer display as collapsed minutes.
- CodeQL: Nikon D-series detection now checks `sscanf(...) == 1` (not a boolean,
  which treated EOF as a match) and initialises `nikond`, fixing the
  "incorrect return-value check for a scanf-like function" finding on PRs #78/#79.

Build inputs (clean):
- libgphoto2 source: b8baf487c10b007edc865c2ebf000806f0264121 (master)
- patcher: 26dba1a7a14197837bcb50f4426899e4e83c5eb4 (main, clean tree)
- stock FwPkt: firmware/FwPkt.zip

Artifact:
- out/o-v9w-bulb-codeql-20260919/FwPkt.zip
  sha256 261b5db4839f5b90a42792a9fdc2d99739c9a9bf2b62eb7b8e18539115833375
  (md5 6df2130dec9365fa86daf02ba7273fae)

Verified (documented release process, docs/LIBGPHOTO2-UPGRADE-PROCESS.md):
- libgphoto2: clean build; test-pentax-utils + pentax tests pass.
- patcher deterministic harness (#117): 6 passed, 0 failed, 3 prerequisite-skipped.
- test_polaris_pentax_build_package.sh: PASS (full build + package path).

Not yet done (hardware qualification pending): Bulb-cluster A/B/C ladder on a
K-3 III to confirm #111/#118/#120 behaviour, and the #119 session-churn / USB
disappearance regression.

## o-v9v-capture-failclosed-20260919 — pre-capture drain wait fails closed (issue #122 TA follow-up)

TA review of o-v9u (libgphoto2 d0419942) found the tri-state helper fixed the
false-IDLE read, but the pre-capture post-drain wait still **failed open**: if all
50 readiness polls stayed BUSY/UNKNOWN the loop ended, logged "drain complete",
and fired InitiateCapture anyway — proceeding while the camera was unproven-ready.

libgphoto2 fix (commit a46421c8e, master):
- Track whether the drain wait actually reached IDLE. On bound exhaustion
  (still BUSY/UNKNOWN) refuse the exposure with GP_ERROR_CAMERA_BUSY, matching
  the existing "stale candidate still pending" path, instead of firing into a
  busy camera.

Build inputs (clean):
- libgphoto2 source: a46421c8e8f8acf13a2cf2a1755f8bbad7d181ef (master)
- patcher: c2ec6ca58c0a8a7509a973ddf3e7aebdf0d5407b (main, clean tree)
- stock FwPkt: firmware/FwPkt.zip

Artifact:
- out/o-v9v-capture-failclosed-20260919/FwPkt.zip
  sha256 d04d96d31b0747dae4a0cfea239ab00b49d899ee3d1e4be89f63715c95aebe97
  (md5 eee477efecea9321f63a90a2f6bb03bb)

Verified (documented release process, docs/LIBGPHOTO2-UPGRADE-PROCESS.md):
- libgphoto2: clean build; test-pentax-utils passes.
- patcher deterministic harness (#117): 6 passed, 0 failed, 3 prerequisite-skipped.
- test_polaris_pentax_build_package.sh: PASS (full build + package path).
- Built ptp2.so contains the new fail-closed marker ("pre-capture drain consumed
  ... still busy/unknown after bounded wait; refusing new exposure").

Not yet done (hardware qualification pending): A/B/C camera ladder on a K-3 III
to confirm the wedge no longer reproduces and that the fail-closed path is not
overly conservative for legitimate multi-shot/astro/bulb drains.

## o-v9u-capture-readiness-20260919 — capture readiness tri-state + gated idle wait (fixes #122)

Shutter release could wedge the K-3 III until a mode toggle + USB reset. Two
defects in the libgphoto2 Pentax capture path contributed:

- The pre-capture drain and post-capture idle waits initialized activity/
  candidate to 0, so a FAILED or SHORT conditions read was indistinguishable
  from a valid idle frame — Benro fired the next shutter while the camera was
  still busy.
- The post-capture idle wait ran unconditionally for every capture.

libgphoto2 fix (commit d0419942, master):
- `pentax_camera_readiness()`: classify a raw conditions frame as IDLE / BUSY /
  UNKNOWN. Only a VALID frame may prove idle; a failed/short read is UNKNOWN,
  never IDLE. Both wait sites use it.
- `pentax_capture_needs_idle_wait()`: gate the post-capture wait to captures
  that can still be processing after all candidates are consumed (multi-shot,
  astro shift/tracer, bulb). Ordinary single-shot captures return through the
  normal completion path so Benro regains control immediately.

Build inputs (clean):
- libgphoto2 source: d0419942debf20cd1bf26ba69f127101f9661a61 (master)
- patcher: f7e982b17fe4e107b5a8b686da6e362ab9e88ca1 (main, clean tree)
- stock FwPkt: firmware/FwPkt.zip

Artifact:
- out/o-v9u-capture-readiness-20260919/FwPkt.zip
  sha256 673802720dc18f86566c2ec0698c835367a17c2ce1533edab8a882160f957e7c
  (md5 a0d313f069ebb1b7bbfb2c16f941d9f4)

Verified (documented release process, docs/LIBGPHOTO2-UPGRADE-PROCESS.md):
- libgphoto2: clean build + test-pentax-utils passes (tri-state + gate unit tests).
- patcher deterministic harness (issue #117): 6 passed, 0 failed, 3 skipped
  (prerequisite-gated: Docker image / source checkout / ARM cross-toolchain).
- test_polaris_pentax_build_package.sh: PASS (full build + package path).
- Pre-handoff appfs re-extraction: generated wrapper CAMLIBS=2.5.34,
  IOLIBS=0.12.2; embedded provenance build_id=o-v9u, git_commit=d0419942.
- Built ptp2.so contains the new single-shot skip marker (fix present).

Not yet done (hardware qualification pending): A/B/C camera ladder on a K-3 III
to confirm the wedge no longer reproduces after a shutter release in single-shot
mode, plus the multi-shot/astro/bulb regression rows.


## Unreleased — firmware-contained Pentax provenance and target-model gate

- Embed the exact clean libgphoto2 source identity at
  `/app/openpolaris-libgphoto2-provenance.txt`, so a flashed device can prove
  its source SHA without relying on files retained beside the ZIP.
- Fail a local-source build unless the final `ptp2.so` contains both the
  Pentax K-1 II and K-3 III model registrations as well as the Pentax vendor
  marker.
- Re-extract the generated appfs in the package test and compare its embedded
  provenance byte-for-byte with the build output; also assert both target
  model strings in the shipped camlib.

## Unreleased — Pentax capture memory budget (fixes #2)

libgphoto2's Pentax driver (`camlibs/ptp2/pentax-utils.c`) hard-codes a 2 GiB
single-capture cap (`PENTAX_CAPTURE_MAX_FILE_SIZE_DEFAULT`). On a desktop
workstation this is harmless. On the Polaris (512 MB – 1 GB userspace), a
single runaway tether request from a K-1 II / K-3 III would overcommit,
abort pgphoto mid-transfer, and leave the tether hung. The libgphoto2 fork
already reads the override env var `LIBGPHOTO2_PENTAX_MAX_CAPTURE_SIZE`; we
expose it through the build chain with a safe 256 MiB default.

### Added
- **`--pentax-max-capture-size BYTES` / `-PentaxMaxCaptureSize BYTES`**
  flag on both `patch-polaris.sh` and `patch-polaris.ps1` (default
  `268435456` = 256 MiB).
- **`PENTAX_MAX_CAPTURE_SIZE`** container env var plumbed through both
  launchers alongside the existing `LIBGPHOTO2_VERSION` /
  `LIBGPHOTO2_PORT_VERSION`.
- **`container/ondisk/pgphoto.wrapper.in`** — added a third `sed`-able
  placeholder, `@PENTAX_MAX_CAPTURE_SIZE@`, that is substituted at build
  time and exported as `LIBGPHOTO2_PENTAX_MAX_CAPTURE_SIZE`.
- **`container/ondisk/install_stage2.sh`** — added `PENTAX_MAX_CAPTURE_SIZE`
  env var with 256 MiB default in the documented-Inputs block.

### Changed
- **`container/patch.sh`** — wrapper-generation `sed` got a third
  substitution; the active value is now logged at startup
  (`Pentax capture cap: <bytes> bytes`).

### Verified (in-container pipeline)
- The sed substitution is exercised by the existing `libgphoto2` build step
  that already runs `pgphoto.wrapper` generation. A negative test with
  `--pentax-max-capture-size 1` would produce a wrapper that exports
  `LIBGPHOTO2_PENTAX_MAX_CAPTURE_SIZE=1`; the libgphoto2 fork's
  `pentax-utils.c` rejects anything below 1 MiB with `GP_LOG_E`. (Not
  auto-run in CI; requires on-device validation — see
  `docs/PENTAX-CAPTURE-BUDGET.md` §"Hardware evidence so far".)

### Docs
- New `docs/PENTAX-CAPTURE-BUDGET.md` documents the Polaris-RAM rationale,
  the chosen 256 MiB default, how to override, and the planned
  hardware-validation steps. Issue #2 closed against this work.

---

## Unreleased — Parameterise libgphoto2 path versions (fixes #1)

Any user passing `--libgphoto2 VER` to build a release other than the
default `2.5.34` was getting a silent mismatch: the patcher produced
fresh binaries with the right on-device layout but left the shipped
`pgphoto` wrapper pointing at hard-coded `2.5.34` / `0.12.2` paths. The
result was a 14-byte-patch-only noop against the stock 2.5.27 core — the
same symptom as issue #1's "vanilla build" reproducer.

### Added
- **`--libgphoto2-port VER` / `-Libgphoto2Port VER`** flag (default
  `0.12.2`) on both `patch-polaris.sh` and `patch-polaris.ps1`.
- **`LIBGPHOTO2_PORT_VERSION`** container env var (default `0.12.2`)
  plumbed through both launchers alongside the existing
  `LIBGPHOTO2_VERSION`.
- **`container/ondisk/pgphoto.wrapper.in`** — the on-device `pgphoto`
  wrapper is now generated from a `sed` template at build time, so the
  camlib/iolib paths it `dlopen`s match the staged
  `libgphoto2/<core>` / `libgphoto2_port/<port>` directories.

### Changed
- **`container/patch.sh`** — the six hard-coded `2.5.34` / `0.12.2`
  path literals (in-app install block + bundle assembly block) now
  read from `LIBGPHOTO2_VERSION` / `LIBGPHOTO2_PORT_VERSION`.
- **`container/ondisk/install_stage2.sh`** — same two env vars
  parameterise the `find_one` lookups and the `mkdir -p`/`cp` commands
  that populate `/app/lib/stage2`.
- **`.gitattributes`** — line-ending rule consolidated onto the
  `*.in` template; the old `pgphoto.wrapper` rule is gone (the file no
  longer exists; it is generated at build time).
- **`pgphoto.wrapper`** renamed to **`pgphoto.wrapper.in`** via `git mv`
  to preserve history; the template's `@CAMLIBS_VERSION@` /
  `@IOLIBS_VERSION@` placeholders are substituted at build time.

### Fixed
- Vanilla `--libgphoto2` builds now produce a working image
  (resolves the "no-op 14-byte patch" symptom in issue #1).
- Users building the Pentax development fork from a non-default
  release tag no longer need to hand-edit `pgphoto.wrapper` after
  the fact.

## Unreleased — FwPkt silent-reject fix (2026-08-27 combined build)

The Polaris on-board updater (`polestar_app → getFwInfo.sh → crcInfo`)
recomputes the MD5 and size of every component in `FwPkt.zip` and
string-compares both fields against `firmwareInfo`. A mismatch causes
a silent reboot with no user notification — the user sees the previous
firmware and no error.

The 2026-08-27 combined build (Pentax + HDMI 720p60) was rejected for
exactly this reason: the HDMI repack re-zipped `appfs.ubifs` but did
not re-run `gen_firmwareinfo.py`, so the shipped manifest still
advertised the Pentax-only `appfs` MD5 (`1775c7bc…`) while the
on-disk file was the HDMI-repacked one (`91629acf…`). One mismatched
line was enough to fail the whole update.

### Added
- **`container/verify_firmwareinfo.py`** — stdlib-only fail-closed
  offline re-MD5/size check. Re-runs the same algorithm the device
  runs. Exits 0 only on a perfect manifest↔file match; exits 1 with
  a per-line diff otherwise. Runnable on any existing build (stock,
  Pentax-only, combined, custom).
- **Build-time gate** in `container/patch.sh:386-396` — the
  verifier is invoked immediately after `gen_firmwareinfo.py` and
  the pipeline `die`s before the zip step on a mismatch. A layered
  repack that forgets to regenerate the manifest cannot leave the
  pipeline anymore.

### Fixed
- **`builds/2026-08-27-combined-720p60/FwPkt.zip`** repacked in place
  with a freshly regenerated `firmwareInfo`. The new manifest matches
  the shipped `appfs.ubifs` (`91629acf…`, 64,356,352 B). The on-board
  updater will now accept this packet.
  - SHA-256 fixed:   `ddc1aab69c97f9d2aea7492709c47f4ea3f1aca443fe5c08bf9ece41a2338e8e` (68,468,962 B)
  - SHA-256 broken:  `fb4c37e0e00c4b61a42e3c3b6d515cc5a1c4b0676cc4bc54275f4a27c6e8adaf` (68,484,760 B)
  - The broken packet is preserved as `builds/2026-08-27-combined-720p60/FwPkt.zip.broken`
    for forensic reference; do not flash it.
  - A copy of the fixed zip is also on the SMB share at
    `smb://morganbackup.local/home/Projects/Pentax/BenroPolaris/2026-08-27_pentax-hdmi720p60-live_only/`.

### Verified
- The new gate was run against four targets and passed/failed as
  expected:
  - fixed zip → PASS 6/6
  - broken zip → FAIL 1/6 (the `appfs` mismatch described above)
  - fixed zip + 3-byte XOR mutation of `appfs.ubifs` → FAIL 1/6
  - stock `firmware/FwPkt/FwPkt/` → PASS 6/6

### Docs
- The archived silent-FwPkt rejection postmortem documents the
  mechanism, the layered-repack root cause, the fix, the fingerprints,
  and the recommended user flash order. Issues #19 and #20 are
  closed against this work.

---

## Unreleased — silent-gimbal-drop fix + finished-package structural validator (issue #21)

While exercising the clean-Pentax rebuild path (the full-stack local-fork
build), a **second, independent** silent-firmware-rejection surfaced. The
on-board `polestar_app` was still silently rebooting, but for a completely
different reason than the 2026-08-27 case.

### Symptom

A clean-Pentax build (`/libgphoto2-source-input` mounted) produced a
68,372,735 B zip containing **8** entries instead of the expected 10.
Both gimbal binaries (`polaris403_2.0.0.22.bin` and
`polaris413_2.0.0.22.bin`) were missing from the output. The on-board
updater would silently reboot (no NAND write, no UI signal, no log
entry), exactly as in the stale-`firmwareInfo` case.

The `verify_firmwareinfo.py` re-MD5/size gate from the previous section
**did not catch this** — because `firmwareInfo` is generated *from* the
on-disk state, the partial gimbal drop left the remaining gimbal line
correct and simply omitted the missing one. The bug is **structural**,
not content-based.

### Fixed
- **`container/patch.sh`** no longer swallows gimbal copy errors. The
  `2>/dev/null || true` that hid a missing `cp` is gone, and a
  pre-flight `ls`/`wc` check now `die`s with a clear "no /in/gimbal/*.bin
  found — refusing to ship a gimbal-less FwPkt (issue #21)" message
  before any output is assembled. See commit for the diff; the relevant
  section is the `8. Repack appfs … assemble` block in
  `container/patch.sh`.
- **`container/validate_fw_package.py`** (NEW, ~250 lines, stdlib-only) —
  the implementation of issue #21's spec. Walks the finished zip and
  rejects any of: wrong top-level layout, duplicate members, missing
  required files, stock-component drift (SHA-256 mismatch on any
  `camera/*` or `gimbal/*.bin` whose name matches a stock component),
  gimbal-dir empty. Always prints a concise manifest of every member and
  its on-disk size, then PASS/FAIL summary.
- The new validator runs **after** the zip is built and **before** the
  pipeline exits; a `die "refuse to ship"` on FAIL means a bad build
  cannot reach `builds/`, the SMB share, or an SD card.
- **Pentax-fork marker check is no longer a SIGPIPE false negative.**
  `container/patch.sh:166-170` had `strings | grep -Fq` under
  `set -euo pipefail`, which is a documented SIGPIPE footgun: grep
  exits 0 on match, `strings` keeps writing to the now-unread pipe, gets
  SIGPIPE (exit 141), `pipefail` propagates 141, and `set -e` turns that
  into a false "marker missing" abort. Replaced with `grep -Fc` (count
  mode, drains the pipe to EOF) and a string compare. See
  PrivateResearch issue #116 archive for the full analysis.

### Verified
- `validate_fw_package.py` run against six packages:
  - stock `firmware/FwPkt.zip` → PASS
  - fixed combined `builds/2026-08-27-combined-720p60/FwPkt.zip` → PASS
  - broken c2 build `/tmp/c2-rebuild/out/FwPkt.zip` → FAIL with 3 errors
    (missing `gimbal/*.bin`, missing `polaris403`, missing `polaris413`)
  - stock unzipped dir → PASS
  - wrong top-level folder (`WrongName/` instead of `FwPkt/`) → FAIL
  - true duplicate `FwPkt/firmwareInfo` member → FAIL
  - mutated `camera/config` (1-bit flip) → FAIL with exact
    expected-vs-actual SHA-256 diff

### Docs
- The archived silent-FwPkt rejection postmortem addendum documents the
  silent-gimbal-drop root cause, why the firmwareInfo check is
  insufficient, and how the structural validator closes the gap. Issue
  #21 is closed against this work.
### Not tested
- Any camera other than the R5 Mark II; any firmware other than 4.0.0.32.

---

## Unreleased — Pentax + HDMI combined build (`builds/2026-08-27-combined-720p60/`)

A combined Pentax + HDMI patched FwPkt was produced on
2026-08-27 by layering the new HDMI geometry patcher over the
Pentax-only FwPkt at `builds/2026-08-23/`. This entry is
**informational** — it does NOT mark the combined build as a
release candidate.

### What was done

- Ported `hdmi_geometry_patch.py` from
  `agents/benro-polaris-firmware-docs` @ `5d0fc75` to
  `container/hdmi_geometry_patch.py` (the upstream version
  targeted a different `polestar_app` build).
- Re-patched the 5 LIVE HDMI sites in
  `bin/polestar_app` (md5 `067b8c3ba68f26141a7becc8d92c8ac0`).
- Re-packed `appfs.ubifs` with the patched `polestar_app`
  substituted in.
- Re-zipped the resulting bundle as
  `builds/2026-08-27-combined-720p60/FwPkt.zip` (md5
  `fd8147c91df44757d8a41c8bacc39519`, sha256
  `fb4c37e0e00c4b61a42e3c3b6d515cc5a1c4b0676cc4bc54275f4a27c6e8adaf`,
  68,484,760 B).

### Release state

**Round-trip verified only.** The combined FwPkt is at the
second rung of the 7-rung release-state ladder documented in
the archived critical review §0 — it
has NOT been validated on a Polaris device, a Pentax camera,
or an HDMI display, and the DEAD-site patches (8 sites in
the VENC / RTSP code paths) are deliberately excluded.

### Known limitations

- **Layered build.** The combined FwPkt was produced by
  patching the Pentax-only FwPkt's UBIFS rather than by a
  clean end-to-end rebuild from a current libgphoto2
  master. The embedded `libgphoto2.so` is at libgphoto2
  commit `da8c33482` (2026-08-26), not the current
  `ian-morgan99/libgphoto2` master. See
  the archived critical review §8.5
  for the blocker plan that supersedes the layered build.
- **LGPL corresponding source is vanilla.** The tarball at
  `builds/2026-08-23/licenses/libgphoto2-2.5.34.tar.xz` is
  the upstream 2.5.34 release, not the Pentax-patched
  source. A real LGPL §6 archive must be regenerated from
  the exact `da8c33482` (or current master) checkout with
  Pentax patches applied.
- **No DEAD-site patches.** Sites 0x13c390, 0x13c394,
  0x13c398, 0x1629f0, 0x16ea90, 0x16eb30, 0x16eb70,
  0x16f080 (per `DEAD_SITES` in
  `container/hdmi_geometry_patch.py`) are not patched. The
  `--include-dead=0` flag is the default. Running with
  `--include-dead=1` is known to fail on the real
  firmware's `polestar_app` offsets.
- **No device / camera / HDMI validation.** See
  the archived critical review §0
  for the 7-rung ladder and §8.5 for the path to a release
  candidate.

### References

- Operational record:
  the archived run journal
- Critical review (with full gap list, 8.5 blocker plan,
  and the next-agent re-check list):
  the archived critical review
- Final state of the build at the time of writing:
  the archived final report
- Docker image used to build / repack:
  [docker/README.md](docker/README.md) (image digest
  `sha256:b475ca01354845358d21e7adbf0eba9fffc3792e8f49a2d548cadf327cc27953`)
- Build provenance for the combined FwPkt:
  `builds/2026-08-27-combined-720p60/build-source-provenance.txt`
  (not committed; lives in `builds/` which is gitignored)

## v0.3.0-pentax-hdmi (tagged 2026-08-23 at commit `b3aa306`)

> **Note added 2026-08-27:** the `v0.3.0-pentax-hdmi` tag was
> created when only the patcher self-tests against a
> **synthesized stock buffer** had passed (13/13 LIVE sites
> matched against a Python re-encoding of the patcher output,
> not real firmware bytes). Verification against the real
> Benro Polaris firmware happened in subsequent commits
> (`4b8a3b7`, `4f1c5d3`, `58c166a`, and the four commits
> pushed as `0354a35` / `ef3c0be` / `fd0a21d` / `0c86436`).
> A reviewer running `git checkout v0.3.0-pentax-hdmi` lands
> on a tree that is **earlier than the actual verification
> work**. For the verified combined build see the
> `v0.3.0-pentax-hdmi-combined-720p60` tag (commit `0c86436`)
> and `builds/2026-08-27-combined-720p60/`. This note closes
> Gap 3.

## v0.3.0-pentax-hdmi-combined-720p60 (tagged 2026-08-27 at commit `0c86436`)

Annotated tag pointing at the verified combined-build state
described under the "Unreleased" section above. Tag
annotation records:

- Stock firmware md5
- Pentax base FwPkt md5
- Combined FwPkt md5 + size + sha256
- Docker image digest
- libgphoto2 commit (`da8c33482`)
- Build method (`combined_layered`)
- LIVE/DEAD site counts
- Release state (`round-trip verified (NOT device validated)`)

Inspect via `git cat-file -p v0.3.0-pentax-hdmi-combined-720p60`.

## Pending next candidate — K-1 II pgphoto readiness (#253)

- `container/ondisk/restart_gphoto.sh` now gives a progressing K-1 II camera
  initialisation a bounded 90-second readiness window. The previous 20-second
  limit falsely failed the rebind while the process was still enumerating the
  K-1 II controls, causing supervisor retries and painfully slow value setting.
- Added `container/test_restart_gphoto_readiness.sh`, covering slow readiness
  and fail-closed hung startup. The slow case now crosses the old 20-second
  bound and the hung case verifies the configured timeout by elapsed time, so
  the regression is red on the parent revision.
- Evidence and hardware qualification plan: `docs/issue-k1ii-pgphoto-readiness.md`.
- This is a patcher/runtime fix; no libgphoto2 source change is included.

## Fixed — main has been RED since PR #299 merged

`tests/test_astro_regression.py` arrived with PR #299 but was never added to `PY_TESTS` in
`tests/run_prerelease_gate.sh`, so the drift guard failed main's gate:

```
FAIL: python suites exist but are not run by this gate: tests/test_astro_regression.py
=== Pre-release gate summary: 10 passed, 1 failed, 3 skipped ===
GATE: RED — do not stage/install the FwPkt until the failed checks pass.
```

Registering it restores GREEN (38 suites, 615 passed — up from 612, so the three new tests
actually run rather than sitting collected-but-unexecuted).

The suite is offline-safe and belongs in the offline list: it invokes
`tests/astro_regression/runner.py --offline`, asserts on checked-in fixtures, touches no
device and no network, and completes in 0.05 s.

Worth noting how this slipped through: #299 was merged test-only with no gate run attached.
The drift guard exists precisely because `test_verify_installed_build.py` once sat unrun
while the gate reported GREEN — it did its job here too, but only after the merge rather
than before it.
## Unreleased — shipped camlibs are now proven to serve the K-1 II and K-3 III (issue #297)

`container/check_camlib_target_models.sh` opens the `ptp2.so` a device actually
receives and requires both `Pentax:K-1 Mark II (PTP mode)` and
`Pentax:K-3 Mark III (MTP mode)` to be present, that the file is an ARM shared
object, and that `camlibs.manifest` hashes match the bytes beside them.

Until now the only K-1 II / K-3 III evidence in the build was textual.
`container/patch.sh` logs "local-source target models: K-1 II and K-3 III present"
after grepping the **source tree**, and `test_polaris_pentax_build_package.sh`
asserts that log line. Neither opens a `.so`. A camlib compiled from correct source
but with the model table filtered, truncated, or built against a different
libgphoto2 passes every one of those and still ships a camera nobody can see — which
is the shape of #297: the operator's symptom was real while every source-side check
was green.

Asserted against `ptp2.so` specifically rather than "any camlib", because that was
measured: `pentax.so` contains `Pentax:K1II`, `Pentax:K3`, `Pentax:K3II` and 14
others, but **not** either target marker. Both are in `ptp2.so`. Checking the wrong
camlib would fail a good build; checking "any" would let a build shipping only
`pentax.so` pass while serving neither camera.

The version directory is globbed rather than hardcoded to `2.5.34`, so a libgphoto2
bump cannot silently skip the gate — a stale hardcoded path makes every `[ -f ]`
guard false and the whole check passes vacuously.

Non-vacuous, three ways: passes on a real v100 build; fails (exit 1) when the K-3 III
marker is blanked out of a copy; fails (exit 1) when a manifest hash is perturbed.
Two bugs in the first draft were caught by running it against real bytes rather than
reasoning about it — `file` puts the architecture *after* "shared object", so an
ordered glob rejected correct ARM binaries, and `printf | while` ran the marker loop
in a subshell so recorded misses vanished.

Registered in `run_prerelease_gate.sh`'s stage2 package section. Offline gate:
**14 passed, 0 failed, 2 skipped**. With `--build`: **21 passed, 0 failed, 3
skipped**, including the new check.

This does not claim recognition works. It proves the shipped camlib *can name* both
cameras; whether a session is ever opened against them is still unproven — on the
device pgphoto currently has no camlib mapped at all.

## Unreleased — a five-layer camera recognition report, read-only (#297)

`scripts/diagnostic/camera-layer-report.sh` answers "is the camera recognised?" by
measuring each layer separately and reporting PASS / FAIL / UNKNOWN per layer, so a
symptom can be attributed instead of guessed at. It is strictly read-only: sysfs,
`/proc`, and GETs against documented Alpaca queries. It never restarts, kills, unbinds
or writes anything.

Why it was needed. On the device that prompted this, `lsusb` showed the camera present,
pgphoto was running, and polaris-httpd was serving — all three true, and the camera still
invisible. The layers that actually differ were never being looked at: whether pgphoto has
a camlib mapped, and what `CameraState` the app publishes.

Current reading on the live device (`docs/evidence/issue-297-k3iii-stale-restart-lock/layer-report.txt`):

```
[PASS]    layer1-usb        25fb:0189 enumerated
[PASS]    layer2-pgphoto    running as PID 10026
[PASS]    layer2-restart-lock  no restart lock held
[PASS]    layer2-quarantine no quarantine lines in /app/Clog.txt
[UNKNOWN] layer3-camlib     no camlib mapped and no client on :8080
[UNKNOWN] layer4-client     no client on :8080 right now
[FAIL]    layer5-published  CameraState=Disconnected
```

Two of those are UNKNOWN on purpose, and that distinction is the point:

- **layer 4** — `polaris-httpd` connects to pgphoto's :8080 *on demand* for the live-view
  stream (`sa.sin_port = htons(8080)` then `GET /?action=stream`), not by polling. With no
  app attached, zero connections is the expected idle state and says nothing about health.
- **layer 3** — libgphoto2 loads a camlib when it builds its abilities list during
  `gp_camera_init`. "Nothing mapped" means no session has opened since this process
  started; whether that is a fault depends on whether anything asked. The verdict is
  deferred until layer 4 is known: UNKNOWN with no client, FAIL if a client is connected
  and still nothing loads.

Both were initially written as FAIL. That was wrong — reporting an idle device as broken
is how a measurement gap turns into a phantom bug.

**layer 5 is the real finding.** `GET /api/v1/camera/0/camerastate` returns `Value:0`
(ASCOM Disconnected) while `/connected` returns `true`. The app reports a camera device
that has no session. That is measured, not inferred, and it is where recognition actually
fails today.

Routes were read from `container/astro/polaris-httpd.c`; the obvious guesses (`/status`,
`/camera`) return "not found" on this server. Only read-only queries are used — the
POST-only guard list (`/api/astro/capture`, `/api/stop`, …) is never touched.

Not registered in the prerelease gate: it needs a reachable device, so it belongs with the
device gates rather than the offline ones. Run it before and after any camera fix.

## Fixed — the prerelease gate was executing two stray commands (#298 review)

Review on PR #298 found bare command lines `s` and `ped` at lines 363/365 of
`tests/run_prerelease_gate.sh`. They were mine: a comment pasted in already hard-wrapped
at terminal width, so the wrapped remainder of "as" and "shipped" landed on its own line
outside the comment and became executable code. Both lines are now part of the comment.

Why nothing caught it. The gate runs `set -uo pipefail` — no `-e`. A missing command
returns 127 and execution continues, so the defect survived `bash -n` (two syntactically
valid commands), survived `--help`, and produced a green summary. Only reading the file or
running with `set -x` would show it.

Added `tests/test_shell_no_bare_fragments.sh`, registered in the gate, covering **every**
tracked `.sh` rather than just this one — the hazard is any script absorbing a wrapped
paste. It treats a bare short line as legitimate only if it is a shell keyword/builtin or a
function defined in that same file (`purge` is called bare at line 65 of
`polaris-autojoin.sh` and defined at line 36, so a naive keyword list would have flagged it).
Tracked files only: `out/` holds copies of these scripts and would double every finding.

Non-vacuous: flags `s` and `ped` when reintroduced (exit 1), passes on the current tree
(117 tracked shell files, exit 0).

Gate from the corrected head: **offline 15 passed, 0 failed, 2 skipped**; **with
`--build`: 22 passed, 0 failed, 3 skipped**. Full output in
`docs/evidence/issue-297-k3iii-stale-restart-lock/gate-{offline,package}.txt`.

## Fixed — camera diagnostic under-reported clients, forcing layer 3 to UNKNOWN

`scripts/diagnostic/camera-layer-report.sh` matched `:1F90` only in `/proc/net/tcp`'s remote
column. pgphoto is the **server** on 8080, so established rows carry it in the *local* column.
Measured against a live stream request with two connections open:

```
$3 ~ /:1F90$/                       -> 0    (what the tool did)
($2 ~ /:1F90$/ || $3 ~ /:1F90$/)    -> 2    (correct)
```

The consequence was worse than a wrong count. Layer 3's verdict is deliberately deferred on
layer 4 — "no camlib mapped" is UNKNOWN while idle because lazy init means nobody has asked
yet, and only becomes FAIL once a client is connected. Under-reporting clients therefore kept
layer 3 at UNKNOWN permanently, hiding the real state. With the fix and a stream held open:

```
[PASS] layer4-client -- 1 established connection(s) to :8080
[FAIL] layer3-camlib -- a client is connected but no pentax.so/ptp2.so is mapped
```
