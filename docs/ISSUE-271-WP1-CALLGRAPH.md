# Issue #271 — WP1 (in progress): call graph, verified against source

Started after WP0 (`docs/ISSUE-271-WP0-BASELINE.md`). This records what has been
**verified by reading the code at `f3b1164`**, and separates that from what is still
outstanding. It is not a complete WP1: the JSON fixtures, full failure-exit inventory
and BenroConnect opcode-sequence comparison are not done (see §4).

Every line reference below was opened and read; nothing is quoted from #271's table.

## 1. Four 527 senders, in two implementations that share no code

The heading-correction command `1&527&3&compass:…` is emitted from four places:

| Site | Command | Waits for a reply / readback? |
|---|---|---|
| `polaris-mount.c:871` | `align --solved-ra/--solved-dec` | **no** |
| `polaris-mount.c:684` | `set-compass --az` | **no** — prints `{"compass_set_az_deg":…}` straight after `conn_send` |
| `polaris-autosolve.sh:756` | `apply_correction()` | no |
| `polaris-autosolve.sh:797` | verification pass in the same function | no |

`polaris-httpd.c` invokes `align` at lines 1879, 2136 and 4832. `autosolve.sh` bypasses
the binary entirely and writes to the mount socket itself via `mount_send`. So the same
correction can be issued by the web API *and* by the autosolve loop with neither knowing
about the other — WP8's "single motion owner" is not theoretical, these paths are
concurrent by construction.

**`star-align` is the counter-example, and it matters for WP4.** It sends 530 (not 527),
and unlike `align` it *does* verify: after both `step:1` and `step:2` it sends `1&284&2&-1#`,
waits with `wait_for(&c, "284", …, 400)`, and reports `aligned` from the mount's own
`track` field (`track:3` means not aligned). So a working readback pattern already exists
in this file — `align` simply doesn't use it. That makes #271 finding 1 a gap against an
existing in-repo precedent, not an absent capability.

Note the two commands disagree about what "aligned" means: `star-align` derives it from
mount state, `align` asserts it unconditionally. A caller cannot treat the two JSON
outputs as equivalent, though both carry an `aligned` key.

## 2. #271 finding 1 confirmed exactly: `align` reports success it has not verified

`polaris-mount.c`, the `align` branch:

```c
snprintf(msg, sizeof(msg), "1&527&3&compass:%.5f;lat:%.5f;lng:%.5f;#", ...);
conn_send(&c, msg);
printf("{\"aligned\":true,\"mount_alt_deg\":%.6f,...}");
conn_close(&c); return 0;
```

`conn_send` then `printf("aligned":true)` with **no `wait_for` afterwards**. Compare
`goto`, which does wait: lines 746 and 749 call `wait_for(&c, "519", …, 4000)` and
`…, 20000)`, and handle a missing reply with `{"goto":false,"error":"no 519 reply"}`
and exit 5. So the codebase already knows how to await an acknowledgement — `align`
just doesn't use it.

This matches #271's wording precisely ("sends 527 and immediately reports `aligned:true`
without verified acknowledgement/readback"). The distinction it asks for — `sent` /
`acknowledged` / `applied` / `verified` — currently collapses to `sent`, reported as
`aligned`.

**Caveat worth resolving before WP4:** whether a 527 *reply exists at all* is unknown.
`goto` has one; `align` may be fire-and-forget by protocol design. #271 says explicitly
not to assume a 527 ACK until the target protocol is traced, and that tracing needs the
MCU/firmware identity that WP0 could not obtain (F2). So "add an ACK" may not be
implementable as stated.

## 3. `dalt` computed and discarded — confirmed

```c
daz  = fmod(s_az - p_az + 540.0, 360.0) - 180.0;
dalt = s_alt - p_alt;
snprintf(msg, ..., "1&527&3&compass:%.5f;lat:%.5f;lng:%.5f;#", ...);   /* az only */
printf("... \"az_error_deg\":%.6f,\"alt_error_deg\":%.6f ...", daz, dalt, ...);
```

`dalt` is calculated and printed in the JSON but never sent — 527 carries `compass`
only. So pitch/altitude error is *reported* and then dropped, exactly as #271 states.
Any caller that reads `alt_error_deg` and assumes it was corrected would be wrong;
nothing in the output distinguishes "measured" from "acted on".

## 4. A false lead I checked and rejected

`align` contains:

```c
if (!arg_get(args, "compass", v, sizeof(v))) p_az = atof(v);
if (!arg_get(args, "alt",     v, sizeof(v))) p_alt = -atof(v);
```

Read casually this looks inverted — assigning the parsed value when the lookup
*failed*. It isn't: `arg_get` returns **0 on success** and `-1` when the key is absent
(`polaris-mount.c:281-299`). So `!arg_get(...)` means "found it", and the code is
correct. Recorded here so nobody re-reports it, and because the convention is easy to
misread — a success-returns-zero parser used inside `if (!…)` twice in a row.

