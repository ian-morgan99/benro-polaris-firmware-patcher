# Local Wi-Fi join failure — root cause, fix applied, and a second blocker

Device: Benro Polaris Astro, `sw:6.0.0.54.97`, hw `1.1.1.2`. Date: 2026-11-07.

## Root cause of the "wpa error"

The device ships **no station-mode tooling at all**. Probed directly:

```
wpa_supplicant=MISSING   wpa_cli=MISSING   iw=MISSING   iwconfig=MISSING
udhcpc=/sbin/udhcpc      dhcpcd=MISSING
find / -name "wpa*" -type f  ->  (nothing)
```

`setup-wifi.sh` begins with `[ -x "$WDIR/wpa_passphrase" ] || exit 2`, so it aborted on
its first line — `/app/sd/polaris-wifi/` did not exist. The failure was never a config or
password problem; the binaries were simply absent.

`container/astro/build_wifi.sh` exists and documents this exact gap ("ships NO
station-mode tooling at all… no wpa_supplicant and no iw"), but **nothing invokes it**
(`grep -rn build_wifi` matches only its own usage comment) and it had never been run —
no kit existed anywhere on the build machine.

**And the astro bundle ships zero files to `polaris-wifi/`** (`unzip -l … | grep -c
polaris-wifi` → 0), while boot looks for the kit there:

```sh
# polaris-astro-boot.sh:116
if [ -f /app/sd/polaris-wifi/autojoin ] && [ -x /app/sd/polaris-wifi/polaris-autojoin.sh ]; then
```

So no release has ever contained the kit. That is why the gap went unnoticed: the feature
was unshippable by construction, and the failure surfaced as a generic "wpa error" rather
than "binary missing".

## Fix applied — built and deployed to the SD card only

Built in the `polaris-patcher-pentax` container (Debian 9 stretch, **glibc 2.24**), which
matches the device exactly:

```
device: /lib/libc.so.6 -> libc-2.24.so   "GNU C Library stable release version 2.24"
```

No host `sudo` was needed — the image's entrypoint was overridden and `flex` installed
inside the container (`bison` was already present).

Build result (exit 0):

| Binary | Size | ABI | Max glibc symbol |
|---|---|---|---|
| `wpa_supplicant` | 3,077,404 | ARM EABI5 softfp | `GLIBC_2.7` |
| `wpa_cli` | 294,512 | ARM EABI5 softfp | `GLIBC_2.4` |
| `wpa_passphrase` | 195,768 | ARM EABI5 softfp | `GLIBC_2.4` |
| `iw` | 384,440 | ARM EABI5 softfp | `GLIBC_2.17` |

libnl is statically linked; dynamic needs are only `libc/libm/libpthread/librt`, all
present on the device. Every requirement is well under the device's 2.24.

Deployed to `/app/sd/polaris-wifi/` (the SD card, `vfat` on `/dev/mmcblk0p1`). Transferred
via ssh pipe — the device runs dropbear with no `scp`.

**Integrity verified by hash**, local vs device, all four identical:

```
0587e5b9dfe707a92  iw
1fe8e21788425407a  wpa_cli
d2e75e775b66d5591  wpa_passphrase
d31520f4373c17599  wpa_supplicant
```

**Executes on the device:**

```
$ ./wpa_supplicant --version   ->  wpa_supplicant v2.10
$ printf 'hunter2hunter2' | ./wpa_passphrase TestNet
        ssid="TestNet"
        psk=45c2…                      # real PSK derived
$ ./iw dev                           ->  phy#0 / Interface wlan0 / type AP
```

`setup-wifi.sh`'s precondition is now satisfied.

## Nothing was written to the device, and the AP was not touched

- `/app` is persistent UBIFS; `/app/sd` is the SD card. Everything landed on the card, so
  it disappears when the card is removed — matching the intended safety model.
- `hostapd.conf.autojoin-bak` does **not** exist, which proves the AP config was never
  modified.
- `wlan0` remained `type AP` at `192.168.0.1` throughout, including across a scan attempt
  and two create/delete cycles of a second interface.
- `dmesg` `tdata_psh_info` count was unchanged over a 4 s window (delta 0), so the testing
  did not degrade the driver.

## Second blocker found: scanning fails while the AP is up

Creating the station interface works — this is `polaris-autojoin.sh`'s first step and it
succeeds:

```
$ iw dev wlan0 interface add wlan1 type managed   ->  rc=0
  Interface wlan1        type managed
  Interface wlan0        type AP
```

But scanning on it fails, **three attempts out of three**:

```
$ iw dev wlan1 scan
command failed: Device or resource busy (-16)
```

`iw dev wlan0 scan` (on the AP interface itself) also returns nothing.

`dmesg` shows `dhd_tcpdata_info_get 1056: No more free tdata_psh_info!!` — issue **#171**,
which describes permanent exhaustion of that pool and says it begins "immediately after the
station associates".

**I am not attributing the EBUSY to #171 with confidence.** Two candidate causes remain,
and I cannot separate them without either tearing down the AP (which would drop this SSH
session) or rebooting:

1. The driver cannot scan on a second interface while an AP is active on the same radio.
2. The `tdata_psh_info` pool is already exhausted from earlier station activity in this
   boot, so any scan fails regardless of interface.

Note no station is currently associated, which argues against (2) — but #171 calls the
exhaustion permanent, so it may not clear without a reboot.

This matters because `polaris-autojoin.sh` **requires** a successful scan as step 1: it
finds the home network's channel before moving the AP there, and exits 4 with "could not
find $SSID in a scan" otherwise. So with the kit now present, autojoin will get further
than before but is likely to stop at the scan.

## Why the channel constraint makes this unavoidable

`polaris-apsta.sh` documents that `iw phy`'s advertised `#channels <= 2` is **false on this
hardware** — the CYW43455 has one radio, and associating a station on a different channel
than the AP "crashes attempting it and takes the whole device down — observed three times,
always at the moment of association". Hence autojoin must scan first to learn the home
network's channel, then move the AP to it. The scan is the load-bearing step, and it is
the one failing.

The AP is currently on `channel=36` (5 GHz), so a 2.4 GHz home network cannot be joined
without moving the AP first.

## Path mismatch still present

Boot checks `/app/sd/polaris-wifi/polaris-autojoin.sh`; the bundle installs it to
`/app/sd/polaris-astro/polaris-autojoin.sh`. Confirmed on the device:

```
/app/sd/polaris-wifi/polaris-autojoin.sh  ->  ABSENT
/app/sd/polaris-astro/polaris-autojoin.sh ->  present
```

So even with the kit in place, boot's autojoin gate never passes. Needs either the bundle
to install the wifi scripts into `polaris-wifi/`, or boot to look in `polaris-astro/`.

## Not done deliberately

- **No network was joined.** No credentials were entered and no association was attempted,
  because off-channel association is what bricks the radio per the notes above.
- **The AP was not moved or restarted.**
- **No reboot.** Whether a fresh boot clears the `tdata` pool and unblocks scanning is
  untested — that is the obvious next experiment, and it needs the card left in place.

## Files

| File | Contents |
|---|---|
| `build_wifi.sh` | The cross-build script as run (unchanged from `container/astro/`) |
| `build.log` | Full build output including ABI and glibc symbol checks |
