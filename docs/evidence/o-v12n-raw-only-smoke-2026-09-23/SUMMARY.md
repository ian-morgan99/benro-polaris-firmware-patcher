# o-v12n RAW-only camera smoke test (re-run, 2026-09-23)

Device: Polaris `polaris_d13e86` (BSSID `48:E7:DA:D4:B5:73`, route via wlp8s0),
firmware `6.0.0.54.23-o-v12n-companion-ownership`. Camera: Pentax K-3 III
(USB `25fb:0189`). User set the camera to **RAW only** (not RAW+JPEG) before
this run.

## Procedure

- Pre-state recorded (`pre-state.txt`): pgphoto PID 4789, USB `25fb:0189`
  present, no fatal signatures in Clog.
- Ran `scripts/canary-probe.py --shot` (handshake on 9090, camera state read,
  preview confirmed OFF, exactly one code-264 capture, lifecycle watch).
  Full transcript: `canary-shot.txt`.

## Result: PASS (single-shot RAW-only canary)

- Camera state before shot: `state:1;storage:2`, model `pentax k-3 mark iii`.
  Note: the camera-info field reported `photoFormat:2` even though the user had
  set RAW only — the published file set (one DNG, no JPEG companion) is the
  authoritative observation of the actual mode.
- Preview was already OFF (`292 -> state:0`) before the shutter.
- Capture lifecycle: `state:1` (ack) -> `state:4` (complete) -> `state:0`
  (idle), ~4 s total.
- Exactly one file event: `773 type:1 path:/app/sd/normal/SP_0074.dng
  size:32900659` — a single DNG, **no JPEG companion**, consistent with the
  user's RAW-only setting. File verified on SD: `SP_0074.dng`, 32,900,659
  bytes, 23:34.
- Post-shot health: pgphoto PID unchanged (4789 before and after), USB
  `25fb:0189` still on the bus, no SIGSEGV/fatal/`state:-10`/`0x02ff`/`0x02fa`
  signatures in Clog.

## Caveats

- The Clog contains 62 historical `dlopen core ok` init cycles (868 lines);
  these predate this run. pgphoto PID 4789 was stable across the shot itself,
  so no restart loop was active during the canary.
- `Mlog.txt` was truncated at 23:36 (post-shot), so the code-264/773 events
  are evidenced by the 9090 transcript and the SD file, not Mlog.
- This is a single-shot smoke test only. It does not yet qualify shot two,
  consecutive RAW-only captures, or the full promotion matrix.
