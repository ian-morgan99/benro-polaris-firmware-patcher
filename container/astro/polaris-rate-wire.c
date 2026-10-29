/* SPDX-License-Identifier: MIT
 *
 * Host-only preparation for the eventual rate-command device wrapper. This
 * file formats the already-known SLOW application controls; it has no socket,
 * process, link or motor side effect.
 */
#include "polaris-rate-wire.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

static int fail(char *err, size_t cap, const char *message) {
    if (err && cap) snprintf(err, cap, "%s", message);
    return -1;
}

static int opcode_for_axis(int axis) {
    switch (axis) {
    case 0: return 532; /* HADJ / M1 */
    case 1: return 533; /* VADJ / M2 */
    case 2: return 534; /* RADJ / M3 */
    default: return 0;
    }
}

static int valid_point(const polaris_rate_point_t *point) {
    return point && isfinite(point->dps) &&
           (point->key == 0 || point->key == 1) &&
           (point->state == 1 || point->state == 2) &&
           point->level >= 1 && point->level <= 5;
}

int polaris_rate_wire_encode(const polaris_rate_schedule_command_t *command,
                             polaris_rate_wire_frame_t *out,
                             char *err, size_t errcap) {
    int opcode;
    int state;
    int written;

    if (!command || !out)
        return fail(err, errcap, "rate wire argument is null");

    opcode = opcode_for_axis(command->axis);
    if (!opcode)
        return fail(err, errcap, "rate wire axis is invalid");
    if (!valid_point(&command->point))
        return fail(err, errcap, "rate wire point is invalid");

    switch (command->kind) {
    case POLARIS_RATE_SCHED_SLOW:
        state = command->point.state;
        break;
    case POLARIS_RATE_SCHED_STOP:
        state = 0;
        break;
    default:
        return fail(err, errcap, "rate wire command kind is invalid");
    }

    memset(out, 0, sizeof *out);
    out->opcode = opcode;
    out->type = POLARIS_RATE_WIRE_TYPE;
    written = snprintf(out->args, sizeof out->args,
                       "key:%d;state:%d;level:%d;",
                       command->point.key, state, command->point.level);
    if (written < 0 || (size_t)written >= sizeof out->args)
        return fail(err, errcap, "rate wire arguments are too long");
    return 0;
}
