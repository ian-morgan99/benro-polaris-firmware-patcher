# K-1 II control failures — offline re-analysis of `Clog_000276.txt`

Source: `docs/evidence/benro-connect-crash-20261010/raw/Clog_000276.txt`, 12,710 lines.
**Firmware caveat:** this log is `6.0.0.54.65` / `o-v16g-k3iii-timed-bulb-20261010`. It is the newest
K-1 II log in the repo, not `.69` or `.70`. Nothing here is re-tested on current firmware.

## What #232 asserts, and what the log actually shows

#232 presents `0xd02b` / `0xd035` as a static descriptor-parsing defect. The same two codes parse
**successfully five times** earlier in the same session:

```
[14:21:00:394] code=0xd02b; datatype=0x0002; getset=1; form=2; enum-count=3; value-bytes=2
[21:43:01:633] code=0xd02b; datatype=0x0002; getset=1; form=2; enum-count=3; value-bytes=2
... 21:43:09, 21:43:33, 21:43:41 — all OK
[21:44:46:960] code=0xd02b; descriptor-parse=failed; descriptor-bytes=16; descriptor-hex=2bd00440010000020200000040024001
[21:45:08:690] ... failed   [21:47:36:643] ... failed   [21:51:03:759] ... failed
```

Identical pattern for `0xd035`. A decoder that cannot parse a descriptor cannot parse it five times
and then fail four — so the defect is not "the parser rejects this shape".

## The failures are gated on camera state, and only on these two codes

Every widget dump line carries `state=N`. Bucketing all 76 `code=0x…` lines by nearest preceding state:

| code | state=0 | state=3 |
|---|---|---|
| `0x5005` `0x5007` `0x5008` `0x5010` `0xd00f` `0xd013` `0xd01e` | OK, never fail | **OK, never fail** (28 lines) |
| `0xd02b` | OK ×5 | **FAIL ×4** |
| `0xd035` | OK ×5 | **FAIL ×4** |

