# Pentax stability change review checklist

Before accepting an agent patch, check:

- Does it address a proven first divergence or merely hide a later symptom?
- Does it add/retain a regression reproducer?
- Does it preserve long-exposure/NR/Pixel Shift/Bulb semantics?
- Does it avoid assuming candidate count from mode/exposure count?
- Does it preserve DNG/user data?
- Does it serialize camera ownership deterministically?
- Does it distinguish transport failure from elapsed-time expectation?
- Does it avoid unbounded retries/restart storms?
- Does it improve structured observability?
- Does it preserve FwPkt/reproducible firmware delivery rather than relying on direct SSH mutation for the product fix?
- Has it been tested below OpenPolaris first, then requalified E2E where appropriate?
