# Bulb regression evidence — 2026-10-02

## What the last logs prove

The display regression is real and is in the value supplied by the firmware
stack, not in the Polaris app's final display widget.  `Mlog_000210.log` shows
the shutter choices arriving as `1m`, `1m10s`, and `1m20s` (lines 1235–1239).
For the selected `1m10s` entry, `polestar_app` then records `u32ShutterUs
60000000` (lines 1240–1242); selecting the next entry repeats the same 60 s
value for `1m20s` (lines 1306–1313).  The proprietary parser is therefore
discarding the seconds suffix and converting both values to 60 seconds.

The source cause is libgphoto2 commit `6fe047613`: it changed whole-second
labels from `60s` to `1m`, and from `70s` to `1m10s`.  That is readable to a
human but incompatible with the Polaris parser, which only consumes the
minute prefix.  No `polestar_app` binary change caused this regression.

The same Mlog capture request was `state:1; ... b:0;` (line 1361), not a
verified Bulb request, and the camera was physically removed at lines
1370–1378.  It must not be misreported as a completed 70 s Bulb failure.
Separately, the prior Clog evidence contains a 70 s Bulb condition report and
the earlier 110 s session contains repeated `Could not capture image` results
after roughly 66 s (for example `Clog_000180.log` lines 75653–77195).  That
matches the second defect: the capture wait was losing the pre-capture timer
and could abort long exposures on a shorter transport/read failure budget.

## Fix shipped in libgphoto2 `e8f0a839`

- Format every denominator-1 whole-second value as lossless `MM:SS`:
  `23 -> 00:23`, `60 -> 01:00`, `70 -> 01:10`, and `110 -> 01:50`.
- Parse `MM:SS` back to the original total seconds, while retaining input
  compatibility for the old `30s`, `1m`, and `1m10s` spellings.
- Preserve and parse the complete pre-capture Pentax conditions frame before
  `InitiateCapture`, so a reported 70 s timer establishes a 101 s total wait
  budget (exposure plus processing margin) even when post-initiate reads are
  busy or incomplete.
- Remove the fixed five-condition-read abort.  Transient busy/short reads now
  retry until the already bounded capture budget expires; this cannot hang
  indefinitely and no longer makes the Bulb limit depend on read timing.

Regression coverage includes 23, 59, 60, 61, 110, 119, 120, and 121 seconds,
round-tripping both display and parser values.  The libgphoto2 deterministic
pack passed 14/14 tests.  The patcher/package gate passed 3 checks with one
documented skip because the clean release clone has no stock zip in its
working tree.

## Candidate

Candidate `o-v15g-bulb-duration-20261002-r1` / build id
`6.0.0.54.50-o-v15g-bulb-duration` was built from libgphoto2 `e8f0a839` and
patcher `465a5ca`, uploaded to PrivateResearch, and installed via the complete
extracted SD-tree flow.  Post-boot provenance and Stage-2 runtime loading
matched the registry row.  The camera USB was not present after reboot, so this
is still not a physical camera qualification: a real 70 s Bulb capture remains
to be performed.
