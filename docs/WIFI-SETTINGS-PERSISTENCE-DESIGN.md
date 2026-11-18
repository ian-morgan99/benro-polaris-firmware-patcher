# Design: preserving Wi-Fi settings across a firmware reflash

Status: **design only, nothing implemented.** No device mutation. Written against
`main` @ `f8d344e`; every code fact below was read from this tree.

This was prompted by the `astro-v113-kit-identity-20261118` deploy on 2026-11-18, where
the head flashed cleanly (staged tree matched byte-for-byte, all six `firmwareInfo` MD5s
verified on-device) and then never came back: no `polaris_*` AP in the air, nothing on the
home LAN, `:8090` closed. The packet was good; the *survival model* is what is wrong.

## 1. What actually survives a reflash

The flash writes NAND partitions named in `firmwareInfo`. For this candidate those are
`config`, `uImage`, `rootfs`, `appfs`, `polaris403`, `polaris413`. The two that matter here:

| Partition | Mounts at | Reflashed? | Holds |
|---|---|---|---|
| `appfs` | `/app` (68 MB UBIFS) | **yes, wholesale** | `/app/astro`, `/app/network_telnetd.sh`, `/app/wifi/hostapd.conf`, `bootapp` |
| SD card | `/app/sd` | **no** | `polaris-wifi/wpa.conf`, `polaris-astro/site.conf`, the kit trees |

Evidence that `/app` is replaced wholesale: `install_astro.sh:41-43` — *"a firmware flash
replaces it wholesale and leaves it nearly full"*; `ASTRO-SD-DEPLOY-DESIGN.md` Failure A —
*"Flashing replaces `/app`, so the hook — and `/app/astro` — are deleted."*

The flash's only deletions on the card are its own staging area: `release-fwpkt.sh:268`
(`rm -rf /app/sd/FwPkt`) and `:315` (`rm -f /app/sd/FwPkt.zip .part`). Nothing else under
`/app/sd` is touched.

## 2. The three things people call "Wi-Fi settings", and where each lives

They are not one thing, and they fail differently. Conflating them is why this keeps
reading as "the flash wiped my Wi-Fi."

| # | Setting | Authoritative copy | Survives reflash? | Symptom after a bare firmware flash |
|---|---|---|---|---|
| S1 | **Station credentials** (home SSID/PSK) | `/app/sd/polaris-wifi/wpa.conf` (SD) | **yes** | none — the file is intact |
| S2 | **The join trigger** | `/app/network_telnetd.sh` → chains `polaris-autojoin.sh` (appfs) | **no** | autojoin never runs, so the intact `wpa.conf` is never read; head stays off the home LAN |
| S3 | **AP config** (`hostapd.conf`) | `/app/wifi/hostapd.conf` (appfs) | **no — and it can be left truncated** | AP never broadcasts: *"polaris_d13e86 never broadcasts; SSH, `:8090` and the Benro app are all unreachable"* |

So after a firmware-only flash the head can have **both** paths to the network broken:
station join (S2) and AP broadcast (S3). That is the total silence observed on v113. The
credentials (S1) were never lost — the mechanism that reads them was reset.

`polaris-autojoin.sh:26-30` confirms the S1/S2/S3 split: `CONF=/app/sd/polaris-wifi/wpa.conf`
(SD), but `HAPCONF=/app/wifi/hostapd.conf` (appfs), and the script itself is invoked from
the appfs boot hook.

### Correction to an earlier reading of S3

An earlier draft of this doc claimed S3 breaks because the flash *reverts* `hostapd.conf`
to a broken stock file. That is wrong, and `docs/POLARIS-AP-HOSTAPD-EMPTY-RECOVERY.md`
already has the verified cause — **issue #21**:

- The `hostapd.conf` packaged inside appfs is **valid**: `ssid=polestar_001 channel=36
  hw_mode=a`. A flash alone does not produce an unparseable file.
- The breakage is a **truncation race**. `polaris-autojoin.sh:103` writes `$HAPCONF.new`
  and `mv`s it over `$HAPCONF` without checking the result is non-empty or still contains
  `interface=`. `/app/wifi` shares the small UBIFS with `/app/astro`, so a single failed
  write leaves a zero-length config, and `restore_ap()` only runs on the *"hostapd did not
  come back"* path (line 113) — never on the truncation path. One bad write bricks the AP
  permanently, with no network recovery path, because the network is what died.
- Which writer produced the bad file is explicitly **not verified** in that doc; do not
  assert it here either.

Consequence for this design: Layer 2 must not simply regenerate `hostapd.conf` at boot,
because it would hit the same full-UBIFS failure. See §5 Layer 2.

## 3. Why the current flow loses S2/S3 even when it "succeeds"

`release-fwpkt.sh` already knows a flash deletes the astro stack (`:39-40`, `:489`) and,
by default, re-installs the kit afterwards (`INSTALL_KIT=1`, `:502-505`) precisely to put
the hook back. The failure modes are:

