/* SPDX-License-Identifier: MIT
 *
 * Pure planning core for the reference SLOW rate ladder.  See the header for
 * the safety boundary: this file is not a motor driver and has no wire path.
 */
#include "polaris-rate-plan.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

/* Measured on the public donor project on 2026-09-26.  These are deliberately
 * named reference values: they must be re-measured on the target firmware and
 * payload before a product controller can use them. */
static const double SLOW_DPS[5][2] = {
    { 0.0059, 0.0119 },
    { 0.0179, 0.0295 },
    { 0.0474, 0.0593 },
    { 0.0896, 0.1193 },
    { 0.2088, 0.2402 }
};

typedef struct {
    double dps;
    int key;
    int state;
} rung_t;

static int fail(char *err, size_t cap, const char *message) {
    if (err && cap) snprintf(err, cap, "%s", message);
    return -1;
}

static int reject(char *err, size_t cap, const char *message) {
    if (err && cap) snprintf(err, cap, "%s", message);
    return -2;
}

static void point_from_rung(polaris_rate_point_t *point, rung_t rung, int level) {
    point->dps = rung.dps;
    point->key = rung.key;
    point->state = rung.state;
    point->level = level;
}

static void make_ladder(int level, rung_t out[4]) {
    double state1 = SLOW_DPS[level - 1][0];
    double state2 = SLOW_DPS[level - 1][1];
    /* Sorted ascending.  State 1/2 are speed rungs, not holds. */
    out[0] = (rung_t){ -state2, 1, 2 };
    out[1] = (rung_t){ -state1, 1, 1 };
    out[2] = (rung_t){  state1, 0, 1 };
    out[3] = (rung_t){  state2, 0, 2 };
}

static void bracket(double target, int level,
                    polaris_rate_point_t *low,
                    polaris_rate_point_t *high,
                    double *duty_high) {
    rung_t ladder[4];
    int i;
    make_ladder(level, ladder);

    if (target <= ladder[0].dps) {
        point_from_rung(low, ladder[0], level);
        point_from_rung(high, ladder[0], level);
        *duty_high = 1.0;
        return;
    }
    for (i = 1; i < 4; i++) {
        if (target <= ladder[i].dps) {
            point_from_rung(low, ladder[i - 1], level);
            point_from_rung(high, ladder[i], level);
            *duty_high = (target - low->dps) / (high->dps - low->dps);
            if (*duty_high < 0.0) *duty_high = 0.0;
            if (*duty_high > 1.0) *duty_high = 1.0;
            return;
        }
    }
    point_from_rung(low, ladder[3], level);
    point_from_rung(high, ladder[3], level);
    *duty_high = 1.0;
}

int polaris_rate_plan(const double target_dps[POLARIS_RATE_AXES],
                      const int hold[POLARIS_RATE_AXES],
                      polaris_rate_plan_t *out,
                      char *err, size_t errcap) {
    int level = 0;
    int i;

    if (!target_dps || !hold || !out)
        return fail(err, errcap, "rate plan argument is null");

    memset(out, 0, sizeof *out);
    for (i = 0; i < POLARIS_RATE_AXES; i++) {
        if (!isfinite(target_dps[i]))
            return fail(err, errcap, "rate must be finite");
        if (hold[i] != 0 && hold[i] != 1)
            return fail(err, errcap, "hold must be 0 or 1");
        if (target_dps[i] != 0.0 || hold[i]) {
            double magnitude = fabs(target_dps[i]);
            int candidate;
            for (candidate = 1; candidate <= 5; candidate++) {
                if (magnitude <= SLOW_DPS[candidate - 1][1]) {
                    if (level == 0 || candidate > level) level = candidate;
                    break;
                }
            }
            if (candidate > 5)
                return reject(err, errcap, "rate exceeds reference SLOW envelope");
        }
    }

    out->common_level = level;
    for (i = 0; i < POLARIS_RATE_AXES; i++) {
        polaris_rate_axis_plan_t *axis = &out->axis[i];
        double target = target_dps[i];

        if (target == 0.0 && !hold[i]) {
            axis->mode = POLARIS_RATE_STOP;
            continue;
        }

        axis->mode = POLARIS_RATE_SLOW;
        if (target == 0.0) {
            /* An engaged zero-rate axis must retain torque.  The balanced
             * state:1 pair averages to zero without using state:0. */
            bracket(0.0, level, &axis->low, &axis->high, &axis->duty_high);
        } else {
            bracket(target, level, &axis->low, &axis->high, &axis->duty_high);
        }
    }
    return 0;
}
