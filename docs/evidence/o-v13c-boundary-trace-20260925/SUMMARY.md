# o-v13c boundary-trace candidate

Status: **INSTALLED; RUNTIME-VERIFIED; K-3 III TWO-SHOT CANARY PASS**

o-v13b proved that direct-to-core Stage-2 dispatch alone does not restore the
first shutter: after a clean `state=1` start and confirmed preview stop, one
code-264 request received `state:1` but no completion/773; the session became
`state:-10` 31 seconds later. No second shutter was sent.

The remaining unobserved interval contains the core entry, mandatory Pentax
conditions read and Pentax InitiateCapture. o-v13c changes no capture policy or
timing. It emits unconditional stderr checkpoints at:

- generic `gp_camera_capture` entry;
- Pentax camlib entry with transfer/recovery state;
- pre-capture conditions enter and return (PTP result and size);
- InitiateCapture enter (focus/output obligation) and return (PTP result).

## Provenance and artifact

- patcher: `8b075f50d36f6b6f0ba3c0815b7c8478fdbc60f4`
- libgphoto2: `4868d3649b4a363679ea7ed9d695fbd153063827`
- harness: `a8b65817354dae04f997d1357d7d4914e396c42f`
- build id: `6.0.0.54.27-o-v13c-boundary-trace`
- zip MD5: `afd320066ddac3d5df62069b44e2afb9`
- zip SHA-256: `ff5a3be41e776b781c7fce004761f09e6a52e6c2c57a8bf4122a6f29b8ed8333`
- appfs MD5: `954934c8146b8bba1a40dfad3cb47c62`
- appfs SHA-256: `3f84195d7bc337ac3a458cbbd36642697fd98a9235b42c46ab9a141bdc537ef9`
- private artifact commit: `d92b1d094`

## Gates

- libgphoto2 focused tests: 2/2 PASS
- patcher offline/package: 12 container + 15 Python + structural PASS
- harness: 62/62 PASS
- build verified all six firmwareInfo entries and required every checkpoint
- package stock-manifest subgate skipped because the clean worktree has no
  stock bytes

## Installed and physical evidence

The sanctioned complete-tree update installed o-v13c and a cold reboot proved
FwVer, embedded provenance, all matched-stack runtime hashes, and pgphoto maps
loading the intended `/app/lib/stage2` core and port libraries. The trace
markers were present in the installed core and ptp2 camlib.

The first bounded K-3 III canary passed and published both DNG and JPEG. Its
trace reached generic core entry, Pentax camlib entry, conditions return
`0x2001`, and InitiateCapture return `0x2001`.

The original two-shot gate then stopped after shot 1 despite receiving
`[1,4,0]`, DNG and JPEG. It had two test defects: completion was evaluated
only on state frames, and it assumed exactly one output despite
`photoFormat:2` (RAW+JPEG). No second shutter was sent in that red run.

The corrected fail-closed gate models the two-output obligation, accepts event
ordering only when state 4, idle state 0, and same-stem DNG+JPEG are all seen,
and rejects stale paths. Four deterministic regressions pass. The live rerun
passed two captures in one unchanged session with no reconnect:

- shot 1: `[1,4,0]`, `SP_0086.dng` + `SP_0086.jpg`;
- shot 2: `[1,4,0]`, `SP_0087.dng` + `SP_0087.jpg`;
- offline gate: 12 container + 19 Python PASS;
- live gate: probe + two-shot PASS, 0 failures, 0 skips.

The full protocol transcript is `two-shot-20260925.txt`. This answers the
minimum physical acceptance question for this observed RAW+JPEG path: the next
ordinary shutter was issued only after exposure completion, both owned outputs
were published, and the prior operation reported idle. Broader body/mode,
cancellation, Live View interaction and soak qualification remain separate.
