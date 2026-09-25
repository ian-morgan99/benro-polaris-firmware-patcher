# Analysis

Notes from reviewing `blaineam/benro-polaris-firmware-patcher` and its `astro-plate-solving` branch. The intent is to capture what the original maintainer has built, what we can learn from it, and what (if anything) we want to pull into our own fork.

These are working notes — they describe upstream as of the commit under review, not a contract.

## Documents

- [`astro-mode-overview.md`](./astro-mode-overview.md) — what blaineam has done since forking, focused on the astro/plate-solving work on the `astro-plate-solving` branch.
- [`astro-mode-architecture.md`](./astro-mode-architecture.md) — where the code lives and the architectural patterns we can learn from it (process boundary, single-connection link layer, server-side dead-man, default-deny opcode allowlist, etc.).
