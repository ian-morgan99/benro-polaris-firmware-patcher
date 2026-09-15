# Pentax stability layer attribution

Assign ownership only after locating the first divergence.

1. **Camera/body firmware/state** — direct control also fails with equivalent settings and transport remains healthy.
2. **libgphoto2 Pentax/PTP** — source-level driver state/candidate/condition handling diverges before pgphoto-specific behaviour.
3. **pgphoto** — embedded orchestration, command sequencing or object lifecycle diverges while equivalent direct libgphoto2 control survives.
4. **runtime/stage2/loader** — wrong library/runtime, process environment or staged artifact behaviour is first divergence.
5. **watchdog/supervisor** — automatic timeout/restart/USB logic acts first and incorrectly.
6. **preview/network** — preview loop/radio/8080 pressure acts first.
7. **OpenPolaris/Benro upper layer** — only after lower path is clean and upper-layer request/protocol behaviour introduces divergence.
8. **physical USB/power** — actual detach/flap/power evidence precedes software session failure.

Use `unknown` rather than assigning a convenient layer without evidence.
