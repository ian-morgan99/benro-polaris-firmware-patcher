# Next agent prompt — Pentax causal stability campaign

You have access to the physical Polaris + Pentax test environment.

Read, in order:

1. `docs/pentax-stability-index.md`
2. `docs/pentax-stability-decision-record.md`
3. `docs/pentax-capture-stability-experiments.md`
4. `docs/pentax-stability-agent-handoff.md`
5. `docs/pentax-mode-aware-liveness.md`

Then inspect the existing pgphoto/stage2/libgphoto2 source and identify the least-invasive way to add the structured events in `docs/pentax-stability-implementation-notes.md`.

Before modifying runtime behaviour, run/verify the repository-side test scaffolding and make the initial non-destructive scenario catalogue executable against the real Polaris pgphoto path.

Start E4/E5 first. The immediate question is whether an apparently successful DNG+JPEG capture returns host completion while a second Pentax transfer candidate still belongs to that exposure and poisons the next shutter.

Then run E1 around 100 seconds. The immediate question is whether any fixed timeout/watchdog action is the **first** divergence while the camera remains legitimately active.

Do not use OpenPolaris for first-cause isolation. Do not change recovery policy until the first abnormal transition is captured. Do not delete unknown DNG candidates. Do not classify elapsed time alone as camera failure.

Post results to the focused source issue where ownership becomes clear and cross-reference #82. Use `docs/pentax-stability-results-template.md`.
