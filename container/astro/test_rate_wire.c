/* SPDX-License-Identifier: MIT
 *
 * Host-only tests for the dry-run SLOW wire adapter. No socket or motor
 * command is involved.
 *
 *   cc -O2 -std=gnu11 -Wall -Wextra -Werror polaris-rate-plan.c \
 *      polaris-rate-scheduler.c polaris-rate-wire.c test_rate_wire.c \
 *      -o test_rate_wire -lm && ./test_rate_wire
 */
#include "polaris-rate-wire.h"

#include <stdio.h>
#include <string.h>

static int fails;

static void ok(int condition, const char *what) {
    printf("%s  %s\n", condition ? "ok  " : "FAIL", what);
    if (!condition) fails++;
}

static polaris_rate_schedule_command_t command(int axis,
                                                polaris_rate_schedule_kind_t kind,
                                                int key, int state, int level) {
    polaris_rate_schedule_command_t out;
    out.axis = axis;
    out.kind = kind;
    out.point.dps = 0.01;
    out.point.key = key;
    out.point.state = state;
    out.point.level = level;
    return out;
}

int main(void) {
    polaris_rate_wire_frame_t frame;
    polaris_rate_schedule_command_t cmd;
    polaris_rate_plan_t plan;
    polaris_rate_scheduler_t scheduler;
    polaris_rate_schedule_command_t commands[POLARIS_RATE_AXES];
    char err[96];
    double target[POLARIS_RATE_AXES] = { 360.0 / 86164.1, 0.0, -0.00402 };
    int hold[POLARIS_RATE_AXES] = { 1, 1, 1 };
    int n, i;

    cmd = command(0, POLARIS_RATE_SCHED_SLOW, 0, 1, 1);
    ok(polaris_rate_wire_encode(&cmd, &frame, err, sizeof err) == 0,
       "positive pan SLOW command encodes");
    ok(frame.opcode == 532 && frame.type == 3 &&
       strcmp(frame.args, "key:0;state:1;level:1;") == 0,
       "pan maps to 532 with the existing SLOW payload");

    cmd = command(1, POLARIS_RATE_SCHED_SLOW, 1, 2, 4);
    ok(polaris_rate_wire_encode(&cmd, &frame, err, sizeof err) == 0 &&
       frame.opcode == 533 &&
       strcmp(frame.args, "key:1;state:2;level:4;") == 0,
       "negative tilt maps to 533 with direction and rung preserved");

    cmd = command(2, POLARIS_RATE_SCHED_STOP, 0, 2, 2);
    ok(polaris_rate_wire_encode(&cmd, &frame, err, sizeof err) == 0 &&
       frame.opcode == 534 &&
       strcmp(frame.args, "key:0;state:0;level:2;") == 0,
       "rotation STOP releases the previously active SLOW point");

    cmd = command(0, POLARIS_RATE_SCHED_STOP, 0, 0, 1);
    ok(polaris_rate_wire_encode(&cmd, &frame, err, sizeof err) == -1,
       "STOP without a prior active point is rejected");
    cmd = command(3, POLARIS_RATE_SCHED_SLOW, 0, 1, 1);
    ok(polaris_rate_wire_encode(&cmd, &frame, err, sizeof err) == -1,
       "unknown axis is rejected");
    cmd = command(0, POLARIS_RATE_SCHED_SLOW, 0, 0, 1);
    ok(polaris_rate_wire_encode(&cmd, &frame, err, sizeof err) == -1,
       "state zero is rejected as a SLOW run point");

    ok(polaris_rate_plan(target, hold, &plan, err, sizeof err) == 0,
       "scheduler plan can feed the wire adapter");
    polaris_rate_scheduler_init(&scheduler);
    polaris_rate_scheduler_set_plan(&scheduler, &plan, 0.0);
    n = polaris_rate_scheduler_tick(&scheduler, 0.0, commands, 3);
    ok(n == 3, "initial scheduler tick produces all three logical commands");
    for (i = 0; i < n; i++) {
        ok(polaris_rate_wire_encode(&commands[i], &frame, err, sizeof err) == 0,
           "scheduler SLOW command encodes without a live link");
        ok(frame.opcode >= 532 && frame.opcode <= 534 && frame.type == 3,
           "encoded scheduler command uses the known app-control family");
    }

    printf("\n%s (%d failure%s)\n", fails ? "FAILED" : "PASSED", fails,
           fails == 1 ? "" : "s");
    return fails ? 1 : 0;
}
