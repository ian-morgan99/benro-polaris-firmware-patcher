# The data that differs in Bulb non-timed: an EMPTY shutter list

Derived from the already-captured corpus in this directory (60 MB, including the
rotated `system-log/` series). No new capture was required.

## The differing data

`Clog` dumps the Pentax descriptor widgets. The **Shutter/Bulb Descriptor** is the
one that changes in non-timed B:

```
Label: Pentax Shutter/Bulb Descriptor
Current: code=0xd00f; datatype=0x0008; getset=1; form=2; enum-count=0; value-bytes...
```

`enum-count=0` — the shutter list is empty. Every other Pentax descriptor in the
same dump has a real count (Aperture 19, ISO 15, White Balance 17, Drive Mode 12,
PC Live View 2).

Corpus-wide the shutter descriptor is `enum-count=0` in 21 dumps and 46/55/56 in
the rest. Empty in exactly four logs: `Clog_000267`, `Clog_000269`, `Clog_000274`,
`Clog_000276`.

## Why it is empty: the camera offers no JPEG

```
MsgFromCamera-->type[1],code[282],val[format:0;]
camera img format:0
camera format no include jpg        <-- ERROR
```

`format:0` = no JPEG output. In B mode the body offers no JPEG stream, and the
shutter/Bulb descriptor the app reads comes back with zero entries.

| log | `camera img format:0` | shutter enum-count |
|---|---|---|
| 255, 256, 257, 271, 272, 273 | 0–5 | 55 |
| 262, 264, 265, 266 | 0–3 | 46 |
| **267, 269** | 1 | **0** |
| **274** | 13 | **0** then 55/56 |
| **276** | 11 | **0** then 56 |

`camera format no include jpg` appears only in the four logs with the empty list.

## The transition (Clog_000276)

```
14:21:00  shutter enum-count=0     <- in B, untimed
21:43:01  shutter enum-count=0
21:43:09  shutter enum-count=0
21:43:33  shutter enum-count=0
21:43:41  shutter enum-count=0
21:44:46  shutter enum-count=56    <- dial leaves B: list repopulates
21:44:47  *** pgphoto is exit, reboot it ***
```

## What the device forwards to the app

The empty list reaches the app as a well-formed-looking payload:

```
code[268],val[RD:0;V:0;R:00:00,;]
```

65 occurrences — the only degenerate payload among 693 shutter-list replies. It
looks like a valid one-entry list whose single entry is the bogus `00:00`, rather
than an empty list.

## Candidate fixes (both on our side)

1. **Device side:** when the camera reports no JPEG, forward an explicitly empty
   shutter list rather than `RD:0;V:0;R:00:00,;`.
2. **Library side:** when the shutter/Bulb descriptor parses to zero entries,
   refuse the Bulb action cleanly (as the timed path already does with `-6`)
   instead of letting the app proceed with a list it cannot use.

## Limits

- **Proven:** the empty list is specific to the no-JPEG/B state and precedes the
  exits.
- **Inferred:** that it is what the app crashes on. Benro Connect is closed and no
  captured log has an app-side stack, so the app's faulting instruction cannot be
  proven from device logs.
- `pgphoto is exit` also occurs in logs with a populated list (255, 257, 259, 271,
  273), so pgphoto exiting is not unique to this state. The empty list is the part
  unique to it.
