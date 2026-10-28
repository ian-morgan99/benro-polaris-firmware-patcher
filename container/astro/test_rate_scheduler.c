/* SPDX-License-Identifier: MIT
 *
 * Host-only tests for the pure rate scheduler.  No socket or motor command is
 * involved; STOP is tested as a logical event only.
 *
 *   cc -O2 -std=gnu11 -Wall -Wextra -Werror polaris-rate-plan.c \
 *      polaris-rate-scheduler.c test_rate_scheduler.c -o test_rate_scheduler -lm \
 *      && ./test_rate_scheduler
 */
#include "polaris-rate-scheduler.h"

#include <math.h>
#include <stdio.h>

static int fails;

static void ok(int condition, const char *what) {
    printf("%s  %s\n", condition ? "ok  " : "FAIL", what);
    if (!condition) fails++;
}

static int find_axis(const polaris_rate_schedule_command_t *commands,
                     int count, int axis) {
    int i;
    for (i = 0; i < count; i++)
        if (commands[i].axis == axis) return i;
    return -1;
}

int main(void) {
    polaris_rate_plan_t plan;
    polaris_rate_scheduler_t scheduler;
    polaris_rate_schedule_command_t command[POLARIS_RATE_AXES];
    char err[96];
    double target[POLARIS_RATE_AXES] = { 360.0 / 86164.1, 0.0, -0.00402 };
    int hold[POLARIS_RATE_AXES] = { 1, 1, 1 };
    int n, i;

    ok(polaris_rate_plan(target, hold, &plan, err, sizeof err) == 0,
       "scheduler accepts a reference three-axis plan");
    polaris_rate_scheduler_init(&scheduler);
    polaris_rate_scheduler_set_plan(&scheduler, &plan, 0.0);

    n = polaris_rate_scheduler_tick(&scheduler, 0.0, command, 3);
    ok(n == 3, "initial tick starts all three axes");
    for (i = 0; i < n; i++)
        ok(command[i].kind == POLARIS_RATE_SCHED_SLOW &&
           command[i].point.state != 0,
           "initial output contains only torque-preserving SLOW points");

    n = polaris_rate_scheduler_tick(&scheduler, 0.05, command, 3);
    ok(n == 0, "minimum dwell prevents a premature transition");
    n = polaris_rate_scheduler_tick(&scheduler, 0.25, command, 3);
    ok(n >= 1, "the low-rate PWM phase eventually transitions");
    i = find_axis(command, n, 1);
    ok(i >= 0 && command[i].kind == POLARIS_RATE_SCHED_SLOW &&
       command[i].point.state == 1 && command[i].point.key == 1,
       "zero-rate hold changes to the opposite state-1 direction");
    ok(n <= 3, "one tick cannot emit more than one command per axis");

    for (i = 0; i < POLARIS_RATE_AXES; i++) {
        target[i] = 0.0;
        hold[i] = 0;
    }
    ok(polaris_rate_plan(target, hold, &plan, err, sizeof err) == 0,
       "planner creates a logical stop plan");
    polaris_rate_scheduler_set_plan(&scheduler, &plan, 1.0);
    n = polaris_rate_scheduler_tick(&scheduler, 1.0, command, 3);
    ok(n == 3, "stop plan emits one logical stop per axis");
    for (i = 0; i < n; i++)
        ok(command[i].kind == POLARIS_RATE_SCHED_STOP,
           "stop plan emits STOP events, not a guessed SLOW state");
    n = polaris_rate_scheduler_tick(&scheduler, 1.1, command, 3);
    ok(n == 0, "stop event is not repeated without a new plan");

    printf("\n%s (%d failure%s)\n", fails ? "FAILED" : "PASSED", fails,
           fails == 1 ? "" : "s");
    return fails ? 1 : 0;
}
