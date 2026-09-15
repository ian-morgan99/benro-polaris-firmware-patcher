# Pentax camera lifecycle testability requirement

New capture/session/recovery code should expose enough deterministic state to test lifecycle transitions without relying on UI interpretation.

Where practical:

- name lifecycle phases explicitly;
- emit capture IDs and transition events;
- make command arbitration outcomes observable;
- expose candidate reconciliation terminal state;
- expose recovery reason/escalation level;
- keep timing expectations configurable/testable rather than hidden magic constants.

This does not require a new public API. Structured internal observability is sufficient, provided the hardware harness can consume it.
