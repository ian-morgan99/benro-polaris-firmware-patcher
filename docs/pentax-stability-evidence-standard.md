# Pentax stability evidence standard

Use these confidence levels when making causal claims:

- **Observed** — present in one trace/log but causality unknown.
- **Correlated** — repeatedly appears with the failure, ordering known.
- **Discriminated** — A/B or controlled injection changes the outcome while other variables are held stable.
- **Source-linked** — first divergence maps to a specific code path/action.
- **Proven fix** — pre-fix reproducer fails, post-fix regression passes repeatedly and adjacent baselines remain healthy.

Do not promote a hypothesis directly from observed to proven because it sounds architecturally plausible.
