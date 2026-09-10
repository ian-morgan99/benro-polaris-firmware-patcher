#ifndef POLARIS_STAGE2_POLICY_H
#define POLARIS_STAGE2_POLICY_H

int stage2_model_uses_r5_shims(const char *model);
/* Pentax models whose preview path benefits from keeping PC live view running
 * across capture-preview calls (issues #36/#55: per-frame d035 teardown +
 * restart re-enters the NoUpdateImage warmup window on every request). */
int stage2_model_uses_pentax_keep_lv(const char *model);
#endif
