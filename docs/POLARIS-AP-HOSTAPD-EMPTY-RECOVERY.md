# Polaris AP unreachable: hostapd rejects `/app/wifi/hostapd.conf`

**Verified:** hostapd is handed a config it cannot parse, so the AP never starts.
**Not verified:** that the file is literally zero-length, or which of the two
writers produced the bad file. See "Who writes this file" below.

## Symptom

`polaris_d13e86` never broadcasts. SSH, `:8090` and the Benro app are all
unreachable. Removing the SD card changes nothing.

## What is observed

Read from the boot logs the device writes to the card at
`/app/sd/system/log/Mlog_*.log`. Last good boot versus the first broken one:

```
boot 15  Configuration file: /app/wifi/hostapd.conf
         Using interface wlan0 with hwaddr 48:e7:da:d4:b5:73 and ssid "polaris_d13e86"
         wlan0: AP-ENABLED

boot 16  Configuration file: /app/wifi/hostapd.conf
         Interface name not specified in /app/wifi/hostapd.conf, nor by '-i' parameter
         : interface state UNINITIALIZED->DISABLED
         : AP-DISABLED
```

Every boot after 15 fails the same way (`Interface name not specified` appears
8, 4, 18, ... times per boot as the firmware retries). hostapd is being handed an
empty or truncated file, so it never brings up the AP.

`/app/wifi/hostapd.conf` lives on the device's **appfs**, not on the SD card —
verified by searching the whole card for `*hostapd*`, which returns nothing. That
is why pulling the card cannot help, and why the AP is dead even with no card
inserted.

The live file was never captured, so "empty" is an inference from hostapd's
error text. What is directly known: the copy of this file inside the appfs we
ship is **195 bytes** and begins `interface=wlan0`, so a reflash restores a
parseable config regardless of who corrupted the live one.

## Who writes this file

Two writers exist, and only one is ours:

| writer | mechanism | guard |
|---|---|---|
| `/app/bin/polaris_wifi_bt` (stock Benro) | regenerates the whole file from an embedded template at boot; contains both `channel=9 hw_mode=g` and `channel=36 hw_mode=a` templates plus `ssid=%s` | unknown, closed binary |
| `container/astro/ondisk/polaris-autojoin.sh:103` (ours) | `sed ... > "$HAPCONF.new" && mv` | none |

The stock binary's template selection also explains the observed `channel=9`
↔ `channel=48` oscillation. Attributing this incident to autojoin specifically is
**not established**; tracked in issue #21.

## The unguarded write we do control

`container/astro/ondisk/polaris-autojoin.sh:103` rewrites the file through a temp:

```sh
sed -e "s/^channel=.*/channel=$CH/" -e "s/^hw_mode=.*/hw_mode=$MODE/" \
    "$HAPCONF" > "$HAPCONF.new" && mv "$HAPCONF.new" "$HAPCONF"
```

On UBIFS a failed write can still leave a zero-length `.new` that `mv` then puts
in place. autojoin runs at every boot to chase the home network onto its channel
(the chip has one radio, so AP and STA must share it), so any write failure there
kills the AP permanently. `restore_ap()` only runs on the `hostapd did not come
back` path (line 113) — never on the truncation path.

## Fix A — reflash appfs from the SD card (preferred, no hardware needed)