At `state=3`, 28 descriptor parses succeed and exactly these two fail. So it is neither a
session-wide breakage (which re-init would suggest) nor a static shape defect (which #232 suggests).
It is specific to `0xd02b`/`0xd035` **and** correlated with `state=3`.

I could not resolve what `state=3` means. `scripts/wait-for-rig.py` documents only `state=1` as
usable and `state=-5` / `state=-2` for absent/unready bodies; `3` is not defined anywhere in the
repo. Naming it would be a guess, so I am not naming it.

## The failing payloads are malformed against DPDS

Decoded offline with the standard DPDS layout (Min u16, Max u16, FormFlag u8, DataType u16, Access u8):

- `0xd035`, 6 bytes `35d0 0000 0000` — **shorter than the 8-byte DPDS header minimum**. Cannot parse,
  for a reason that has nothing to do with Pentax semantics.
- `0xd02b`, 16 bytes `2bd0 0440 01 0000 02 02000000 4002 4001` — parses as `Min=0xd02b Max=0x4004
  FormFlag=1 DataType=0x0000 Access=2`. `DataType=0x0000` is not a valid PTP datatype, and the OK-case
  for the same code reports `datatype=0x0002 form=2`. The bytes are not the descriptor the camera
  returns when it answers normally.

So in the failing state the camera (or the layer above it) is returning truncated/garbage payloads
for these two properties, and the parse failure is a *symptom* of that, not the cause.

## #233 shares this root cause — confirmed, not hypothesised

#233 asks whether EV readback failures share a cause with #232. Bucketing `exposurecompensation ret`
by nearest preceding state gives an exact split with no exceptions:

```
EV ret= 0  nearest-state=0     (14:21:01, 21:43:11)
EV ret=-1  nearest-state=3     (all 11 occurrences, 21:45:51 onward)
```

Same for the rest of the cluster:

| symptom | state=0 | state=3 |
|---|---|---|
| `whitebalance ret` | 2 OK | 11 fail |
| `imageformat ret` | 3 OK | 6 fail |
| `configuration entry shutterspeed` write fail | 0 | 4 |
| `configuration entry capturetarget` write fail | 3 | 1 |

Everything except `capturetarget` tracks state exactly. #232, #233 and the readback half of #235 are
**one state-gated failure mode**, not three independent defects. Filing them separately — and
especially treating `descriptor-parse=failed` as the root cause — inverts the causality: the parse
failure and the `ret -1` readbacks are both downstream of whatever `state=3` does to PTP responses.

## #234 — TA's error-code correction is right, verified in the headers

`libgphoto2_port/gphoto2/gphoto2-port-result.h`:

```c
#define GP_ERROR_BAD_PARAMETERS  -2
#define GP_ERROR_NOT_SUPPORTED   -6
```

So `updateCameraAutoFocus ret:-2` is **BAD_PARAMETERS**, exactly as TA said. It is not a
capability/unsupported signal, and #234's framing of it as an AF-enable failure is not supported by
the code.

## #234 — one thing I could not resolve, stated rather than guessed

TA asked whether the firmware demonstrably inverts the `enable` parameter. In pgphoto
(`updateCameraAutoFocus`, `gpManager.c:3631-3706`, vaddr `0x102fa0`) the argument is stored at
`[fp,#-0x50]` and read back four times. Two of those reads feed writes with **opposite polarity**:

```
0x103150  gpManager.c:3680   ldr r3,[fp,#-0x50]; cmp r3,#0; moveq r3,#1; movne r3,#0   -> value = !enable
0x103178  gpManager.c:3681   bl #0x42a3c          (write)
0x103188  gpManager.c:3683   bne <end>            skip next write if the first returned non-zero
0x10318c  gpManager.c:3687   ldr r3,[fp,#-0x50]; cmp r3,#0; movne r3,#1; moveq r3,#0   -> value = enable
0x1031b4  gpManager.c:3688   bl #0x42a3c          (write)
```

Both writes pass the same `[fp,#-0x20]` as their first argument, and the first is guarded by
`cmp r3,#4` on `[fp,#-0x24]` at line 3676. I could **not** resolve `[fp,#-0x20]` to a config-entry
name — the literal pool entries I dereferenced came back as code pointers, not strings — and I
could **not** identify what `[fp,#-0x24]` holds either, so `cmp r3,#4` is recorded as an unlabelled
guard rather than characterised as a datatype test. Consequently I cannot say whether these are two
different properties (in which case the polarity difference is legitimate) or the same property
written twice with opposite values (which would be a real bug).

**I am not claiming an inversion.** TA's condition was "unless the firmware implementation
demonstrably inverts that parameter", and I have not demonstrated it. This is flagged as unresolved.

## What this changes about the issue set

- **#232** should stop treating descriptor parsing as the root cause. The actionable question is what
  `state=3` does to PTP responses for these two properties, and whether an unparseable descriptor
  should surface as "unsupported" instead of silently dropping the control — TA's point 3 stands and
  is still the best available fix.
- **#233** is not a separate write-path bug; it is the same state-gated readback failure. Fixing the
  write path alone would leave EV missing, which is exactly the conflation TA warned about.
- **#234** should be retitled per TA to *focus unqualified / initialization disable returned -2*.
- **#235** — TA's correction holds: `SP_SET_SHUTTER FAIL` ×4 does not prove the following
  `bulb:0` frame is a fallback, and `bulb:0` may be the held-shutter form. I did not verify the
  `264` handler's `bulb==0` branch; that needs hardware.
- **#217** remains accurate: no K-1 II qualification evidence exists on any build since `.65`, and
  this analysis is offline log work, not qualification.

## Limits of this analysis

Single session, single boot, `.65` firmware, ~9 widget dumps total at `state=3`. The state
correlation is exact within that sample but the sample is small, and nothing here has been reproduced
on `.69` or `.70`. Resolving `state=3`, the config-entry names above, and the `264` handler all need
a K-1 II attached — the rig currently reports `state:-5`.