1. **`--no-kit` was used** (this deploy). `release-fwpkt.sh:496-500` prints a WARN and
   tells the operator to run `install-astro-kit.sh` by hand — but it does not *stop*. A
   flash that deletes the boot hook and then skips the step that restores it is a
   self-inflicted brick of the network path, and the run still exits looking fine.
2. **Even with the kit installed**, survival lasts only until the *next* firmware flash,
   because the hook lives in appfs. Every firmware release re-breaks S2/S3 and depends on
   a human remembering to re-push the kit over a network path that the previous flash just
   removed. Chicken-and-egg: you need the network to fix the thing the flash broke by
   removing the network.

## 4. Design goal

After any firmware reflash, with **no operator action and no network access**, the head
must come back on the network by itself — either by joining the home SSID (S1+S2) or by
broadcasting a usable AP (S3). Credentials must never need re-entering.

## 5. Principle: SD is authoritative, appfs carries only a trigger

The fix is not "copy more into appfs" — appfs is wiped every flash and is nearly full
(`install_astro.sh:41-43`). The fix is to make the *authoritative* Wi-Fi state live on the
SD card (which survives) and have a **minimal, self-restoring trigger** in appfs rebuild
the runtime config from SD at every boot.

This is the same two-layer shape already accepted for the astro bundle in
`ASTRO-SD-DEPLOY-DESIGN.md` §4 (Layer 1 bootstrap hook in the flashed appfs; Layer 2 the
bundle on SD). This doc extends that to Wi-Fi specifically and closes the gap it left open:
that design restores the *astro* boot hook but does not, by itself, restore AP config or
guarantee autojoin runs after a **stock** flash.

### Layer 1 — bootstrap hook carried in the flashed appfs (fixes S2)

Ship a tiny `/app/network_telnetd.sh` inside the Astro candidate's `appfs`, using the
mechanism already proven for the SSH debug hook (`patch.sh:679-703`): grep `bootapp` to
prove it calls the name, refuse if it does not (C4 — never edit `bootapp`), install with
bootapp's own uid/gid/mode. Because the hook is *inside* the flashed image, flashing an
Astro candidate **restores** it instead of deleting it.

The bootstrap does only three things and must not block (`polaris-astro-boot.sh:1-8`:
bootapp runs it inline):
1. chain any pre-existing hook to `network_telnetd.pre-astro.sh` (C3, `install_astro.sh:91-98`);
2. wait for `/app/sd` to mount (C2 — SD is not mounted when bootapp runs; existing hook
   waits up to 45 iterations, `polaris-astro-boot.sh:24,49`);
3. hand off to the SD-carried stack: `/app/sd/polaris-wifi/polaris-autojoin.sh` and
   `/app/sd/polaris-astro/polaris-astro-boot.sh`.

If SD never mounts it exits non-destructively, exactly as today.

### Layer 2 — AP config generated from SD at boot (fixes S3)

Do **not** fix #21 by regenerating `hostapd.conf` in place on the same UBIFS — that is the
exact filesystem whose full condition caused the truncation. Two changes are needed, in
this order:

**(a) Fix #21 first.** Before any `mv` onto `$HAPCONF`, verify `$HAPCONF.new` is non-empty
and still contains `interface=`, and call `restore_ap()` when it does not. Also check the
write succeeded rather than relying on `set -e`, which does not catch a short write.
Without this, Layer 2 inherits the same silent brick.

**(b) Then carry the desired AP identity on the card** and materialise it at boot from a
verified temp file, refusing to install it if the target filesystem cannot hold it:

```
/app/sd/polaris-wifi/ap.conf        # ssid=, psk-hash, channel — operator-owned, survives
```

The bootstrap, before starting `hostapd`, writes `/app/wifi/hostapd.conf` from `ap.conf`
if `ap.conf` is present and newer than the current file. If `ap.conf` is absent it leaves
the flashed `hostapd.conf` alone (stock behaviour preserved). This makes AP SSID/password
survive every reflash, because the copy that matters is on SD and the appfs one is a
derived artifact rebuilt at boot — mirroring how `polaris-autojoin.sh:48-52` already backs
up and restores `hostapd.conf` around a join.

### Layer 3 — visible when a stock flash removes the hook (fixes the silence)

Flashing a *non-Astro* firmware still deletes the hook; that is unavoidable and correct.
The difference required here is that it must be **loud, not silent**. On the next boot with
SD present but no hook, write one line to `/app/sd/polaris-wifi/WIFI-STATUS`:

```
NO_BOOT_HOOK: astro/wifi stack absent from /app after flash.
              Re-push the kit: scripts/release/install-astro-kit.sh <build-dir>
```

This turns the v113 outcome (total silence, ~85 min of blind scanning) into a one-line
diagnosis readable by pulling the card — no serial console needed.

## 6. Operational guard (cheap, do this regardless of Layers 1-3)

`release-fwpkt.sh:496-500` currently only WARNs when `--no-kit` is passed while a kit sits
beside the candidate. Make it **fail closed** unless the operator also passes an explicit
override, because the combination "flash that deletes the hook" + "skip the step that
restores it" is exactly how v113 was bricked at the network layer:

