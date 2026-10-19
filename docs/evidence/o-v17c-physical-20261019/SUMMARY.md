# o-v17c (`.68`) physical qualification — 2026-10-19

Candidate: `o-v17c-colortemp-formless` → `6.0.0.54.68;date:2026.10.19;`
libgphoto2 `8e06d39ae` (merged PR #105, closes #104), patcher `36d72ae`,
camlibs `ptp2,pentax`. Single purpose: carry the `_pentax_prop_get` fix for the
one control that failed `.67` qualification.
Body: Pentax K-3 Mark III (`25fb:0189`), firmware 2.20, MTP mode,
output on `/app/sd/normal/`.

## Verdict

**PASS — Color Temperature (`0xd018`) is now usable through its named control,
`pentaxcolortemperature`, in both directions. No regressions: the control tree
gained exactly one entry, `0xd024`–`0xd026` remain withheld, the read-only
descriptor passthroughs still refuse writes, every other Custom Image control
reads and round-trips, and the capture path is qualified.**

`.68` is the first build that is release-qualified as Color Temperature support.
`.67` was not, and is superseded for that purpose.

## Install — VERIFIED

| check | result |
|---|---|
| upload | 68392387 B, on-device SHA-256 `14e5761c…e604d` **matches** the candidate |
| staged tree MD5s | all six `firmwareInfo` entries match (`appfs d6a99d1f…`, config, rootfs, uImage, polaris403, polaris413) |
| reboot is real | uptime `9373` → `79`; single boot for the whole session |
| installed identity | `INSTALLED BUILD IDENTITY: PASS`, `build_id=6.0.0.54.68-o-v17c-colortemp-formless`, `display_fwver=6.0.0.54.68` |
| installed binaries | **10/10 mandatory files SHA-256 match** the install manifest, 0 mismatch, 0 missing |

Upload note: the AP link drops mid-stream, and a naive append-resume produced a
file of the **correct size but wrong digest** (misaligned bytes). The transfer
only became trustworthy once each chunk was written at an explicit offset
(`dd seek=`) and a cumulative prefix hash was verified after every chunk. That
procedure is `out/upload-chunked.sh` and should be the default for this device.

## Acceptance test — `0xd018` through the named control — PASS

WB set to color-temperature-1 (`pentaxdirectwb=12`) first, since the control is
only meaningful in that mode. Every assertion taken from a **fresh process**, per
the async-apply finding from `.67`.

| step | `.67` | `.68` |
|---|---|---|
| `--get-config /main/status/pentaxcolortemperature` | **`Error (-1)`** | **`Label: Pentax Color Temperature`, `Readonly: 0`, `Current: 5000`** |
| `--get-config /main/other/d018` (raw cross-check) | `Current: 5000` | `Current: 5000` (agrees) |
| `--set-config pentaxcolortemperature=4000` | **rc=1, no write performed** | **rc=0** |
| named control re-read, fresh process | — | **`Current: 4000`** |
| raw `d018` re-read | — | **`Current: 4000`** (agrees) |
| restore to `5000`, WB → `auto` | rc=0 | rc=0 |

The named control and the raw property now agree in both states, which is the
strongest available oracle here. Transcript: `colortemp-named-control.txt`.

The widget renders as `Type: TEXT` with no value list — as designed. The
descriptor supplies no range, and none was invented; this is the same shape the
generic property path has always produced for `0xd018`.

## Blast radius — exactly one control

`_pentax_prop_get` serves ten controls (the nine `0xd021`–`0xd029` detail
parameters plus `0xd018`), so the relaxation could in principle have surfaced
nine new widgets. It surfaced one.

`--list-all-config` captured twice on `.68`, once with WB=`auto` and once with
WB=color-temp-1: **35 Pentax controls** and **36** respectively, and the diff
between them is a single added line, `+/main/status/pentaxcolortemperature`.
Nothing else appeared. The control is additionally gated by
`model_supports_color_temperature`, so it is absent outside the K-3 III family —
which is why the WB=`auto` capture of the tree does not show it either.

## Regression — no change from the `.67` baseline

| group | expected | result |
|---|---|---|
| `pentaxcisaturation` / `cihue` / `cikey` / `cifinesharpness` / `cihighlightcontrast` / `cishadowcontrast` | readable | **PASS** — all render `RADIO` with descriptor-derived ranges, `Current: 0` |
| `pentaxcisaturation` write `0 → +2 → 0` | applies, restorable | **PASS** — `Current: 2` then `Current: 0`, each confirmed from a fresh process |
| `pentaxcifiltereffect` / `cimonotonetoning` / `citoning` (`0xd024`–`0xd026`) | still withheld | **PASS** — `Error (-1)` on get, and absent from `--list-all-config`; the `Enumeration`/`NumberOfValues == 0` branch is untouched |
| `pentaxpropd02b`, `pentaxpropd02d` | read-only, refuse writes | **PASS** — render `Readonly: 1`, write attempt refused |

Transcripts: `ci-sweep-corrected.txt` (authoritative names), `ci-sweep.txt`
(first pass; contains two mistyped names — `pentaxcihightlightcontrast`,
`pentaxcirefinement`/`pentaxciuserfilter` do not exist; the real read-only
passthroughs are `pentaxpropd02b`/`pentaxpropd02d`).

## Capture path — PASS

| test | result |
|---|---|
| `canary-probe.py --shot --expected-files 1 --expected-sw 6.0.0.54.68` | **PASS** `lifecycle=[1,4,0]` → `SP_0355.dng` |
| same, re-run after the CLI sessions and daemon restore | **PASS** `lifecycle=[1,4,0]` → `SP_0356.dng` |

The second run matters: the qualification procedure stops and restarts the gphoto
daemon repeatedly, so the production path was re-proven after that churn rather
than only before it. Transcripts: `canary-single-shot.txt`,
`canary-after-daemon-restore.txt`.

## Stability

No segfault, OOM-killer or panic in `dmesg` since boot; no new core file (the
one `/app/sd/core` present is a 0-byte file dated 2026-10-05, unrelated);
`polestar_app` pid 249 unchanged throughout; one boot for the whole session.

`pgphoto.stage2ondisk` pid 250 did **not** survive — expected, not a fault: the
CLI qualification deliberately `kill -TERM`s that daemon to own the USB device,
and `/app/restart_gphoto` respawns it under new pids. The pid-invariance check
that applies to a pure-canary run therefore does not apply to this procedure;
the post-restore canary passing is the meaningful signal, and it passed.

## Caveats

- **A probe run immediately after the reboot returned `Could not detect any
  camera` / `Error (-105)` for every command while the body was plainly present
  on USB (`lsusb` showed `25fb:0189`).** It cleared on its own within a couple
  of minutes. Any qualification script must assert `--auto-detect` succeeds
  before treating per-control errors as results, otherwise a transient bus/
  session state is recorded as a control failure. The transcript on file is the
  clean re-run.
- The async-apply behaviour found in `.67` is unchanged and was not addressed
  here: a read issued immediately after a successful write can still return the
  pre-write value. All assertions above re-read from a fresh process.
- K-1 II behaviour of the relaxed branch is still untested. The relaxation only
  admits a `GetSet` scalar with `FormFlag == None`, and the control is
  model-gated, so the expected K-1 II behaviour is unchanged — but that is
  reasoning, not evidence.

## Ownership

Closes the acceptance gate recorded for `.67` and libgphoto2 #104. Update
`docs/RELEASE-VERSION-STATE.md` (`.68` row) and `docs/CURRENT-STATE.md`.
