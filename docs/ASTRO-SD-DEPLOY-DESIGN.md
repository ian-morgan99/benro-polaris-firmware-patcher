# Design: SD-card ZIP self-deployment for the Astro bundle (#265)

Status: **design only, nothing implemented.** No device mutation. Written against
`feature/v95-libgphoto2-integration`; every code fact below was read from this tree.

## 1. The two failures being fixed

**Failure A — no way to start the Web UI.** `polaris-httpd` is started only by
`container/astro/ondisk/polaris-astro-boot.sh`, which is installed as
`/app/network_telnetd.sh` by `install_astro.sh:97`. `/app/bootapp` runs that path at boot
if it exists (verified in `container/patch.sh:664`:
`if [ -f "/app/network_telnetd.sh" ];then cd /app; ./network_telnetd.sh; fi`). Flashing
replaces `/app`, so the hook — and `/app/astro` — are deleted. v94 was installed-verified
and its Astro half never ran for exactly this reason
(`docs/evidence/liveview-crash-camera-offbus-20261103/SUMMARY.md`).

**Failure B — no deployment path.** `scripts/build-astro-bundle.sh` emits a directory tree
plus `ASTRO-MANIFEST.sha256`; nothing on the device consumes it. Installation is a manual
telnet session running `install_astro.sh`.

## 2. Hard constraints, each from evidence

| # | Constraint | Source |
|---|---|---|
| C1 | A bare zip at SD root is **silently ignored**. The stock watcher `SP_EVENT_SD_SCAN` walks the extracted tree `/app/sd/FwPkt/{gimbal,camera}/`. | #58 — cost ~5 h of K-1 II diagnosis attributed to o-v9d instead of o-v9f |
| C2 | `/app/sd` is **not mounted when bootapp runs**. The existing hook waits up to 45 iterations for `$SITE` before giving up. | `polaris-astro-boot.sh:24,49` |
| C3 | `/app/network_telnetd.sh` is a **single** hook; the Astro installer chains whatever was there first to `/app/network_telnetd.pre-astro.sh`. | `install_astro.sh:91-98`, `polaris-astro-boot.sh:34-40` |
| C4 | Never modify `bootapp`. The existing SSH-hook code greps `bootapp` for a hook name it provably calls and **dies** rather than editing it. | `patch.sh:679-688` |
| C5 | Camera firmware must never auto-flash without explicit operator authorisation; installed bytes must be verified against an immutable manifest; reboot outcome confirmed. | #201, #200, #202 |
| C6 | Mlog/Clog retain ~30 s, so a failed deploy cannot be post-mortemed from device logs alone. | #213 |

## 3. Accepted SD path — explicit, never inferred

```
/app/sd/polaris-deploy/incoming/<package-id>.zip      <- operator drops this
/app/sd/polaris-deploy/staging/                       <- extracted, verified here
/app/sd/polaris-deploy/applied/<package-id>/          <- kept for rollback
/app/sd/polaris-deploy/deploy-state.txt               <- durable record (survives reboot)
/app/sd/polaris-deploy/DEPLOY-STATUS                   <- one line, human readable
```

Nothing is accepted anywhere else. **SD root is explicitly rejected with a loud message**,
because C1's failure mode is silence: if `FwPkt.zip` or any `*.zip` is found at `/app/sd/`
root, the deployer writes

```
REJECTED: <name> at SD root is not a supported location.
          Expected /app/sd/polaris-deploy/incoming/<package-id>.zip
```

to `DEPLOY-STATUS`, echoes it to the boot console, and continues booting. It does not act
on it. This turns #58's silent failure into a visible one.

## 4. Flash survival — two layers

The hook cannot live only on SD: C2 means bootapp runs before SD exists, and bootapp only
looks at `/app/network_telnetd.sh`. So the hook must be inside the flashed image.