```
ERROR: --no-kit with a kit present in $BUILD_DIR. The flash just deleted
       /app/astro and its boot hook; nothing will start the Web UI or join
       Wi-Fi on reboot. Re-run without --no-kit, or pass
       --allow-hookless-flash if you will re-push the kit yourself.
```

Also: before rebooting, record whether the device *currently* has `/app/astro` (it did on
v113). If it does and the run is going to remove it without restoring it, that is a
regression the operator must acknowledge, not a warning they scroll past.

## 7. What this does NOT change

- **S1 credentials** already survive; no migration needed. `install-astro-kit.sh:156-158`
  already states *"The reason is NOT credential loss — wpa.conf lives on the card."* This
  doc agrees and keeps that boundary.
- **C4 (never modify bootapp)** is preserved: Layer 1 installs a hook file bootapp already
  calls, it does not edit bootapp.
- **C5 (no auto-flash without authorisation)** is untouched; this is about post-flash
  survival, not triggering flashes.

## 8. Open questions to resolve before implementing

1. **Which writer truncated `hostapd.conf`?** Resolved as *not determinable* by
   `docs/POLARIS-AP-HOSTAPD-EMPTY-RECOVERY.md`, which names two candidate writers and
   declines to pick one. Layer 2 must therefore be safe against either, not tuned to one.
2. **Free space on the `/app` UBIFS after a flash.** `install_astro.sh:41-43` says a flash
   leaves it "nearly full"; #21's truncation is consistent with that. Layer 2 needs a real
   free-space check, and the astro bundle may need to stop copying into `/app/astro` at all
   (run from SD) so the filesystem stops being the constraint.
2. **Does bootapp call `network_telnetd.sh` in *every* firmware we ship, or only some?**
   `patch.sh:683-690` already handles "try the next candidate hook" (`start_agent.sh`);
   Layer 1 should reuse that selection rather than assume the name.
3. **Ordering vs autojoin's channel move.** `polaris-autojoin.sh:48-52` restarts hostapd on
   the home channel and backs up `hostapd.conf`. Layer 2's regeneration must run *before*
   autojoin, or it will fight the backup/restore. Define the sequence explicitly.

## 9. Immediate recovery for the v113 head (not part of the design)

Recovery procedure is already written and staged in
`docs/POLARIS-AP-HOSTAPD-EMPTY-RECOVERY.md` — do not restate it here. Summary of what
applies to v113:

- **Fix A** (preferred, no hardware): `/home/ian/polaris-rescue/rescue.sh` with sudo —
  repairs the FAT, stages the extracted `FwPkt/` tree, re-verifies every artifact, and
  disables autojoin so the config is not truncated again.
- **Fix B** (serial console, no SD or network): UART at `115200 8N1` — the console is real,
  `FwPkt/camera/config` sets `console=ttyAMA0,115200`. Restore from
  `hostapd.conf.autojoin-bak`, or write the minimal 2.4 GHz config from that doc. Do not
  add a `driver=` line; the stock file has none and the build's default driver is what
  worked.
- **Then re-install the kit**, with the flags that doc specifies:
  `install-astro-kit.sh <build-dir> --no-indexes --no-wifi`. This *contradicts* the advice
  given verbally during the v113 deploy (`--with-wifi`, full bundle). The doc is correct:
  the SD card survives the flash, so `wpa.conf`, the kit and the indexes are still
  byte-correct, and re-streaming them changes nothing while overwriting a **live**
  `wpa.conf`. Add `--with-wifi` only if the card itself was rebuilt.
- **Judge success by uptime reset**, not by the link going dark — AP-link flaps look
  identical to a reboot.

### Detection lesson from this incident

Host-side scans for the head must cover **both bands and every SSID**, not just names
matching `polaris`. The packaged `hostapd.conf` broadcasts `ssid=polestar_001 channel=36
hw_mode=a` (5 GHz), while the device rewrites SSID and channel at boot and has been seen
as `polaris_d13e86` on 2.4 GHz channel 9. Grepping for `polaris` misses `polestar_001`
entirely — which is exactly what happened during the v113 outage, where ~85 minutes of
scanning was spent filtering on the wrong SSID.

## 10. Prior art this doc must not duplicate

| Concern | Already owned by |
|---|---|
| AP truncation root cause and recovery | `docs/POLARIS-AP-HOSTAPD-EMPTY-RECOVERY.md`, issue **#21** |
| Boot hook deleted by flash; SD self-deploy design | `docs/ASTRO-SD-DEPLOY-DESIGN.md`, issue **#265** |
| Kit must be re-pushed after every flash | `docs/FIRMWARE-INSTALL-PROCESS.md`, `install-astro-kit.sh:156-158` |
| Silent zip-at-SD-root failure | issue **#58**, constraint C1 |

What is genuinely new here is only: the S1/S2/S3 taxonomy, the fail-closed `--no-kit`
guard in §6, and making a missing boot hook visible on the card (§5 Layer 3). Everything
else should link to the documents above rather than restate them.
