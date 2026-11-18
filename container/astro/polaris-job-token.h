/* SPDX-License-Identifier: MIT
 * Shared, host-testable arithmetic for Alpaca solve tokens.
 */
#ifndef POLARIS_JOB_TOKEN_H
#define POLARIS_JOB_TOKEN_H
#include <stdint.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
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
/* Decimal only, no sign, whitespace, suffix or overflow. */
static inline int polaris_parse_job_token(const char *s, uint64_t *out) {
    char *end;
    unsigned long long parsed;
    const unsigned char *p = (const unsigned char *)s;
    if (!s || !*s || !out) return 0;
    while (*p) {
        if (*p < '0' || *p > '9') return 0;
        p++;
    }
    errno = 0;
    parsed = strtoull(s, &end, 10);
    if (errno == ERANGE || !end || *end || parsed == 0) return 0;
    *out = (uint64_t)parsed;
    return (unsigned long long)*out == parsed;
}
/* Read-only file representation may end in one newline written by fprintf.
 * Never use this for client input, which must remain strictly decimal. */
static inline int polaris_parse_persisted_job_token(char *s, uint64_t *out) {
    size_t n;
    if (!s) return 0;
    n = strlen(s);
    if (n && s[n - 1] == '\n') s[--n] = 0;
    return polaris_parse_job_token(s, out);
}
#endif
