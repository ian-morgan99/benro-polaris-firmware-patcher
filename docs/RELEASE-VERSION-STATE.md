# Polaris display firmware-version release state

Benro Connect must receive the exact five-component version from code 780.
The release builder treats the value below as the last accepted display version
and refuses to build a candidate that is unchanged, lower, from another
version family, or missing the fifth build component.

```text
last_display_fwver=6.0.0.54.55
```

## Consumed-version registry (authoritative)

Every display version ever issued is listed below. `verify_display_fwver_monotonic.py`
reads these lines and refuses to hand out any of them again, **regardless of what
`last_display_fwver` says**. The list is append-only: never delete or edit an
entry, only add one when a candidate is claimed.

```text
consumed_display_fwver=6.0.0.54.53
consumed_display_fwver=6.0.0.54.54
consumed_display_fwver=6.0.0.54.55
```

| Version | Candidate | Notes |
| --- | --- | --- |
| `.53` | o-v15p | withdrawn artifact |
| `.54` | o-v15q | installed; reported `6.0.0.54.54` on code 780 |
| `.55` | o-v15r-supervisor-preload-20261005 | installed 2026-10-05; reports `6.0.0.54.55` |

## Why the registry exists (#169)

`.54` is the failure case: the baseline was left at `.53` when o-v15q was
installed, so `--next` derived `.54` again — a duplicate of a version already
running on hardware. A single mutable baseline cannot detect that, because the
information "`.54` was used" was not recorded anywhere the tool read.

`--next` now derives from `max(baseline, registry) + 1` and then skips anything
already in the registry, so a stale baseline can no longer produce a duplicate.
`--record` advances the baseline **and** appends to the registry in one step, so
the two cannot drift apart during a release.

Keep the human cross-check anyway — it is a secondary defence, not the primary
one: confirm the derived value against what the device actually reports
(`canary-probe.py --probe --expected-sw <value>`) before building.

When the next candidate is promoted, let `--record` update both entries in the
same commit as its provenance row and release evidence.
