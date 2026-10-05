# Polaris display firmware-version release state

Benro Connect must receive the exact five-component version from code 780.
The release builder treats the value below as the last accepted display version
and refuses to build a candidate that is unchanged, lower, from another
version family, or missing the fifth build component.

```text
last_display_fwver=6.0.0.54.55
```

The `.53` value was consumed by the withdrawn o-v15p artifact and must not be
reused. When the next candidate is promoted, update this value in the same
commit as its provenance row and release evidence. The next permitted display
version after the current baseline is `6.0.0.54.54`.
