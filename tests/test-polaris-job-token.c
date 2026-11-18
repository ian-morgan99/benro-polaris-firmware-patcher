/* SPDX-License-Identifier: MIT
 * Host-only regression for the Alpaca job-token arithmetic.
 * cc -std=c99 -Wall -Wextra -Werror -pedantic tests/test-polaris-job-token.c -o /tmp/test-job-token && /tmp/test-job-token
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <limits.h>

static uint64_t next_token(uint64_t epoch_microseconds, uint64_t *last) {
    uint64_t token = epoch_microseconds;
    if (token <= *last) {
        if (*last == UINT64_MAX) return 0;
        token = *last + 1;
    }
    *last = token;
    return token;
}
int main(void) {
    uint64_t last = 0;
    const uint64_t now_us = UINT64_C(1794960000000000);
    uint64_t a = next_token(now_us, &last);
    uint64_t b = next_token(now_us, &last);
    uint64_t c = next_token(now_us - 1000000, &last);
    assert(a == now_us);
    assert(b == a + 1);
    assert(c == b + 1);
    assert(c > a);
    assert(next_token(UINT64_MAX, &last) == UINT64_MAX);
    assert(next_token(UINT64_MAX, &last) == 0);
    puts("Alpaca job token arithmetic tests passed");
    return 0;
}
