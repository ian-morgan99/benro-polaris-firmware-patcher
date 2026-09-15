# Pentax stability causal failure chain

Represent each mature failure as:

```text
preconditions
  -> trigger
  -> FIRST INCORRECT TRANSITION
  -> contaminated camera/session/process state
  -> high-level symptom(s)
  -> recovery action
```

Engineering priority is to fix as far left as possible. Recovery hardening addresses the right side and remains valuable, but must not substitute for eliminating a preventable trigger/transition.
