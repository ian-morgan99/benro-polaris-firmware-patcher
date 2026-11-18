/* SPDX-License-Identifier: MIT
 * Shared, host-testable arithmetic for Alpaca solve tokens.
 */
#ifndef POLARIS_JOB_TOKEN_H
#define POLARIS_JOB_TOKEN_H
#include <stdint.h>
static inline uint64_t polaris_next_job_token(uint64_t epoch_us, uint64_t *last) {
    uint64_t token = epoch_us;
    if (!last) return 0;
    if (token <= *last) {
        if (*last == UINT64_MAX) return 0;
        token = *last + 1;
    }
    *last = token;
    return token;
}
#endif
