/* SPDX-License-Identifier: MIT
 * Host-only regression for the Alpaca job-token arithmetic.
 * cc -std=c99 -Wall -Wextra -Werror -pedantic -Icontainer/astro tests/test-polaris-job-token.c -o /tmp/test-job-token && /tmp/test-job-token
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <limits.h>
#include "polaris-job-token.h"

int main(void) {
    uint64_t last = 0;
    const uint64_t now_us = UINT64_C(1794960000000000);
    uint64_t a = polaris_next_job_token(now_us, &last);
    uint64_t b = polaris_next_job_token(now_us, &last);
    uint64_t c = polaris_next_job_token(now_us - 1000000, &last);
    assert(a == now_us);
    assert(b == a + 1);
    assert(c == b + 1);
    assert(c > a);
    assert(polaris_next_job_token(UINT64_MAX, &last) == UINT64_MAX);
    assert(polaris_next_job_token(UINT64_MAX, &last) == 0);
    {
        uint64_t parsed = 0;
        assert(polaris_parse_job_token("1794960000000000", &parsed));
        assert(parsed == now_us);
        assert(polaris_parse_job_token("18446744073709551615", &parsed));
        assert(parsed == UINT64_MAX);
        assert(!polaris_parse_job_token("18446744073709551616", &parsed));
        assert(!polaris_parse_job_token("0", &parsed));
        assert(!polaris_parse_job_token("", &parsed));
        assert(!polaris_parse_job_token("-1", &parsed));
        assert(!polaris_parse_job_token("+1", &parsed));
        assert(!polaris_parse_job_token(" 1", &parsed));
        assert(!polaris_parse_job_token("1x", &parsed));
        assert(!polaris_parse_job_token("1\n", &parsed));
        assert(!polaris_parse_job_token(NULL, &parsed));
        assert(!polaris_parse_job_token("1", NULL));
    }
    {
        char persisted[] = "1794960000000000\n";
        char bad[] = "1794960000000000\nX";
        uint64_t parsed = 0;
        assert(polaris_parse_persisted_job_token(persisted, &parsed));
        assert(parsed == now_us);
        assert(!polaris_parse_persisted_job_token(bad, &parsed));
    }
    puts("Alpaca job token arithmetic and parser tests passed");
    return 0;
}
