/* SPDX-License-Identifier: MIT
 *
 * polaris-rate-scheduler — offline clock-driven scheduler for a rate plan.
 *
 * This is still a pure core.  It emits logical SLOW points and an explicit
 * logical STOP; it does not turn them into wire frames and has no link or
 * motor side effect.  The wire adapter must prove the target stop semantics
 * before it can consume RATE_SCHED_STOP.
 */
#ifndef POLARIS_RATE_SCHEDULER_H
#define POLARIS_RATE_SCHEDULER_H

#include "polaris-rate-plan.h"

#define POLARIS_RATE_MIN_DWELL_S 0.075
#define POLARIS_RATE_CYCLE_S     0.25
#define POLARIS_RATE_REVERSE_CYCLE_S 0.50

typedef enum {
    POLARIS_RATE_SCHED_STOP = 0,
    POLARIS_RATE_SCHED_SLOW = 1
} polaris_rate_schedule_kind_t;

typedef struct {
    int axis;
    polaris_rate_schedule_kind_t kind;
    polaris_rate_point_t point; /* valid for SLOW; last point is retained for diagnostics */
} polaris_rate_schedule_command_t;

typedef struct {
    polaris_rate_plan_t plan;
    polaris_rate_point_t active[POLARIS_RATE_AXES];
    double last_switch_s[POLARIS_RATE_AXES];
    double cycle_start_s[POLARIS_RATE_AXES];
    int active_valid[POLARIS_RATE_AXES];
    int stop_sent[POLARIS_RATE_AXES];
    int have_plan;
} polaris_rate_scheduler_t;

void polaris_rate_scheduler_init(polaris_rate_scheduler_t *scheduler);

/* Replace the desired plan. `now_s` is monotonic scheduler time. */
void polaris_rate_scheduler_set_plan(polaris_rate_scheduler_t *scheduler,
                                      const polaris_rate_plan_t *plan,
                                      double now_s);

/*
 * Emit commands whose state is due at now_s.  The caller owns `out`.
 * Returns the number of logical commands written, or -1 for invalid output.
 * The result is bounded by POLARIS_RATE_AXES.
 */
int polaris_rate_scheduler_tick(polaris_rate_scheduler_t *scheduler,
                                 double now_s,
                                 polaris_rate_schedule_command_t *out,
                                 int cap);

#endif /* POLARIS_RATE_SCHEDULER_H */
