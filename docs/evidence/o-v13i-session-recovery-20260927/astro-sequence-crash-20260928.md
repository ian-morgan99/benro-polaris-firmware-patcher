# Astro sequence crash — 2026-09-28

Installed candidate: `6.0.0.54.34-o-v13j-crash-boundary`.

During a Benro Connect Astro sequence, Stage-2 recorded:

```text
SIGSEGV sig=11 si_addr=pc=0xb2c00090
last checkpoint reached: slots filled
```

The watchdog restarted `pgphoto` (PID changed from 2730 to 4085). The Pentax
re-enumerated as `25fb:0189`; `sp_Gphoto_Init ret 0` and camera state 1 were
then observed. Astro shot 2 was acknowledged (`code 264 state:1`,
`SP_0002.jpg`) and immediately returned `state:-110`.

This confirms a packaged Stage-2/pgphoto active-owner/reinitialisation defect
under Astro scheduling. It is not sufficient to qualify Astro multi-shot.
The persistent crash log preserved the fault boundary as intended. Direct
two-shot canary remains a separate lower-level PASS.
