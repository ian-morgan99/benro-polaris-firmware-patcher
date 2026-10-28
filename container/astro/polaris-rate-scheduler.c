/* SPDX-License-Identifier: MIT
 *
 * Pure clock-driven scheduler for the reference SLOW rate plan.  There is no
 * socket, process control, or command serialization in this file.
 */
#include "polaris-rate-scheduler.h"

#include <math.h>
#include <string.h>

static int same_point(const polaris_rate_point_t *a,
                      const polaris_rate_point_t *b) {
    return a->key == b->key && a->state == b->state && a->level == b->level;
}

static double cycle_for(const polaris_rate_axis_plan_t *axis) {
    return axis->low.dps < 0.0 && axis->high.dps > 0.0
        ? POLARIS_RATE_REVERSE_CYCLE_S
        : POLARIS_RATE_CYCLE_S;
}

static polaris_rate_point_t point_for_phase(const polaris_rate_axis_plan_t *axis,
                                            double now_s,
                                            double cycle_start_s) {
    double cycle = cycle_for(axis);
    double phase = fmod(now_s - cycle_start_s, cycle);
    double high_s;
    if (phase < 0.0) phase += cycle;
    high_s = axis->duty_high * cycle;
    return phase < high_s ? axis->high : axis->low;
}

void polaris_rate_scheduler_init(polaris_rate_scheduler_t *scheduler) {
    if (scheduler) memset(scheduler, 0, sizeof *scheduler);
}

void polaris_rate_scheduler_set_plan(polaris_rate_scheduler_t *scheduler,
                                      const polaris_rate_plan_t *plan,
                                      double now_s) {
    int axis;
    if (!scheduler || !plan || !isfinite(now_s)) return;
    scheduler->plan = *plan;
    scheduler->have_plan = 1;
    for (axis = 0; axis < POLARIS_RATE_AXES; axis++) {
        scheduler->cycle_start_s[axis] = now_s;
        scheduler->stop_sent[axis] = 0;
    }
}

int polaris_rate_scheduler_tick(polaris_rate_scheduler_t *scheduler,
                                 double now_s,
                                 polaris_rate_schedule_command_t *out,
                                 int cap) {
    int axis;
    int count = 0;

    if (!scheduler || !out || cap < POLARIS_RATE_AXES ||
        !scheduler->have_plan || !isfinite(now_s)) return -1;

    for (axis = 0; axis < POLARIS_RATE_AXES; axis++) {
        const polaris_rate_axis_plan_t *want = &scheduler->plan.axis[axis];
        polaris_rate_schedule_command_t *command;
        polaris_rate_point_t desired;
        double since_switch;

        if (want->mode == POLARIS_RATE_STOP) {
            if (scheduler->stop_sent[axis]) continue;
            command = &out[count++];
            command->axis = axis;
            command->kind = POLARIS_RATE_SCHED_STOP;
            if (scheduler->active_valid[axis])
                command->point = scheduler->active[axis];
            else
                memset(&command->point, 0, sizeof command->point);
            scheduler->active_valid[axis] = 0;
            scheduler->stop_sent[axis] = 1;
            continue;
        }

        scheduler->stop_sent[axis] = 0;
        desired = point_for_phase(want, now_s, scheduler->cycle_start_s[axis]);
        since_switch = scheduler->active_valid[axis]
            ? now_s - scheduler->last_switch_s[axis]
            : POLARIS_RATE_MIN_DWELL_S;

        if (scheduler->active_valid[axis] &&
            same_point(&desired, &scheduler->active[axis]))
            continue;
        if (since_switch < POLARIS_RATE_MIN_DWELL_S)
            continue;

        command = &out[count++];
        command->axis = axis;
        command->kind = POLARIS_RATE_SCHED_SLOW;
        command->point = desired;
        scheduler->active[axis] = desired;
        scheduler->active_valid[axis] = 1;
        scheduler->last_switch_s[axis] = now_s;
    }
    return count;
}
