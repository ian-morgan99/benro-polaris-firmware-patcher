# Agent reporting rules — Pentax stability

When an agent runs hardware tests, report evidence rather than narrative confidence.

For each batch post:

- exact scenarios run;
- pass/fail counts;
- exact SHAs/build/camera settings;
- first abnormal event for each failed run;
- whether the failure reproduced after returning to baseline (A/B/A);
- trace/log artifact locations;
- focused issue updated/created;
- next smallest experiment that discriminates between remaining hypotheses.

Do not report "fixed" because one capture worked. Require the scenario's repeat count plus a consecutive next-shutter proof.

Do not report "USB issue" unless USB identity/transport evidence diverged before the PTP/application symptom.

Do not report "stale session caused it" unless stale-session evidence is the first divergence rather than state observed after another failure.

Do not hide negative experiments. A stressor that fails to reproduce the bug is valuable discrimination evidence.
