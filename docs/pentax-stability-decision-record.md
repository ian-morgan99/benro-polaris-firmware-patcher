# Decision record: Pentax/Polaris stability investigation

## Decisions

1. **Investigate initiating failures before optimising recovery.** Recovery is required, but a successful reset is not evidence that the original defect is understood.
2. **Do not use OpenPolaris for first-cause isolation.** Use the real Polaris pgphoto/staged-libgphoto2 path with minimal upper-layer variables. Reintroduce OpenPolaris for E2E qualification after lower layers are stable.
3. **Do not use requested shutter duration as a capture timeout.** Pentax mode matters; NR, Pixel Shift, processing and Bulb can legitimately extend operation.
4. **Do not infer output/candidate count from physical exposure count.** Pixel Shift may consolidate multiple physical exposures into DNG/JPEG outputs. Enumerate actual descriptors.
5. **Treat camera state, process state and transport health as separate signals.** USB presence alone does not prove a healthy PTP lifecycle; elapsed time alone does not prove failure.
6. **Serialise camera ownership deterministically.** Preview/config/focus/status must not race capture merely because another subsystem polls.
7. **Cluster evidence by first abnormal event.** `session already open`, stale ports, NoUpdateImage, -1005 and reboot requirements are common aftermath until proven otherwise.
8. **Preserve user image data.** Candidate reconciliation must not blindly delete DNGs to make the next shutter work.
9. **Prefer fresh process replacement when in-process teardown cannot be proven clean.** Full Polaris reboot remains last resort.
10. **Convert every reproduced failure into a permanent regression test.**

## Rationale

Current evidence suggests multiple defects can compound: incomplete candidate finalisation, stale in-process session/port state, preview/concurrency pressure and potentially mode-unaware timeout behaviour. A single 'recovery' patch risks masking the initiating bug and making future failures harder to diagnose.
