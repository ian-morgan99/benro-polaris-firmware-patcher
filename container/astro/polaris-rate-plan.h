/* SPDX-License-Identifier: MIT
 *
 * polaris-rate-plan — pure, native-C planning for the qualified SLOW ladder.
 *
 * This module deliberately does not open a socket, call polaris-link, or
 * schedule motor commands.  It turns a requested per-axis average rate into
 * the two adjacent 532/533/534 SLOW points and a duty cycle.  A later runtime
 * must enforce the MCU dwell time, command ownership, watchdog and stop path
 * before it is allowed to consume this plan.
 *
 * The ladder values are reference measurements from the public
 * ogecko/alpaca-benro-polaris project, not a qualification of this target
 * head.  They are therefore kept in this isolated planner and are not wired
 * into the Astro runtime by this change.
 */
#ifndef POLARIS_RATE_PLAN_H
#define POLARIS_RATE_PLAN_H

#include <stddef.h>

#define POLARIS_RATE_AXES 3

typedef enum {
    POLARIS_RATE_STOP = 0,
    POLARIS_RATE_SLOW = 1
} polaris_rate_mode_t;

typedef struct {
    double dps;
    int    key;       /* 0 = positive, 1 = negative on the app wire */
    int    state;     /* 1/2 are speed rungs; 0 is never a SLOW run point */
    int    level;     /* 1..5 */
} polaris_rate_point_t;

typedef struct {
    polaris_rate_mode_t mode;
    polaris_rate_point_t low;
    polaris_rate_point_t high;
    double duty_high; /* average = low + duty_high * (high - low) */
} polaris_rate_axis_plan_t;

typedef struct {
    int common_level; /* 0 when all axes are stopped */
    polaris_rate_axis_plan_t axis[POLARIS_RATE_AXES];
} polaris_rate_plan_t;

/*
 * Plan all three axes atomically.
 *
 * target_dps is a desired average rate.  A zero target with hold[i] true is
 * an engaged zero-rate hold and is represented by a balanced pair of
 * opposite state:1 points.  A zero target with hold[i] false is a STOP and
 * is the only case that produces a stop mode.  No plan contains a SLOW
 * state:0 point.
 *
 * Return values:
 *   0  plan produced
 *  -1  invalid argument or non-finite rate
 *  -2  requested rate is outside the reference SLOW envelope
 */
int polaris_rate_plan(const double target_dps[POLARIS_RATE_AXES],
                      const int hold[POLARIS_RATE_AXES],
                      polaris_rate_plan_t *out,
                      char *err, size_t errcap);

#endif /* POLARIS_RATE_PLAN_H */
