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

## 6. Still outstanding for WP1

- **JSON fixtures** for each function's inputs/outputs — not written.
- **Complete failure-exit inventory** across the shell paths (only the C exits are
  mapped above).
- **BenroConnect opcode-sequence verification** against target firmware — blocked by
  WP0/F2, no MCU version obtainable via `getOmsFwInfo.sh` / `getFwInfo.sh`.
- **`handle_arm` (autosolve.sh:601) and the 530 handshake** traced only as far as
  seeing it call `apply_correction`; the state-transition safety question #271 raises
  is not yet answered.
- **`compass_for_solve` (autosolve.sh:423)** sign convention not yet audited — WP4
  depends on it.

## 7. What this does not establish

Source reading only. No command was sent, no reply observed, no hardware involved —
the camera was absent throughout. Nothing here qualifies pointing accuracy or tracking
performance, and §2's conclusion is about what the code *reports*, not about what the
mount actually did.
