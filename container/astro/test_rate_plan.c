/* SPDX-License-Identifier: MIT
 *
 * Host-only tests for the pure rate planner.  This test never opens a socket
 * or talks to a Polaris head.
 *
 *   cc -O2 -std=gnu11 -Wall -Wextra -Werror polaris-rate-plan.c \
 *      test_rate_plan.c -o test_rate_plan -lm && ./test_rate_plan
 */
#include "polaris-rate-plan.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

static int fails;

static void ok(int condition, const char *what) {
    printf("%s  %s\n", condition ? "ok  " : "FAIL", what);
    if (!condition) fails++;
}

static void assert_pair(const polaris_rate_axis_plan_t *axis,
                        double target, const char *what) {
    double average = axis->low.dps + axis->duty_high *
                     (axis->high.dps - axis->low.dps);
    ok(axis->mode == POLARIS_RATE_SLOW, what);
    ok(fabs(average - target) < 1e-12, "duty cycle reproduces requested average");
    ok(axis->low.level == axis->high.level, "pair uses one common level");
    ok(axis->low.state != 0 && axis->high.state != 0,
       "slow pair never releases torque");
}

int main(void) {
    polaris_rate_plan_t plan;
    char err[96];
    double sidereal = 360.0 / 86164.1;
    double target[POLARIS_RATE_AXES] = { sidereal, 0.0, -0.00402 };
    int hold[POLARIS_RATE_AXES] = { 1, 1, 1 };

    ok(polaris_rate_plan(target, hold, &plan, err, sizeof err) == 0,
       "plans a three-axis tracking request");
    ok(plan.common_level == 1, "low-rate tracking stays on reference level 1");
    assert_pair(&plan.axis[0], sidereal, "M1 is represented by a SLOW pair");
    assert_pair(&plan.axis[1], 0.0, "M2 zero-rate hold is represented by a pair");
    assert_pair(&plan.axis[2], -0.00402, "M3 is independent of M1 and M2");
    ok(plan.axis[1].low.state == 1 && plan.axis[1].high.state == 1,
       "zero-rate hold uses state 1 in both directions");

    target[0] = 0.2;
    target[1] = 0.0;
    target[2] = 0.0;
    hold[1] = 0;
    hold[2] = 0;
    ok(polaris_rate_plan(target, hold, &plan, err, sizeof err) == 0,
       "plans a higher slow rate with stopped idle axes");
    ok(plan.common_level == 5, "shared level follows the fastest slow axis");
    assert_pair(&plan.axis[0], 0.2, "higher rate is bracketed on level 5");
    ok(plan.axis[1].mode == POLARIS_RATE_STOP &&
       plan.axis[2].mode == POLARIS_RATE_STOP,
       "non-holding zero axes are explicit stops");

    target[0] = 0.3;
    ok(polaris_rate_plan(target, hold, &plan, err, sizeof err) == -2,
       "rate above the reference SLOW envelope is rejected");
    target[0] = NAN;
    ok(polaris_rate_plan(target, hold, &plan, err, sizeof err) == -1,
       "non-finite rate is rejected");

    memset(target, 0, sizeof target);
    hold[0] = 2;
    ok(polaris_rate_plan(target, hold, &plan, err, sizeof err) == -1,
       "invalid hold flag is rejected");

    printf("\n%s (%d failure%s)\n", fails ? "FAILED" : "PASSED", fails,
           fails == 1 ? "" : "s");
    return fails ? 1 : 0;
}
