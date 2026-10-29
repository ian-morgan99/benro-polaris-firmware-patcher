/* SPDX-License-Identifier: MIT
 *
 * Host-only fake-head model for the known application SLOW path.
 *
 * This is a safety-test model, not a claim about the target MCU. Its watchdog
 * is the host-side lease policy we intend to require before live enablement.
 */
#ifndef POLARIS_RATE_FAKE_HEAD_H
#define POLARIS_RATE_FAKE_HEAD_H

#include "polaris-rate-wire.h"

#define POLARIS_RATE_FAKE_HEAD_WATCHDOG_S 0.400

typedef struct {
    int active;
    int key;
    int state;
    int level;
    double last_update_s;
} polaris_rate_fake_axis_t;

typedef struct {
    polaris_rate_fake_axis_t axis[POLARIS_RATE_AXES];
    double watchdog_s;
} polaris_rate_fake_head_t;

void polaris_rate_fake_head_init(polaris_rate_fake_head_t *head,
                                  double watchdog_s);

/* Apply one encoded frame at monotonic `now_s`. Return 0 if accepted. */
int polaris_rate_fake_head_apply(polaris_rate_fake_head_t *head,
                                 const polaris_rate_wire_frame_t *frame,
                                 double now_s);

/* Host-side watchdog stop. Returns the number of axes stopped. */
int polaris_rate_fake_head_tick(polaris_rate_fake_head_t *head,
                                double now_s);

#endif /* POLARIS_RATE_FAKE_HEAD_H */
