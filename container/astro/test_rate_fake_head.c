/* SPDX-License-Identifier: MIT
 *
 * Host-only fake-head tests for the scheduler and dry-run wire seam.
 *
 *   cc -O2 -std=gnu11 -Wall -Wextra -Werror polaris-rate-plan.c \
 *      polaris-rate-scheduler.c polaris-rate-wire.c polaris-rate-fake-head.c \
 *      test_rate_fake_head.c -o test_rate_fake_head -lm && ./test_rate_fake_head
 */
#include "polaris-rate-fake-head.h"

#include <stdio.h>
#include <string.h>

static int fails;

static void ok(int condition, const char *what) {
    printf("%s  %s\n", condition ? "ok  " : "FAIL", what);
    if (!condition) fails++;
}

static void apply_all(polaris_rate_fake_head_t *head,
                      polaris_rate_schedule_command_t *commands, int count,
                      double now_s) {
    polaris_rate_wire_frame_t frame;
    char err[96];
    int i;
    for (i = 0; i < count; i++) {
        ok(polaris_rate_wire_encode(&commands[i], &frame, err, sizeof err) == 0,
           "logical command encodes before fake-head delivery");
        ok(polaris_rate_fake_head_apply(head, &frame, now_s) == 0,
           "fake head accepts the encoded command");
    }
}

int main(void) {
    polaris_rate_fake_head_t head;
    polaris_rate_plan_t plan;
    polaris_rate_scheduler_t scheduler;
    polaris_rate_schedule_command_t commands[POLARIS_RATE_AXES];
    polaris_rate_wire_frame_t frame;
    char err[96];
    double target[POLARIS_RATE_AXES] = { 360.0 / 86164.1, 0.0, -0.00402 };
    int hold[POLARIS_RATE_AXES] = { 1, 1, 1 };
    int n, i;

    polaris_rate_fake_head_init(&head, 0.4);
    ok(polaris_rate_plan(target, hold, &plan, err, sizeof err) == 0,
       "reference tracking plan is available to the fake-head test");
    polaris_rate_scheduler_init(&scheduler);
    polaris_rate_scheduler_set_plan(&scheduler, &plan, 0.0);
    n = polaris_rate_scheduler_tick(&scheduler, 0.0, commands, 3);
    ok(n == 3, "initial scheduler output contains every axis");
    apply_all(&head, commands, n, 0.0);
    for (i = 0; i < POLARIS_RATE_AXES; i++)
        ok(head.axis[i].active, "accepted SLOW point leaves the axis active");

    ok(polaris_rate_fake_head_tick(&head, 0.39) == 0,
       "watchdog does not fire before its lease expires");
    ok(polaris_rate_fake_head_tick(&head, 0.41) == 3,
       "watchdog stops every stale axis in the host model");
    for (i = 0; i < POLARIS_RATE_AXES; i++)
        ok(!head.axis[i].active, "watchdog leaves no axis active");

    memset(&frame, 0, sizeof frame);
    frame.opcode = 532;
    frame.type = 3;
    strcpy(frame.args, "key:0;state:1;level:1;");
    ok(polaris_rate_fake_head_apply(&head, &frame, 0.5) == 0,
       "a fresh SLOW point can re-arm an axis after watchdog expiry");
    ok(head.axis[0].active, "fresh SLOW point reactivates the axis");
    strcpy(frame.args, "key:0;state:0;level:1;");
    ok(polaris_rate_fake_head_apply(&head, &frame, 0.6) == 0,
       "explicit STOP is accepted for an active axis");
    ok(!head.axis[0].active, "explicit STOP clears the axis");
    ok(polaris_rate_fake_head_apply(&head, &frame, 0.7) == -1,
       "repeated STOP is rejected instead of silently guessed");

    frame.opcode = 999;
    ok(polaris_rate_fake_head_apply(&head, &frame, 0.8) == -1,
       "unknown opcode is rejected");
    frame.opcode = 532;
    strcpy(frame.args, "key:0;state:1;level:1;extra;");
    ok(polaris_rate_fake_head_apply(&head, &frame, 0.8) == -1,
       "non-canonical payload is rejected");
    frame.type = 2;
    strcpy(frame.args, "key:0;state:1;level:1;");
    ok(polaris_rate_fake_head_apply(&head, &frame, 0.8) == -1,
       "wrong subsystem type is rejected");

    printf("\n%s (%d failure%s)\n", fails ? "FAILED" : "PASSED", fails,
           fails == 1 ? "" : "s");
    return fails ? 1 : 0;
}
