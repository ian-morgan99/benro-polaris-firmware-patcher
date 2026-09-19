#ifndef POLARIS_STAGE2_POLICY_H
#define POLARIS_STAGE2_POLICY_H

int stage2_model_uses_r5_shims(const char *model);
/* Pentax models whose preview path benefits from keeping PC live view running
 * across capture-preview calls (issues #36/#55: per-frame d035 teardown +
 * restart re-enters the NoUpdateImage warmup window on every request). */
int stage2_model_uses_pentax_keep_lv(const char *model);
/* K-1 Mark II only: its PC live view is measurably slow (~1 frame / 7-8 s,
 * docs/evidence/k1ii-live-test-2026-09-15), so the on-demand preview gate
 * should default to a longer minimum interval than the generic 2 s. */
int stage2_model_is_k1_mark_ii(const char *model);
#endif
