# astro-v106 install attempt — 2026-11-12

**Result: NOT INSTALLED. Device is on `6.0.0.54.105`, unharmed, and currently
unreachable.** No flash was performed in any attempt. Nothing was staged that the
on-boot watcher could consume.

## What was verified before touching anything

| check | value |
|---|---|
| `FwPkt.zip` SHA-256 | `273c697a3465b13bd0ba780f184ae7632c2d5b738688ccce2a92d0dfabc3415e` — matches the registry row and `install-manifest.json` |
| zip size | 68,407,830 bytes |
| build dir | `/home/ian/polaris-v101/out/astro-v106-autonomous-harness-20261111` |
| `build_id` | `astro-v106-autonomous-harness-20261111` |
| driver pin | `530c879fe7959ac4ccf4f4620a3032d49e45c293` |
| patcher commit | `73e3066123b7640205f5cbe72207757ae5429cad` |
| extracted tree | 89,816,752 bytes, matching the sum of `firmwareInfo` size fields |
| camera state | idle — no reply to `286`, no capture in flight |

The colliding unpublished build at `/home/ian/astro-v106-build/out/astro-v106-appliance-fixes-20261111`
(sha256 `b14559986e6182a6…`, driver `96cb7b8b4`) was **not** used. Identified by
digest, not display version, per the registry note.

## SD card state before starting

The previous agent's aborted transfer left two remnants. Both were staging
artifacts, not user data — every capture directory (`HDR`, `Lapse`, `normal`,
`panorama`, `focusStack`, `starskyStack`, `sun`) was empty and was left alone:

- `/app/sd/FwPkt.zip.part` (4,992 KB) — the **deprecated zip-only path** (issue #58).
  The on-boot watcher consumes the extracted tree, never the zip, so this could
  never have installed anything.
- `/app/sd/test-input/` (152 KB) — one prior upload test JPEG.

Removed both. Card clean at 118,894 KB free.

## Attempt 1 — staging failed at ~2 MB

```
--- [2/6] Staging FwPkt/ tree to /app/sd/FwPkt/ ---
Streaming 86M to device...
Timeout, server 192.168.0.1 not responding.
tar: -: Wrote only 2048 of 10240 bytes
tar: Error is not recoverable: exiting now
```

`set -euo pipefail` stopped the run before phase 4, so **no reboot was triggered**
(`grep -c '\[4/6\] Triggering' install.log` = 0). Device stayed on `.105` with
continuous uptime. A truncated `/app/sd/FwPkt/camera/rootfs.ubifs` (2 MB of
21 MB) was left behind; removed by hand. It had no `firmwareInfo`, so the watcher
could not have consumed it even if the device had rebooted.

## Diagnosis

The card is **not** at fault:

```
dd 40 MB -> /app/sd   rc=0  2.2 MB/s  drop_events=0
dd 86 MB -> /app/sd   rc=0  2.4 MB/s  drop_events=0
```

The failure is in the **host → device** direction, and it is not SSH-specific:

| test | result |
|---|---|
| upload 1 MB over ssh | timed out at 74 s |
| upload 2 MB, ciphers `aes128-ctr` / `aes128-gcm` / `-ctr+hmac-sha2-256` | all stalled |
| upload 64 KB over ssh | stalled |
| upload 256 KB raw TCP via `nc` (no SSH at all) | received only **41,992 bytes** |
| download 2 MB device → host | **OK**, 13.5 s (~155 KB/s) |

Device-side counters: `wlan0: rxerr=27775 txerr=0`. RX errors only, TX clean —
the device cannot reliably receive. Download works, upload collapses at ~40 KB.

## Reboot, and the current blocker

Rebooted deliberately to clear driver state and the stale sessions left by killed
transfers (7 `sshd: root` + 3 dropbear). Safe at the time: nothing staged, `.105`
healthy. Confirmed real reboot — uptime reset to 53 s, `rxerr` reset 27,775 → 73,
still `.105`, card clean.

A 4 MB upload test after the reboot **still stalled**, so RX error accumulation
was not the cause. During that test SSH began returning `Connection refused`, and
the device then disappeared entirely:

- ports 22, 23, 8090, 9090 all refuse
- no ARP entry for `192.168.0.1`
- this host has **no interface or route on 192.168.0.0/24** — its only LAN address
  is `192.168.68.89` on `enp11s0` — so earlier "refused" replies came via the
  sandbox proxy and are not reliable liveness signals
- sweep of the reachable `192.168.68.0/22` on ports 22 and 8090 found no Polaris

**The device is almost certainly up and has simply rejoined a network this host
cannot reach.** Its WiFi restarted after reboot (`wifi-watch.sh` /
`setup-wifi.sh` run from the astro boot hook). This needs physical or same-subnet
access to resolve.

## Fixes landed during this attempt

1. `600b9ed` — capacity gate in `release-fwpkt.sh` now **fails closed**. It printed
   `WARN: low space` and continued; with vfat mounted `errors=continue` an over-full
   card reports success while truncating, so a warning let bad bytes reach the
   watcher. Also added registry rows for `.104`, `.105`, `.106` (the table stopped
   at `.97`, making checklist item 1 unsatisfiable for all three) and documented
   that nothing enforces that rule, plus the `.106` version collision.
2. `53e624d` — SSH keepalive tolerance. `ServerAliveInterval=10` with the default
   `ServerAliveCountMax=3` tears down after 30 s of silence, but `tar xzf` + `sync`
   is silent for ~40 s at 2.1 MB/s, so it killed a healthy transfer. Both installers
   now use `ServerAliveCountMax=60`. Added a post-stage byte-count check that
   removes the tree and exits before any reboot if it is short.

Both were necessary but neither addresses the actual blocker, which is inbound
throughput on the device's WiFi.

## To resume

1. Reach the device from the same subnet (or restore a route to 192.168.0.0/24) and
   note its address.
2. Confirm `FwVer` is still `.105` and `/app/sd/FwPkt` is absent.
3. Re-run:
   `./scripts/release/release-fwpkt.sh /home/ian/polaris-v101/out/astro-v106-autonomous-harness-20261111 --host <ip>`
4. If uploads still collapse at ~40 KB, the WiFi link is the limit and staging must
   be done another way — the card written directly in a reader, or a wired/stronger
   link. Do not retry over the same link; a truncated tree is caught now, but it
   cannot succeed.
