# Pentax stability experiment result

## Provenance

- Experiment:
- Run IDs:
- Camera/body:
- Camera firmware:
- **Attachment: PC / POLARIS**
- **Layer: A / B / C**
- **Actual software path:**
- Observed USB identity:
- Patcher SHA (if applicable):
- libgphoto2 SHA:
- Polaris firmware/build (Layer C):
- Lens:
- App/upper layer present: none / Benro Connect / OpenPolaris
- Preview: on/off + cadence

`Camera + Attachment + Layer + Actual software path` are mandatory. A result without these is not sufficient evidence for layer attribution.

## Physical setup / transitions

- Initial host:
- Was a physical cable move required?:
- Agent instruction issued:
- New-host enumeration verified?:
- Any physical recovery action during/after run:

Do not combine multiple recovery actions into one entry. Record camera power-cycle, USB reconnect, USB Compatibility change, pgphoto restart and Polaris reboot independently.

## Camera configuration

- Exposure mode:
- Requested shutter:
- Image format:
- NR:
- Pixel Shift:
- Other relevant settings:

## Reproduction

Exact deterministic steps/commands.

## Expected lifecycle

State what was expected, distinguishing expected duration from authoritative completion.

## First abnormal event

- Monotonic timestamp:
- Lifecycle phase:
- Active command:
- Camera/PTP condition:
- Candidate state/descriptors:
- pgphoto PID/process state:
- USB fingerprint/state:
- Concurrent request if any:

## Later symptoms

List separately. Do not rewrite these as root cause.

## Recovery required

- none / session reset / pgphoto restart / USB reconnect / camera power cycle / Polaris reboot

## Reproducibility

- failures / runs:
- baseline/stressor/baseline result:

## A/B/C differential

- Layer A direct result:
- Layer B Benro-compatible PC result:
- Layer C Polaris result:
- Earliest layer reproducing:
- Lower layer known clean?: yes / no / not testable

## Layer attribution

Camera / Pentax libgphoto2 / pgphoto / runtime-loader / watchdog-supervisor / preview-network / upper layer / unknown.

## Source hypothesis

Exact source path/functions where possible, with evidence.

## Deterministic fix

No LLM/heuristic runtime control.

## Regression test

How this failure recipe will be permanently exercised and at which layer(s).

## Evidence

Trace artifact, Mlog/Clog for Polaris runs, relevant excerpts and cross-referenced issues.
