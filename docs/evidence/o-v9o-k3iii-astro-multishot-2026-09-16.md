# o-v9o K-3 III ordinary-capture gate before astro multi-shot

Date: 2026-09-16 20:24 UTC (device log clock: 21:24 UTC)

## Scope

The intended test was a bounded simulation of an Astro multiple-shooting
workload: three ordinary captures, preview off, ten seconds between completed
captures. Repository policy requires one ordinary capture to reach capture
states `1 -> 4 -> 2 -> 3 -> 5` before progressing to multiple shots. The run
therefore stopped after the baseline failed that progression gate.

No firmware was installed or modified. No process was stopped or restarted.

## Preflight

- Route: `192.168.0.1 dev wlp8s0 src 192.168.0.4`.
- Device identity: `/app/FwVer` reported stock base `4.0.0.32`.
- Installed candidate: o-v9o, build ID `6.0.0.54.6` per the existing roadmap.
- Camera: Pentax K-3 III, USB `25fb:0189`.
- Camera init: `sp_Gphoto_Init ret 0`; camera info state 1.
- Runtime: `polestar_app` and `pgphoto.stage2ondisk` alive; 8080/9090 listening.
- Two other established 9090 clients were present after the test
  (`192.168.0.4:49390` and `192.168.0.2:49283`). This was not a single-client
  qualification run.
- Preview initially defaulted ON after connection. Before the capture gate it
  was stopped with code 291 (`state:0;ret:0`) and confirmed off with code 292.
- Before preview was stopped, a valid 67,006-byte preview frame had completed
  and the USB/runtime remained stable. This is a useful preview-on stability
  observation, but it is not a preview soak qualification.

## Baseline command

```bash
python3 scripts/test-astro-multishot.py --execute --shots 1
```

The script performed the `284 -> 820 -> 823` session handshake, confirmed
preview off, and sent the live-qualified capture frame:

```text
1&264&4&state:1;bulb:0;c:-1;#
```

## Observed result

Wire events:

```text
264@state:1
264@state:4
773@type:1;path:/app/sd/normal/SP_0042.dng;size:28198130;...
775@status:1;totalspace:121866;freespace:120264;usespace:1602;
264@state:0
```

The file exists on the Polaris SD card with the reported size:

```text
-rwxr-xr-x 1 root root 28198130 Sep 16 21:24 /app/sd/normal/SP_0042.dng
```

For the remainder of the bounded 120-second window, mode state remained idle
(`284@mode:1;state:0`). The camera stayed on USB and the control stream remained
active. Capture states 2, 3, and 5 never arrived.

The kernel ring buffer contained 1,871 occurrences of the known Broadcom
`No more free tdata_psh_info!!` / `Out of tdata_disc_grp` signatures. The count
did not increase during a five-second post-test sample, so this proves prior
pool exhaustion during the current boot but does not timestamp it to this one
capture. With two other control clients present, it prevents this run from
being labelled a clean single-client radio qualification.

## Verdict

**Ordinary exposure/file creation: PASS.** The shutter ran and a 28,198,130-byte
DNG was recorded.

**o-v9o ordinary-capture lifecycle gate: FAIL/INCOMPLETE.** The required
candidate/transfer/reconciliation terminal sequence did not reach state 5.

**Astro multi-shot simulation: NOT RUN.** Starting more exposures after this
result would violate the explicit o-v9o progression gate and could recreate a
pending-candidate lifecycle fault. The next run must also close or explicitly
isolate the two other 9090 clients. The investigation must explain why a
durable DNG plus state 0 replaced the expected states 2/3/5, or formally update
the completion contract with evidence before repeating captures.

## Reproduction tooling

See `scripts/test-astro-multishot.py` and `docs/ASTRO-MULTISHOT-TEST.md`. The
script fails closed without `--execute`, forces preview off, maintains one
authenticated socket, stops on a negative state or timeout, and will not begin
the next shot until the previous shot satisfies the full configured lifecycle.