Also checked: `solve_frame` is defined in `polaris-autosolve.sh:298`, not only in the
dormant `polaris-autoalign.sh:193`. An earlier grep with a truncated result set made it
look like autosolve called an undefined function. It does not.

## 5. Zenith guard — already present, and good

`align` refuses to correct above `g_max_align_alt`, returning exit 6 with
`error_amplification = 1/cos(alt)`. That is a real safety property worth preserving in
WP4 rather than re-deriving: near the zenith, heading error amplification explodes, so
a solve there is actively harmful to apply.

## 6. Sign convention — consistent across both paths (WP4 dependency)

The mount's `compass` field is 180° out from the azimuth used internally, and both
implementations apply the same transform:

- `polaris-mount.c:684` (`set-compass`): `fmod(az - 180.0 + 360.0, 360.0)`, with the
  comment *"the mount's 'compass' is 180 deg out from the azimuth we reason in"*.
- `polaris-autosolve.sh:477` (`compass_for_solve`): `c=a-180; while(c<0)c+=360;
  while(c>=360)c-=360`.

`align` (line 871) reaches the same result differently — it computes
`p_az + daz` where `daz = wrap(s_az - p_az)` and then applies
`fmod(fmod(x,360) - 180 + 360, 360)`, i.e. the −180 offset plus a positive wrap. So all
three agree on the offset; `align` additionally wraps into [0,360) rather than leaving a
signed value.

**Not verified:** whether −180 is the *correct* offset for this firmware. The comment
says it was captured from the phone app on real hardware, but that capture predates this
session and no MCU/firmware identity is available (WP0/F2). WP4 must re-confirm against
BenroConnect before trusting it — a wrong sign here produces a correction that doubles
the pointing error instead of halving it, which is precisely the "confidently wrong
alignment" the script's own header warns about.

## 7. Gate asymmetry: the web API can apply corrections autosolve would refuse

`compass_for_solve` has two refusals before it emits a heading:

1. **Zenith cap** — refuses above `MAX_ALIGN_ALT`, because azimuth error amplification
   is `1/cos(alt)` and the axis is ill-conditioned near the zenith.
2. **Uncertainty-vs-correction ratio** (`MAX_UNCERT_FRAC`, default **0.25**) — refuses
   when the azimuth uncertainty exceeds a quarter of the correction, i.e. when the
   heading "would not be a clear improvement on leaving it alone".

`polaris-mount.c::align` implements only the zenith cap (exit 6). It has **no
uncertainty gate**. So `/api/astro/*` paths that call `align` (httpd lines 1879, 2136,
4832) will send a heading correction that the autosolve loop would deliberately decline.

This is the concrete instance of #271's "bounded correction" requirement: the bound
exists in one implementation and not the other. WP4 should put the ratio check into
`align` so both paths share it, rather than leaving the safer logic in shell only.

Two smaller observations from the same reading, recorded but **not** treated as defects:

- `compass_for_solve` solves against the **frame's own epoch** when available and logs
  how far the sky moved since (`lag × 15.041″/s`). That is correct behaviour and worth
  preserving — #271 asks for exposure-midpoint timestamps, and this already does the
  time-corrected conversion.
- `apply_correction` is called with 5 arguments at line 678 (frame epoch supplied) but
  with only 4 at line 632 (the `STUB_FRAME` path), so `_fep` is empty there and
  `compass_for_solve` falls back to `utc_now`. For a stub frame that means solving
  against the current time rather than the frame's. It affects the test path only, not
  live capture — but it is exactly the class of bug WP2's normalised contract (an
  explicit `exposure_mid_unix_s`, never defaulted) is meant to prevent.

## 8. Still outstanding for WP1

- **JSON fixtures** for each function's inputs/outputs — not written.
- **Complete failure-exit inventory** across the shell paths (only the C exits are
  mapped above).
- **BenroConnect opcode-sequence verification** against target firmware — blocked by
  WP0/F2, no MCU version obtainable via `getOmsFwInfo.sh` / `getFwInfo.sh`.
- **The 530 calibration handshake's state transitions.** `handle_arm` (601) reads the
  armed yaw/pitch, converts to a solve hint, and calls `apply_correction`, which ends by
  sending `530 step:2` and then `start_guiding`. Whether completing that handshake while
  the app's own dialog is open is safe — #271's specific question — is **not answered**.
- **`good_solve`'s acceptance thresholds** (`autosolve.sh:333`) not yet compared against
  WP2's proposed `validate_solve` parameters.

## 9. What this does not establish

Source reading only. No command was sent, no reply observed, no hardware involved —
the camera was absent throughout. Nothing here qualifies pointing accuracy or tracking
performance, and §2's conclusion is about what the code *reports*, not about what the
mount actually did.