The stock watcher `SP_EVENT_SD_SCAN` consumes the **extracted tree** at
`/app/sd/FwPkt/{camera,gimbal}/`. A bare zip at SD root is silently ignored
(`docs/ASTRO-SD-DEPLOY-DESIGN.md` constraint C1, issue #58).

Staged and verified on this machine:

| artifact | sha256 / md5 |
|---|---|
| `FwPkt.zip` | `504d4a36c32a74b31358b983043152dd127aea2226524d7a897b98b236f3cda3` (matches `install-manifest.json`) |
| all 6 `firmwareInfo` entries | verified by md5 **and** size |

Run `/home/ian/polaris-rescue/rescue.sh` with sudo. It repairs the FAT (the card
was force-remounted read-only after I/O errors), stages the tree, re-verifies
every artifact on-device-equivalent bytes, and disables autojoin so the config is
not truncated again.

Judge success by **uptime reset**, not by the link going dark — AP-link flaps
look identical to a reboot (`docs/CURRENT-STATE.md`).

After the flash, scan **both** bands: the packaged `hostapd.conf` inside appfs is
`ssid=polestar_001 channel=36 hw_mode=a`, but the device rewrites SSID and channel
at boot and has been observed as `polaris_d13e86` on 2.4 GHz channel 9.

### After ANY flash: re-install the astro kit (issue #265)

**A flash replaces appfs, and appfs is where `/app/astro` and the boot hook
`/app/network_telnetd.sh` live.** Both are deleted by it. This route is run by hand
from this document, so unlike `release-fwpkt.sh` step 7 it does not re-install the
kit and leaves no receipt — the device then reports the correct `FwVer`, looks
completely healthy over SSH, and has no plate solver and no port 8090, with nothing
in any log saying why. That is exactly what happened here: the kit was
`installed-verified` at `2026-11-15T12:26:30Z`, this flash ran that evening, and on
2026-11-16 `/app/astro` did not exist.

So once the AP is back, run:

```sh
./scripts/release/install-astro-kit.sh \
  out/astro-v109-camera-mainline-20261115 --no-indexes --no-wifi --reboot
```

`--no-indexes` and `--no-wifi` because the SD card survives the flash — the kit, the
astrometry indexes and `/app/sd/polaris-wifi/wpa.conf` are all still there and
byte-correct, and re-streaming them changes nothing while overwriting a live
`wpa.conf`. Add `--with-wifi` only if the card itself was rebuilt.

Then verify independently rather than trusting the script's own summary:

```sh
ssh root@192.168.0.1 'ls -l /app/astro/polaris-httpd; \
  grep -c "polaris-astro boot hook" /app/network_telnetd.sh; \
  netstat -tln | grep :8090'
curl -sS -o /dev/null -w '%{http_code}\n' http://192.168.0.1:8090/    # expect 200
```

`install-astro-kit.sh` appends a `kit_status=installed-verified` block to the
candidate's `install-receipt.txt`. If that block is missing after a flash, the kit
was not re-installed. The durable fix — a boot-time assertion that says so out loud
— is still open under #265; until it lands, this step is manual and mandatory.

## Fix B — serial console (no SD card, no network required)

The kernel console is real: `FwPkt/camera/config` sets
`console=ttyAMA0,115200`. Wire UART at **115200 8N1**, then:

```sh
# 1. confirm the diagnosis
wc -c /app/wifi/hostapd.conf          # expect 0 or truncated
cat /app/wifi/hostapd.conf

# 2. autojoin keeps its own pre-change copy -- restore from it if present
ls -l /app/wifi/hostapd.conf.autojoin-bak
cp /app/wifi/hostapd.conf.autojoin-bak /app/wifi/hostapd.conf

# 3. if there is no backup, write a minimal working config (2.4 GHz so every
#    client can see it) and start the AP. Deliberately mirrors the stock file
#    recovered from appfs, which carries NO driver= line -- do not add one, the
#    build's default driver is what worked on boot 15.
cat > /app/wifi/hostapd.conf <<'EOF'
interface=wlan0
ssid=polaris_d13e86
hw_mode=g
channel=9
beacon_int=15
max_num_sta=8
EOF
cd /app/wifi && ./hostapd -B hostapd.conf

# 4. stop autojoin re-truncating it, then reboot to make the fix durable
rm -f /app/sd/polaris-wifi/autojoin
sync; /sbin/reboot
```

`iw`, `hostapd` and `wpa_supplicant` all ship in `/app/wifi`, so this needs no
payload transfer.

## Follow-up

Tracked as **issue #21** — `polaris-autojoin.sh:103` should verify `$HAPCONF.new`
is non-empty and still contains `interface=` before `mv`, and call `restore_ap()`
when it does not. As written, a single failed write permanently bricks the AP with
no recovery path over the network — because the network is what died.

## The RED gate was an environment gap, and it now runs GREEN

The v109 handover recorded `24 passed, 1 failed, 2 skipped`, failing only on
`REQUIRED Bulb cancellation-return diagnostic not run: unicorn or pyelftools not
importable`. That is a prerequisite gap, not a firmware failure. Re-running with
the harness supplied:

```sh
./tests/run_prerelease_gate.sh \
  --build out/astro-v109-camera-mainline-20261115/FwPkt \
  --arm-harness-src ../BenroHardwareValidator/benro-polaris-test-harness/src

=== Pre-release gate summary: 26 passed, 0 failed, 1 skipped ===
Skipped: libgphoto2 capture contract (no --libgphoto2-src supplied)
GATE: GREEN
```

Both previously-blocked checks now pass:

- **Bulb cancellation-return** — `cancellation survives cleanup and publication; a
  failed stop still outranks it`. Observed returns:
  `cancel=-52 stop=0 return=-52` and `cancel=-52 stop=-1 return=-1`.
- **ARM emulation of Stage-2** — binary sha256 matches `install-manifest.json`,
  entry `0x15ed8`, 265 relocations resolved / 0 unresolved, 100000/100000
  instructions, 0 stub calls.

Two caveats on that GREEN:

1. It ran at HEAD `9d43482` with a dirty tree (`polaris-httpd.c`,
   `test_native_runtime_wiring.py`, `ASTRO-HISTORIC-SOLVE-TESTS.md`), not at the
   build commit `fcc2b5fa`. `polaris-httpd` **is** a shipped astro bundle artifact,
   so those uncommitted changes are not covered by this gate run.
2. The container harness reports 30 passed / 3 skipped here versus 31 in the
   original run; the three skips (`test_polaris_pentax_build_package.sh`,
   `test_source_input.sh`, `test_stage2_loader_compile.sh`) are prerequisite gaps,
   and no test files changed between `fcc2b5fa` and HEAD.

Physical qualification is still outstanding — the emulator states plainly that it
proves load, relocation and bounded execution only, and does not cover shutter
closure, PTP behaviour, the on-boot upgrade watcher, or Wi-Fi/AP behaviour.

## Evidence location

Preserved outside `/tmp` at `~/Documents/polaris-v109-sd-recovery-20261115/`
(848 files, 736 MB): `card-before.tar.gz`, `shipped-appfs/`, `log-review/`,
`gate-green-20261116/`, plus the prior investigation artifacts.

**Do not publish that tree as-is.** It contains `log-review/polaris-wifi/wpa.conf`
and `wpa_passphrase`, which hold a plaintext Wi-Fi PSK. Redact or exclude both
before any push or attachment.
