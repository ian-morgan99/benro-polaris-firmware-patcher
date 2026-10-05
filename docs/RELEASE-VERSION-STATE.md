# Polaris display firmware-version release state

Benro Connect must receive the exact five-component version from code 780.
The release builder treats the value below as the last accepted display version
and refuses to build a candidate that is unchanged, lower, from another
version family, or missing the fifth build component.

```text
last_display_fwver=6.0.0.54.55
```

Consumed values that must never be reused:

- `.53` — the withdrawn o-v15p artifact.
- `.54` — o-v15q, which is installed and reports `6.0.0.54.54` on code 780.
- `.55` — o-v15r-supervisor-preload-20261005.

`.54` is the reason `--next` cannot be trusted on its own: the baseline was left
at `.53` when o-v15q was installed, so auto-derivation offered `.54` again, i.e.
a duplicate of a version already running on hardware. This is the failure mode
#169 describes. Until the baseline is advanced in the same commit as every
install, cross-check the derived value against what the device actually reports
(`canary-probe.py --probe --expected-sw <value>`) before building.

When the next candidate is promoted, update this value in the same commit as its
provenance row and release evidence, and keep the consumed list above current.
