# Defect A answered: which pgphoto operation holds the claim

Defect A on v118 was "live view flickers every ~3-4 s, mechanism identified but the
remaining question is why a config read holds the camera for ~4 s at all." That question
was answerable statically and had not been asked. It is now answered.

## Why it was answerable

The gate logs `site=%x` from `__builtin_return_address(0)` at the claim site, so it is a
return address **inside pgphoto**. `pgphoto.stage2ondisk` is a non-PIE ARM `EXEC` (entry
`0x15ed8`), so those addresses are absolute -- no runtime load base to subtract. One
`addr2line` call resolves them to functions.

Addresses are stable across versions: pgphoto md5 `79d4454f…` is identical for v115, v117
and v118, and the three key sites resolve identically against the **v114** binary
(`8789c3bb…`). pgphoto itself is never patched by us, so a site number means the same
function in every build. That is what makes pre-v118 logs comparable to v118 ones.

## The map

| site | function | gpManager.c | kind |
|---|---|---|---|
| `0x100540` | `deal_camera_control_handler` | 2832 | 2 CONFIG / 3 SET |
| `0x1013ac` | `capture_image` | 3059 | 0 CONTROL |
| `0x101b0c` | `capture_image_with_Bulb` | 3195 | 0 CONTROL |
| `0x102cd4` | `updateCameraViewFinder` | 3566 | 0 CONTROL |
| `0x102ff0` | `updateCameraAutoFocus` | 3635 | 0 CONTROL |
| `0x102ba0` | `updateLivePreView` | 3531 | 1 PREVIEW |

`kind` is `enum stage2_camera_operation {CONTROL, PREVIEW, CONFIG, SET}`.

## Answer: the holder is the settings handler, and it contends with itself

375 refusals across `Clog_000020`-`Clog_000039`, 13 distinct site/owner pairs:

```text
170  deal_camera_control_handler wants CONFIG   held by deal_camera_control_handler (CONFIG)
 68  deal_camera_control_handler wants CONFIG   held by capture_image            (CONTROL)
 46  deal_camera_control_handler wants CONFIG   held by capture_image_with_Bulb  (CONTROL)
 25  updateCameraViewFinder      wants CONTROL  held by deal_camera_control_handler (CONFIG)
 23  deal_camera_control_handler wants CONFIG   held by updateCameraViewFinder   (CONTROL)
 16  updateCameraAutoFocus       wants CONTROL  held by deal_camera_control_handler (CONFIG)
 13  deal_camera_control_handler wants SET      held by deal_camera_control_handler (CONFIG)
```

**170 of 375 (45%) are the same function refusing itself** -- `deal_camera_control_handler`
waiting on a claim held by another thread in `deal_camera_control_handler`. That is not
preview/config contention, which is what the gate was designed to arbitrate. It is two
settings requests serialising against each other. The 13 `SET`-vs-`CONFIG` and 7
`CONFIG`-vs-`SET` pairs are the same handler in its write role blocking its read role.

So the flicker cadence is explained by settings traffic queueing behind settings traffic,
with viewfinder and autofocus updates (25 + 16) pushed behind them. The gate is behaving
as designed -- `stolen=0`, depth bounded at 1, every refusal recovers -- and the open
question "why does a config read hold for ~4 s" resolves to: **because another settings
request already holds it.**

## Defect A predates v118 -- but the holder does not

`Clog_000027`-`Clog_000032` carry refusals with **no** `held_ms`/`stolen` fields, i.e.
written by a pre-v118 build. Splitting all 375 lines by format:

```text
v118-format (237)                        pre-v118-format (138)
155  settings(CONFIG) vs settings        68  settings(CONFIG) vs capture_image   (CONTROL)
 22  viewfinder vs settings              46  settings(CONFIG) vs capture_bulb    (CONTROL)
 19  settings vs viewfinder              15  settings(CONFIG) vs settings
 16  autofocus vs settings                4  settings vs viewfinder
 13  settings(SET) vs settings            3  viewfinder vs settings
```

Two things follow, and they are different from what I first wrote here. I claimed the
distributions were "identical shape"; they are not, and the counts that looked equal
(`68`/`46`) were the same lines counted twice because my first regex silently dropped all
138 pre-v118 lines.

**What is the same:** `deal_camera_control_handler` is the refused party in both eras, and
self-contention (`settings vs settings`) exists in both -- 15 occurrences pre-v118. So the
phenomenon of a settings request waiting on another settings request predates v118. The
v118 findings' caution ("do not describe the flicker as introduced by v118 without a
pre-v118 measurement") is satisfied: it was not introduced by v118.

**What differs:** pre-v118, settings were mostly blocked by **capture operations** (114 of
138, 83%). On v118 they are mostly blocked by **other settings requests** (155 of 237,
65%). I cannot attribute that to a firmware change. Those log files cover different
sessions, and the holder distribution tracks what the operator was doing -- shooting
versus browsing settings -- at least as plausibly as it tracks the build. Attributing it
to v118 would need two sessions running the same activity on different builds.

## What this does NOT establish

- **No duration claim for pre-v118.** Those logs have no `held_ms`, so we know the same
  contention existed but not how long claims were held. Do not state that v114 held claims
  for seconds.
- **No version attribution for the shift in holder.** See above -- activity is a live
  confound and the samples are different sessions.
- **No fix proposed.** Whether two settings requests *should* serialise is a pgphoto-side
  design question, and pgphoto is stock and unpatched. The gate is reporting accurately.
- **Defect A is still open.** The mechanism is now named rather than inferred, which is
  what was missing; the flicker itself is unchanged.

## Reproduce

```bash
ssh root@rig 'grep -ah "admission refused" /app/sd/system/log/Clog_*.log' \
  | scripts/decode-stage2-sites.py \
      --binary out/<build>/stage2-ondisk/ondisk/pgphoto.stage2ondisk --summary
```

`scripts/decode-stage2-sites.py` refuses PIE binaries (addresses would be load-base
relative) and accepts `--expect-build-id` so a mismatched binary cannot silently produce
plausible wrong function names.
