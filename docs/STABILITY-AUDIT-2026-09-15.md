# Stability audit and simulation review — 2026-09-15

## Scope and evidence boundary

This audit reviewed `main`, all local/remote Git history, fault-oriented shell
tests, Stage-2 loader simulation hooks, packaging gates, and recorded K-1 II / K-3
III evidence. It did not access or mutate a live Polaris and did not build,
stage, or install a new FwPkt.

Simulation establishes deterministic state-machine and lifecycle behaviour. It
does not establish radio, camera, or firmware qualification. QEMU
`container/selftest.sh` proves only camlib loading/model registration; it cannot
exercise USB capture or the Broadcom Wi-Fi driver.

## Historical findings reviewed

| History | Finding | Audit conclusion and action |
|---|---|---|
| `ba269df`, `0258654` on `upstream/astro-plate-solving` | Closed-loop simulation exposed a narrow solve hint, clock-error cancellation, unreachable network simulator, and perfect tracking that never exercised guiding. | Valid for the separate unmerged astro stack. Those product files do not exist on `main`; do not import an unrelated subsystem. Retain the rule: inject non-ideal state and drive real command paths. |
| `2802572` on that branch | High-rate `bcmdhd` diagnostics mirrored to a 115200-baud console; reducing console loglevel avoided an observed TCP-starvation amplifier. | Plausible containment, but not proof that printk caused the driver-pool failure. Port reversibly at pgphoto startup, preserve `dmesg`, and allow opt-out. |
| `5d6b59f`, `b7b93a3`, `a0ade5e` on `main` | Owner-bearing launch locks, exit-safe backoff, and restart-side stale-lock recovery. | Ownership was still inferred from PID existence in two paths, while the restart lock was never reclaimed. Fix executable identity checks and simulate PID reuse. |
| `1b021e9` on `main` | Debounced restart after stable camera USB identity change. | Its singleton lock also trusted PID existence. Validate the owner executable and simulate PID reuse. |
| `446fbfd`, `de98a23`, `3964701` on `main` | Non-blocking Pentax preview rate gate/cooldown, later counting all failures. | Appropriate load avoidance, but it does not bound independent unsupported-property polling and is not a driver fix. Retained unchanged. |

## Changes enacted

1. `pgphoto.wrapper.in` verifies that launch-lock and PID-file owners are the
   exact configured `pgphoto.stage2ondisk` executable. An unrelated live PID is
   reclaimed as stale ownership.
2. `restart_gphoto.sh` validates restart-lock ownership and reclaims dead or
   PID-reused locks. A genuine concurrent restart remains fail-closed.
3. `camera_usb_supervisor.sh` validates its singleton owner rather than treating
   any live PID as the supervisor.
4. At pgphoto startup, console loglevel is lowered to 1 by default when writable.
   This limits serial-console amplification while retaining ring-buffer evidence.
   `OPENPOLARIS_PRINTK_QUIET=0` restores stock behaviour;
   `OPENPOLARIS_PRINTK_PATH` supports deterministic tests.

## Simulations and regression results

- Dead launch-lock owner: reclaimed; pgphoto launches.
- Live unrelated launch-lock owner (PID reuse): reclaimed; pgphoto launches.
- Exact live Stage-2 owner: preserved; duplicate refused.
- TERM during crash-loop backoff: exit 143; no PID publication or late launch.
- Console containment: fake sysctl changes to 1; opt-out preserves its value.
- Stable USB identity: no restart; debounced address change: exactly one restart.
- Live unrelated USB-supervisor lock owner: reclaimed.
- Dead and PID-reused restart-lock owners: reclaimed; restart succeeds.
- Fail-closed package fixtures still reject malformed/missing manifests,
  duplicate archive members, and bad top-level layout.

## Remaining qualification work

These changes are source- and simulator-qualified only. Before calling the radio
symptom fixed, build and register a FwPkt, install through the supported SD flow,
cold boot, then:

1. prove AP/route/FwVer, runtime hashes, loaded libraries, and active clients;
2. record printk state and baseline `bcmdhd` counters/message rate;
3. test one control client plus one deliberate preview stream;
4. run labelled, bounded multi-client stress with recovery checks;
5. repeat qualified Canon R5 Mark II, Pentax K-3 III, and Pentax K-1 II paths;
6. distinguish fewer console stalls from continued pool exhaustion. A responsive
   device with recurring pool errors is mitigated, not repaired.
