# o-v17b (`.67`) physical qualification — 2026-10-19

Candidate: `o-v17b-ci-colortemp-20261018` → `6.0.0.54.67;date:2026.10.18;`
Body: Pentax K-3 III (`25fb:0189`), firmware 2.20, on `/app/sd/normal/`.
Identity re-proven per run: `/app/FwVer`, provenance `build_id`
`6.0.0.54.67-o-v17b-ci-colortemp-20261018`, libgphoto2 `6c6142625`,
camlibs `ptp2,pentax`. Dual-path (#38): `/proc/<pgphoto>/maps` loads
`stage2/libgphoto2.so.6` + `libpolaris_stage2.so`.

## Verdict

**PARTIAL PASS — capture path qualified; every exposed Custom Image control
(`0xd021`–`0xd023`, `0xd027`–`0xd029`) writes and round-trips; Color Temperature
(`0xd018`) is NOT usable through its named control; Custom Image `0xd024`–`0xd026`
remain withheld (as designed).**

(Verdict unchanged by the later extended-CI addendum below, which completes the
exposed-control coverage and corrects the raw-property oracle used earlier.)

The candidate's headline feature does not reach a client through the widget the
candidate added. The underlying property works, but only through the generic
raw-property path.

## Capture path — PASS

| test | result |
|---|---|
| `canary-probe.py --shot --expected-files 1 --expected-sw 6.0.0.54.67` | **PASS** `lifecycle=[1,4,0]` → `SP_0352.dng` (24 s) |
| `canary-two-shot.py --expected-files 1 --expected-sp-prefix /app/sd/normal/SP_` | **PASS** `shots=2` → `SP_0353.dng`, `SP_0354.dng` (distinct) |

The body was in RAW-only mode. `photoFormat` is not authoritative for the output
count (the live-gate oracle was corrected on exactly this point in the 2026-09-26
post-merge review, see `docs/CURRENT-STATE.md`), so the obligation must come from
an independent mode contract. The first attempt with `--expected-files 2` correctly
returned `verdict=partial-files` with one DNG — the oracle behaving, not a fault.
Transcripts: `canary-single-shot.txt`, `canary-two-shot.txt`.

Stability across all captures: `pgphoto.stage2ondisk` pid **250** and
`polestar_app` 249 unchanged, no core file, no segfault/OOM in `dmesg`, no
device reboot.

## Custom Image `0xd021`–`0xd029` — PASS on the exposed subset (completed in the addendum)

Via the direct CLI with the shipped Stage-2 stack (daemon stopped, one chained
gphoto2 session, service restored with `/app/restart_gphoto`):

| control | property | read | write | read-back |
|---|---|---|---|---|
| `pentaxcisaturation` | `0xd021` | `0` | `=2` | **`2` via the widget AND via raw `/main/other/d021`** |
| `pentaxcihue` | `0xd022` | `0` | `=-2` | **`-2` via the widget AND via raw `/main/other/d022`** (signed path correct) |
| restore | — | — | `=0` | `0`, confirmed from a **separate process** |

### Caveat: the applied value is not immediately observable

The signed path was re-tested three times and the results were **not consistent
between runs**, which is itself worth recording:

| run | sequence | raw `d022` observed |
|---|---|---|
| 1 | `set hue=-2` → raw read | **`0`** (write reported rc=0) |
| 2 | raw read → `set hue=-2` → raw read → widget read → `set hue=0` → raw read | `-2`, `-2`, `-2`, **`-2`** (the restore to `0` was not yet visible) |
| 3 | `set hue=0` (rc=0) → **fresh process** raw read | **`0`** |

So the writes do reach the camera (run 3 proves the value settles, and run 2's
first read proves run 1's write had in fact applied), but a read issued
immediately after a successful `--set-config` — even in the same session, after
the candidate's own read-back verification has passed — can still return the
pre-write value. The camera appears to apply these Custom-Image properties
asynchronously, which is the same `0x2001` acknowledges-but-does-not-apply
behaviour PR #103's read-back was written to catch. The read-back is therefore
**not sufficient to prove the value is live**; a qualification run must re-read
from a fresh session (or after a delay) before asserting the applied value.
Not treated as a `.67` regression — the value does land — but it weakens any
test that asserts immediately after a write.

Ranges come from the camera's own descriptor, as intended — `-4…+4` for
saturation/hue/key/highlight/shadow, `0|1` for fine sharpness — and match the
raw `other/d021`-`d029` descriptors in the same dump. No hard-coded table is
visible in the rendered widgets.

`0xd024`–`0xd026` (filter effect / monotone toning / toning): the raw
descriptors return **empty enumerations** (`other/d024` renders `MENU` with zero
choices), and the named controls are withheld — `--set-config
pentaxcifiltereffect=1` fails closed with `GP_ERROR` rather than accepting a
value with no source-defined list. That is the documented fail-closed design.

**The `0xd024` "255 sentinel" question is answered: the descriptor does NOT
enumerate 255.** It enumerates nothing. So there is no sentinel to confirm, and
withholding remains correct until a source-derived list exists.

## Color Temperature `0xd018` — FAIL through the named control

The camera **does not advertise `0xd018`** in its `GetDeviceInfo` property list
(`print_debug_deviceinfo` shows it only as an unsolicited entry, and the
`--list-all-config` dump has no `other/d018` node), so the generic widget is
absent until WB is switched into a color-temperature mode. That part is expected
Pentax behaviour. The problem is what happens after:

| step | result |
|---|---|
| `--set-config pentaxdirectwb=12` (color-temp-1) | rc=0, read-back `color-temp-1` |
| `--get-config /main/status/pentaxcolortemperature` | **rc=1, `Error (-1: 'Unspecified error')`** |
| `--get-config /main/other/d018` | **rc=0, `Current: 5000`** |
| `--set-config pentaxcolortemperature=4000` | **rc=1**, raw read-back still `5000` (no write performed) |
| `--set-config /main/other/d018=4000` | **rc=0**, raw read-back **`4000`** |
| restore WB → `auto`, `d018` → `5000` | rc=0, verified |

So the property is fully readable and writable on this body — the failure is in
the candidate's own wrapper, not the camera.

**Root cause (from the source, confirmed by the widget shape):**
`_pentax_prop_get()` fails closed when `desc.FormFlag == PTP_DPFF_None`. On the
K-3 III `0xd018` is a plain range-less UINT16: `GetDevicePropDesc` succeeds and
returns a usable current value, but with **no enumeration and no
min/max/step form** — the generic path renders it as `Type: TEXT, Current:
5000`, which is exactly the `FormFlag == PTP_DPFF_None` shape. The guard written
to reject "a descriptor that advertises no concrete values" for the empty-enum
CI properties therefore also rejects the one property that is genuinely a
scalar-with-no-form. The same guard in `_pentax_prop_put()` blocks the write.

Note the two cases are not the same thing: `0xd024`–`0xd026` are
`FormFlag == Enumeration` with `NumberOfValues == 0` (a genuinely unknown value
set — withhold is right), whereas `0xd018` is `FormFlag == None` on a
`GetSet`-capable scalar whose value the camera happily accepts. The guard
conflates them.

The write fails **downstream of that same guard, not through a second one**:
`_pentax_prop_put()` only rejects `desc.GetSet != PTP_DPGS_GetSet`, which
`0xd018` passes. Because the get path returns `GP_ERROR_NOT_SUPPORTED`, the
widget is never instantiated, so `--set-config` errors before
`_put_INT`/`ptp_setdevicepropvalue` is reached. Fixing the get path unblocks
both directions.

## Repro (device, one session)

```sh
D=/app/lib/stage2; export LD_LIBRARY_PATH=$D:/app/lib \
  CAMLIBS=$D/libgphoto2/2.5.34 IOLIBS=$D/libgphoto2_port/0.12.2
PID=$(cat /var/run/openpolaris-pgphoto.pid); kill -TERM $PID; sleep 2
/app/bin/gphoto2 --set-config /main/status/pentaxdirectwb=12 \
  --get-config /main/status/pentaxcolortemperature   # Error (-1)
/app/bin/gphoto2 --get-config /main/other/d018       # Current: 5000
/app/bin/gphoto2 --set-config /main/other/d018=4000 \
  --get-config /main/other/d018                      # Current: 4000
/app/bin/gphoto2 --set-config /main/status/pentaxdirectwb=0
/app/restart_gphoto
```

## Ownership

First divergence is in the **libgphoto2 fork** (`_pentax_prop_get`/`_put` in
`camlibs/ptp2/config.c`): the direct CLI against the shipped stack reproduces it
with no Polaris/Stage-2 involvement. Per the source/runtime rule, that belongs in
`ian-morgan99/libgphoto2`, not this repo.

## Bulb (separate, not a `.67` regression)

With the dial physically on **B**, `268` still reported the 57-entry timed list
(`V:9`) instead of the B-mode single-entry bulb list, and
`264 state:1;bulb:5;c:-1;` returned `state:-6` twice. Recorded on #164.
Transcripts: `bulb-refusal-1.txt`, `bulb-refusal-2.txt`.

## Addendum — extended CI coverage (same day, later session)

The remaining exposed controls were then exercised: `pentaxcikey` (`0xd023`),
`pentaxcihighlightcontrast` (`0xd027`), `pentaxcishadowcontrast` (`0xd028`),
`pentaxcifinesharpness` (`0xd029`), plus the read-only descriptor passthroughs
`pentaxpropd02b` and `pentaxpropd02d`.

### Named widgets — PASS (all four)

Each accepts a write (`rc=0`) and the widget's own value read-back **in a fresh
process** reflects it; every restore was verified the same way. Note the widget
`Current:` is the *value* while `--set-config name=N` addresses the *choice
index*, so writing index 5 on a `-4…+4` control correctly yields `Current: 1`.

| control | before | write (index) | fresh read-back | restore | restored (fresh) |
|---|---|---|---|---|---|
| `pentaxcikey` | `0` | 5 | **`1`** | 0 | `0` |
| `pentaxcihighlightcontrast` | `0` | 5 | **`1`** | 0 | `0` |
| `pentaxcishadowcontrast` | `0` | 5 | **`1`** | 0 | `0` |
| `pentaxcifinesharpness` | `1` | 0 | **`0`** | 1 | `1` |

Ranges again come from the camera's own descriptor (`-4…+4`, and `0|1` for fine
sharpness) — no hard-coded table.

### Correction to the earlier method: raw `d0XX` is NOT a usable oracle here

The raw nodes did **not** track the widgets, and in one case disagreed *before
any write*:

| property | raw vs widget |
|---|---|
| `d023` | agreed (`0`/`0`, then `1`/`1`) |
| `d027` | raw `1` while widget `0` — **both before the write and after the verified restore** |
| `d028` | raw stayed `0` while the widget moved to `1` and back |
| `d029` | raw `0` while the widget moved `1`→`0`→`1` |

So for these Custom-Image properties the raw `/main/other/d0XX` value is either
asynchronously lagged or differently encoded, and a raw/widget disagreement is
**not** evidence of a control failure. The reliable oracle is the named widget
read from a fresh process. (This refines the earlier section, which treated raw
agreement on `d021`/`d022` as confirmation — that agreement was not reproducible
here.)

### Deep-settle re-test — inconclusive (methodology, not firmware)

A follow-up intended to settle each write for 20–40 s and re-read produced empty
reads and `rc=1` writes after the first control, with
`Pentax session already open from a previous connection` in the output. Cause:
one `gphoto2` process per read issued back-to-back, i.e. PTP session churn. Not
a `.67` fault; a correct re-test must batch reads into a single session.

### Read-only descriptor passthroughs — PASS as designed

Both render and are `Readonly: 1`:

- `pentaxpropd02b` → `code=0xd02b; datatype=0x0002; getset=1; form=2;
  enum-count=3; value-bytes=2; value-hex=0000`
- `pentaxpropd02d` → `code=0xd02d; datatype=0x4002; getset=1; form=0;
  enum-count=0; value-bytes=8; value-hex=0400000000000000`

`0xd02d` shows `form=0; enum-count=0`, consistent with the named CI user-filter
control being withheld (fail-closed) rather than rendered with no value set.

## Final camera state (restored, verified)

All six Custom-Image controls confirmed neutral from a **fresh session**:
`pentaxcisaturation=0`, `pentaxcihue=0`, `pentaxcikey=0`,
`pentaxcihighlightcontrast=0`, `pentaxcishadowcontrast=0`,
`pentaxcifinesharpness=0`; `pentaxdirectwb=auto`, `0xd018=5000` (as found).
Daemon restored via `/app/restart_gphoto` after every session.
