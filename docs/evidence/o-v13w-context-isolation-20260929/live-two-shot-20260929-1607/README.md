# o-v13w RAW+JPEG repeatability test — 2026-09-29

## Result

The instrumented two-shot canary passed on installed FwVer `6.0.0.54.42`.
Before capture, Polaris identified Pentax K-3 Mark III `25fb:0189`, reported
`state=1`, `photoFormat=2`, and the test was explicitly configured to require
two files per exposure. After capture, a read-only probe still reported
`state=1`; pgphoto and polestar_app were running, and all four files existed.

| Shot | Lifecycle | Published outputs | Result |
|---|---|---|---|
| 1 | `[1,4,0]` | `SP_0135.dng` (34,199,072 B), `SP_0135.jpg` (385,111 B) | PASS |
| 2 | `[1,4,0]` | `SP_0136.dng` (34,222,707 B), `SP_0136.jpg` (385,434 B) | PASS |

Each output arrived through code 773, followed by idle plus output-obligation
confirmation. No further shutter was sent after the two-shot sequence.

## Connection stability evidence

The boot kernel log contains one Pentax USB reset followed by a disconnect and
re-enumeration (`1-1.2`, device 3 to device 4). At the time the diagnostic
bundle was collected, the camera was enumerated, and five read-only Polaris
probes all returned `state=1`. A separate 5-minute read-only USB/process watch
was started to determine whether additional disconnects occur; its result is
recorded as an addendum when complete. Thus the two-shot capture path passed,
but the user's report of intermittent USB disappearance is not yet dismissed.

## Provenance and transcripts

- Candidate: `o-v13w-context-isolation-20260929`, FwVer `6.0.0.54.42`.
- libgphoto2: `fbc2e7e6544efc93cc708a1e7d2fdf2b2bf7c7cd`.
- Patcher build source: `aaa557f0764cc029672f63c159e953a9f8a6ee3b`.
- Harness: `0355f6f643ae7c154ea42a2f751d14fa1dbcb135`.
- Gate transcript: [two-shot-transcript.txt](two-shot-transcript.txt), SHA-256
  `b38b4ef553abc1f7ee39b4fa0c5fd29b84a545caa621ba8a6bb1c383c14c4872`.
- Local raw Clog SHA-256:
  `18398ef2aa54d82cef161598333bae98975e83756c89c7f331f6c464b1c1e03a`.
- Local raw Mlog SHA-256:
  `495307f2214fc091e16e29fcbe9047aef1ee2c8558d3180c8cfe3260ebae2f08`.

Raw device logs remain local/ignored. This PASS proves the two tested captures
and output publication on the device; it is not a general soak or all-mode
qualification.

## Preservation location — 2026-10-01

This historical assessment and its complete original raw directory are preserved
in the [verified private working-tree archive](https://github.com/ian-morgan99/PrivateResearch/blob/main/archives/pentax-workspace-convergence/20260930/patcher-main-dirty.tar.gz).
Extract its `docs/evidence/o-v13w-context-isolation-20260929/live-two-shot-20260929-1607/` subtree.
This preservation note does not add a hardware test or change the original
assessment; current qualification is in `docs/HANDOVER-PENTAX-STABILITY-20260930.md`.
