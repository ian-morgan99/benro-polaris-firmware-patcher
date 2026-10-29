/* SPDX-License-Identifier: MIT
 *
 * A deliberately small fake head for host-side rate lifecycle tests. It
 * accepts only the already-known 532/533/534 SLOW payload and models an
 * explicit host watchdog. It does not represent an MCU implementation.
 */
#include "polaris-rate-fake-head.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

static int axis_for_opcode(int opcode) {
    switch (opcode) {
    case 532: return 0;
    case 533: return 1;
    case 534: return 2;
    default: return -1;
    }
}

static int parse_args(const char *args, int *key, int *state, int *level) {
    char canonical[64];
    char extra;
    int n;

    if (!args || !key || !state || !level) return -1;
    n = sscanf(args, "key:%d;state:%d;level:%d;%c",
               key, state, level, &extra);
    if (n != 3) return -1;
    n = snprintf(canonical, sizeof canonical, "key:%d;state:%d;level:%d;",
                 *key, *state, *level);
    if (n < 0 || (size_t)n >= sizeof canonical || strcmp(args, canonical) != 0)
        return -1;
    return 0;
}

void polaris_rate_fake_head_init(polaris_rate_fake_head_t *head,
                                  double watchdog_s) {
    if (!head) return;
    memset(head, 0, sizeof *head);
    head->watchdog_s = isfinite(watchdog_s) && watchdog_s > 0.0
        ? watchdog_s : POLARIS_RATE_FAKE_HEAD_WATCHDOG_S;
}

int polaris_rate_fake_head_apply(polaris_rate_fake_head_t *head,
                                 const polaris_rate_wire_frame_t *frame,
                                 double now_s) {
    int axis;
    int key, state, level;
    polaris_rate_fake_axis_t *slot;

    if (!head || !frame || !isfinite(now_s) || frame->type != 3)
        return -1;
    axis = axis_for_opcode(frame->opcode);
    if (axis < 0 || parse_args(frame->args, &key, &state, &level) != 0)
        return -1;
    if ((key != 0 && key != 1) || level < 1 || level > 5)
        return -1;

    slot = &head->axis[axis];
    if (slot->active && now_s < slot->last_update_s)
        return -1;
    if (state == 0) {
        if (!slot->active) return -1;
        slot->active = 0;
        slot->last_update_s = now_s;
        return 0;
    }
    if (state != 1 && state != 2)
        return -1;

    slot->active = 1;
    slot->key = key;
    slot->state = state;
    slot->level = level;
    slot->last_update_s = now_s;
    return 0;
}

int polaris_rate_fake_head_tick(polaris_rate_fake_head_t *head,
                                double now_s) {
    int axis;
    int stopped = 0;

    if (!head || !isfinite(now_s)) return -1;
    for (axis = 0; axis < POLARIS_RATE_AXES; axis++) {
        polaris_rate_fake_axis_t *slot = &head->axis[axis];
        if (slot->active && now_s - slot->last_update_s >= head->watchdog_s) {
            slot->active = 0;
            slot->last_update_s = now_s;
            stopped++;
        }
    }
    return stopped;
}
