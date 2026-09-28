# o-v13d pubfix canary retry — staged automation (2026-09-27)

## Context
- Issue #145 (libgphoto2 + patcher): canonical Pentax capture lifecycle.
- o-v13d-pubfix (libgphoto2 75f9e4b1e) installed on Polaris: /app/FwVer = 6.0.0.54.28-o-v13d-pubfix, install gate PASS.
- Live two-shot canary FAILED environmentally: K-3 III USB link marginal (camera re-enumerates ~18s into each capture; #119 pattern). Not a pubfix regression.
- Polaris then entered deep sleep: AP polaris_d13e86 not visible, 6 BT wake pulses over ~15 min did not complete GATT connect (BLE radio sleeps with SoC — bare GATT connect cannot wake a hard-off SoC per .github/skills/polaris-debugging/SKILL.md).

## Physical action required (one-time)
Power the gimbal on (power button / power cycle) until at least the blue idle-wake LED.
Optional but ideal: also power-cycle the K-3 III for a clean USB link.

## Staged automation chain (all running, no further action needed after power-on)
1. /tmp/polaris-recover.sh  (PID 4123931, log /tmp/polaris-recover.log, ~6h budget)
   - every 2 min: BT wake pulse (bluetoothctl connect 48:E7:DA:D4:B5:72) + AP poll
   - on AP visible: nmcli join polaris_d13e86 -> wlp8s0
   - identity check via /tmp/pssh.sh (pty, empty root password — no key on this host):
     cat /app/FwVer; uptime  -> /tmp/polaris-identity.txt (retries until sshd up)
   - then 45 min of 9090 keepalive so the box does not re-sleep mid-work
2. /tmp/polaris-canary-run.sh  (PID 4131926, log docs/evidence/o-v13d-pubfix-canary-retry-20260927/run.log)
   - waits for /tmp/polaris-identity.txt containing FwVer
   - settles 180 s (known marginal-USB window after boot), 9090 keepalive in background
   - pre-state: canary-probe.py --probe + pssh device state (lsusb 25fb, uptime, FwVer, dmesg tail)
   - THE GATE: python3 scripts/canary-two-shot.py --expected-files 2  (pure 9090 wire protocol, no SSH)
   - post-state incl. dmesg tail for #119-pattern diagnosis -> post-device.txt
   - writes DONE marker
3. /tmp/polaris-install-run.sh  (PID 3195, log docs/evidence/o-v13d-pubfix-canary-retry-20260927/install-run.log)
   - waits for DONE + "TWO-SHOT PASS" in two-shot.log (aborts on DONE without PASS)
   - pushes /tmp/polaris-install-key.pub to /root/.ssh/authorized_keys via pssh
     (boot hook appends missing keys; rootfs persists across NAND reflash, so key survives reboot)
   - runs scripts/release/release-fwpkt.sh out/o-v13e-restored-fixes-20260927 --max-wait 900
     (stage FwPkt tree -> /app/sd/FwPkt/, verify MD5s on-device, reboot, wait for return, confirm FwVer)
   - post-reboot: rejoin AP if needed, final FwVer check -> post-install-fwver.txt, writes INSTALL-DONE

## o-v13e artifact (verified locally)
- out/o-v13e-restored-fixes-20260927/ : FwPkt tree + FwPkt.zip + build-source-provenance.txt
- build_id=6.0.0.54.29-o-v13e-restored-fixes, git_commit=564bdd070 (contains pubfix 75f9e4b1e + 7 more commits)

## Branch state (codex untouched)
- BenroPolarisPatcher main checkout: release/o-v13d-review-convergence-20260926 @ 576f4ad (clean except untracked evidence dir)
- Codex worktree: OpenPolaris/.worktrees/issue-90-capture on codex/issue-90-capture (+ uncommitted changes in OpenPolaris main checkout)
- libgphoto2 fork: convergence/pentax-restored-fixes-20260927 @ 564bdd070

## If the two-shot gate fails again
post-device.txt contains dmesg tail: look for usb reset / session init churn ~18s into capture = #119 marginal link (power-cycle K-3 III, re-run). If camera stays enumerated but capture still fails, that is a pubfix regression -> escalate to issue #145.