**Layer 1 — bootstrap hook, carried in the Astro FwPkt's appfs.**
Ship a small `/app/network_telnetd.sh` as part of the Astro candidate's appfs, using the
mechanism already proven for the SSH debug hook (`patch.sh:679-703`: grep `bootapp` to
prove it calls the name, refuse if it does not, install with bootapp's own uid/gid/mode).
Because the hook is *inside* the flashed image, flashing an Astro candidate **restores** it
instead of deleting it. This inverts Failure A.

The bootstrap is tiny and does only: chain any pre-existing hook (C3), wait for SD (C2),
then hand off to `/app/sd/polaris-astro/polaris-astro-deploy.sh` if present. If SD never
mounts it exits non-destructively, exactly as today.

**Layer 2 — the bundle, carried on SD.** Binaries, `site.conf`, camera profiles, FITS
indexes and the Gaia catalogue stay on SD. They are far too large for appfs and already
live there (`INDEXES=/app/sd/astrometry`, `CONF=/app/sd/polaris-astro/site.conf`).

Consequence to state plainly: **flashing a *stock* (non-Astro) firmware still removes the
hook.** That is correct and unavoidable — stock firmware has no Astro. The difference is
that it is now visible: the bootstrap writes `DEPLOY-STATUS` on the SD card recording that
the hook is absent, and the next Astro flash restores it.

## 5. Package format

Reuse what the builder already emits rather than inventing a format.
`build-astro-bundle.sh:207-235` produces `ASTRO-MANIFEST.sha256` (per-file `sha256sum`) and
`build-source-provenance.txt`. The ZIP wraps that tree unchanged plus one new file:

```
manifest.json {
  "schema": 1,
  "package_id": "astro-v95-<slug>-YYYYMMDD",
  "kind": "astro-bundle",              // "astro-bundle" | "camera-firmware"
  "min_firmware": "6.0.0.54.95",       // refuse if installed fwver is lower
  "created_utc": "...",
  "files": [ {"path":"polaris-httpd","sha256":"...","mode":"0755"} ],
  "entrypoint": "install_astro.sh"
}
```

`ASTRO-MANIFEST.sha256` remains the authoritative per-file hash list; `manifest.json` adds
identity, kind and version gate. Both must agree — a disagreement is a hard reject.

## 6. Deploy algorithm (idempotent, fail-closed)

Runs from the bootstrap hook at boot, and can be run by hand.

1. Wait for SD mount, bounded (reuse the existing 45-iteration pattern, C2).
2. List `incoming/*.zip`. For each:
   a. Read `manifest.json` from the archive **without extracting** (`unzip -p`). If it is
      absent or unparseable → reject, record reason, continue.
   b. `kind == "camera-firmware"` → **do not flash.** Move to
      `incoming/awaiting-authorisation/`, write `DEPLOY-STATUS` saying exactly what is
      staged and which command authorises it (C5). This issue must not become a firmware
      flashing path.
   c. `package_id` already in `deploy-state.txt` with the same archive hash → skip, log
      "already applied". Idempotent.
   d. `min_firmware` > installed fwver → reject as incompatible.
   e. Extract to `staging/<package-id>/`, verify **every** sha256 in `manifest.json` and
      `ASTRO-MANIFEST.sha256`. Any mismatch → delete staging, reject, keep previous install
      untouched.
   f. Refuse downgrade: if `package_id` sorts below the applied one and the archive is not
      explicitly marked `allow_downgrade`, reject.
   g. Apply: run `install_astro.sh` with `SRC=staging/<package-id>`. It already checks each
      required binary rather than best-effort copying, and already preserves an existing
      `network_telnetd.sh` by chaining it (C3).
   h. On success: move staging → `applied/<package-id>/`, append to `deploy-state.txt`
      (`utc, package_id, archive sha256, result`), write `DEPLOY-STATUS=ok <id>`, `sync`.
   i. On failure: leave the previous install alone, write `DEPLOY-STATUS=failed <id>:
      <reason>` to SD (C6 — the record must survive reboot and outlive Mlog's ~30 s).
3. Start `polaris-httpd` as today.

## 7. Making success/failure observable

- `DEPLOY-STATUS` on SD, one line, survives reboot (C6).
- Boot console echo of the same line.
- `polaris-httpd` `/api/deploy/status` returning `deploy-state.txt`, so the Web UI shows
  what is installed and what was rejected — closing the "no way to tell" gap from #58.
- A missing hook after a stock flash must be stated, not hidden.

## 8. Open questions before implementation

1. **Is `unzip` on the device?** Not verified in this tree. If absent, either ship a static
   unzip in the Astro bundle or switch the accepted package to `.tar.gz` (which the builder
   already produces and busybox tar handles). This decides the format and must be answered
   first — do not assume busybox has unzip.
2. Does `SP_EVENT_SD_SCAN` conflict with a second SD watcher? #58 shows it walks
   `/app/sd/FwPkt/`; our path is disjoint, but confirm it does not choke on an unknown
   top-level dir.
3. Where is installed fwver readable from at boot without polestar_app being up? Needed for
   the `min_firmware` gate.
4. Should the bootstrap hook be opt-in per candidate (like `SSH_PUBKEY`, issue #31) or always
   on for Astro builds? Recommend always-on for Astro candidates only, since Failure A is the
   default state today.

## 9. Acceptance mapping

| From #265 | Covered by |
|---|---|
| One ZIP + reboot → httpd on `:8090`, no telnet | §4 layer 1 + §6 step g |
| Reflash does not silently remove Astro | §4 (hook in appfs) + §7 |
| Bad/truncated/downgraded ZIP rejected, previous install intact | §6 steps e, f, i |
| Explicit accepted path, not assumed (C1/#58) | §3 |
| Camera firmware gated separately (C5) | §6 step b |
