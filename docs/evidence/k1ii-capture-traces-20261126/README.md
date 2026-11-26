# K-1 II capture traces — 2026-11-26

Redacted, correlated log traces for single captures on the patched K-1 II (release
`6.0.0.54.117`, camlib libgphoto2 `f48a05e0` + patcher `e0464f39`). Text only — no images, per
operator directive.

Produced by `scripts/k1ii-capture-trace.py`, which records byte offsets of every log before the
capture, slices only the window it caused, and scrubs credential shapes (`password:`, `securityA:`,
`username:`, `token`) using the same patterns as
`docs/evidence/v117-k1ii-regression-20261125/redact-credentials.py`. It refuses to write if any
pattern survives. Both traces here scanned clean (0 redactions needed — these logs carry no account
material).

## Why two logs

| log | contains | why it matters |
|---|---|---|
| `/app/Clog.txt` + SD-rotated `/app/sd/system/log/Clog_*` | pgphoto internals (`will CAPTURE_IMAGE`, `capture end -N ms`, `get file to buffer`) plus our loader's `[stage2]` and the camlib's `[pentax]` boundary markers | where the invariant ~6.1 s post-candidate wait lives |
| `/app/Mlog.txt` | `SP_MsgFromCamera` (what the camera sent) and `SP_SendMsgToApp` (what the phone received, with payload) | the user-visible timeline — the record of what the app was told and when |

Trap worth recording: the loader writes to the SD-rotated `Clog_*`, **not** `/app/Clog.txt`. Grepping
the latter for `[stage2]` returns zero lines and reads as "no loader activity". Rotation can also
happen mid-capture, which is why the script tracks the three newest rotated files rather than one.

## jpgraw-1s.trace.txt — JPG+RAW, 1 s exposure (shutter index 15)

Total 17.0 s. `state:4` at 11.6 s, file notified at ~17.0 s.

The decisive sequence, from Mlog at 13:31:03:

```
13:31:03.232  MsgFromCamera   state:2;/app/sd/normal/SP_0039.jpg     JPEG published
13:31:03.236  MsgFromCamera   state:3;/app/sd/normal/SP_0039.jpg
13:31:03.237  -> app          code 773  type:1;path:...SP_0039.jpg;size:131483
13:31:03.239  MsgFromCamera   state:5;                                <-- unhandled
13:31:03.239  -> app          code 264  state:0                       reported as success
```

**One file delivered in a JPG+RAW configuration.** The JPEG is announced with `type:1`; no second
`773` and no RAW path appear anywhere in the window. `capture end -15488 ms` followed by
`get file to buffer -11 ms`, so pgphoto's own transfer is 11 ms — the time is not transfer.

**`state:5` is undefined in our code but is NOT dual-format specific.** It arrives from the camera
immediately after publication and we map it to `state:0` (success). It appears in no header, doc, or
script in either repo.

I initially read its presence here as evidence that the camera was signalling a pending second output
while we reported success. **That reading is wrong.** Counting across all 25 retained rotated logs:

```
128 val[state:1;    38 val[state:0;    31 val[state:3;
 31 val[state:4;    30 val[state:2;    30 val[state:5;
```

`state:5` occurs once per capture — the same count as `state:2` (publication) and `state:4` — and
appears in logs from before the dial was set to JPG+RAW (`Clog_000017`, and the JPEG-only M-mode runs
in `Clog_000028–30`). It is a normal lifecycle state emitted on every capture, so it explains nothing
about the missing RAW. Recorded here because the correlation looked decisive at first glance and isn't.

## jpgraw-1s-b.trace.txt — JPG+RAW, 1 s exposure (repeat)

Total 17.7 s. Same shape: `state:4` at 11.6 s, `capture end -15488 ms`, `get file to buffer -11 ms`,
one JPEG (`SP_0040.jpg`, 132630 B), and the same `state:5;` immediately after publication. Reproduced
on a second capture, so this is not a one-off.

## What these traces establish

- JPG+RAW yields exactly one delivered file, on two consecutive captures.
- The camera-side cost of JPG+RAW sits in publication (`state:4` at ~11.6 s vs ~3.8 s pre-`state:4`
  for JPEG-only), not in transfer (11 ms).
- `state:5` follows publication and is treated as terminal success — but it does so on **every**
  capture, in both formats, so it is not evidence about dual-format output.

## What they do not establish

- Why the RAW sibling never reaches a transfer candidate our reconciliation (#73) can see — it logged
  nothing on either capture.
- What `state:5` means. It is emitted once per capture regardless of format and is undefined in our
  code; it is not the dual-format signal I first assumed.
- The cause of the invariant ~6.1 s post-`state:4` wait; these traces bound it but do not explain it.
