/* SPDX-License-Identifier: MIT
 *
 * polaris-rate-wire — dry-run adapter for the known application SLOW path.
 *
 * This translates logical scheduler commands into the existing 532/533/534
 * application payload shape. It deliberately does not call polaris-link or
 * open a socket. The AC 4A float helper remains outside this adapter until
 * its MCU route, units, acknowledgement and stop/watchdog contract are
 * qualified on the target head.
 */
#ifndef POLARIS_RATE_WIRE_H
#define POLARIS_RATE_WIRE_H

#include <stddef.h>

#include "polaris-rate-scheduler.h"

#define POLARIS_RATE_WIRE_TYPE 3
#define POLARIS_RATE_WIRE_ARGS_MAX 64

typedef struct {
    int opcode; /* 532 HADJ, 533 VADJ, 534 RADJ */
    int type;   /* application control type, currently 3 */
    char args[POLARIS_RATE_WIRE_ARGS_MAX];
} polaris_rate_wire_frame_t;

/*
 * Encode one logical scheduler command for inspection by a fake head or a
 * future, separately qualified device wrapper.
 *
 * STOP uses the last active point retained by the scheduler, but changes its
 * state to 0. A stop without a valid previous SLOW point is rejected rather
 * than guessed. Return 0 on success and -1 on invalid input.
 */
int polaris_rate_wire_encode(const polaris_rate_schedule_command_t *command,
                             polaris_rate_wire_frame_t *out,
                             char *err, size_t errcap);

#endif /* POLARIS_RATE_WIRE_H */
