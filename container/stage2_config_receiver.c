/* Optional local collector for Stage-2 config timing. No camera API calls.
 * Collection is bounded by time, received datagrams and retained records.
 * File output occurs in this separate process, never in the camera process.
 */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <regex.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#define RECORD_BYTES 256
#define RECORD_LIMIT 128
#define DATAGRAM_LIMIT 512
static volatile sig_atomic_t interrupted;

static void interrupt_collection(int signal_number)
{
    (void)signal_number;
    interrupted = 1;
}

static int64_t now_ms(void)
{
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now))
        return -1;
    return (int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

static long argument_number(const char *text, long min, long max)
{
    if (!text || !*text)
        return -1;
    for (const char *p = text; *p; p++)
        if (*p < '0' || *p > '9')
            return -1;
    char *end;
    errno = 0;
    long value = strtol(text, &end, 10);
    return errno || *end || value < min || value > max ? -1 : value;
}

static int write_all(int fd, const char *data, size_t length)
{
    while (length) {
        ssize_t written = write(fd, data, length);
        if (written < 0 && errno == EINTR)
            continue;
        if (written <= 0)
            return -1;
        data += written;
        length -= (size_t)written;
    }
    return 0;
}

int main(int argc, char **argv)
{
    long port = -1, seconds = 30, limit = RECORD_LIMIT, expected_pid = 0;
    const char *output = NULL;
    for (int i = 1; i < argc; i += 2) {
        if (i + 1 == argc)
            goto usage;
        if (!strcmp(argv[i], "--port"))
            port = argument_number(argv[i + 1], 1024, 65535);
        else if (!strcmp(argv[i], "--seconds"))
            seconds = argument_number(argv[i + 1], 1, 120);
        else if (!strcmp(argv[i], "--max-records"))
            limit = argument_number(argv[i + 1], 1, RECORD_LIMIT);
        else if (!strcmp(argv[i], "--pid"))
            expected_pid = argument_number(argv[i + 1], 1, INT_MAX);
        else if (!strcmp(argv[i], "--output"))
            output = argv[i + 1];
        else
            goto usage;
    }
    if (port < 0 || seconds < 0 || limit < 0 || expected_pid < 0 ||
        !output || !*output)
        goto usage;

    regex_t format;
    const char *pattern =
        "^config-timing seq=([1-9][0-9]{0,2}) pid=([1-9][0-9]{0,9}) "
        "tid=[1-9][0-9]{0,9} op=(get-single|set-single|get-tree) "
        "name=[A-Za-z0-9_/-]{1,64} core-ret=-?[0-9]{1,11} "
        "start=[0-9]{1,20}\\.[0-9]{9} end=[0-9]{1,20}\\.[0-9]{9}\n$";
    if (regcomp(&format, pattern, REG_EXTENDED)) {
        fputs("receiver: cannot compile record validator\n", stderr);
        return 1;
    }
    int fd = socket(AF_INET, SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (fd < 0) {
        perror("receiver socket");
        regfree(&format);
        return 1;
    }
    struct sockaddr_in address = {
        .sin_family = AF_INET,
        .sin_addr.s_addr = htonl(INADDR_LOOPBACK),
        .sin_port = htons((uint16_t)port),
    };
    if (bind(fd, (struct sockaddr *)&address, sizeof(address))) {
        perror("receiver bind");
        close(fd);
        regfree(&format);
        return 1;
    }
    /* Refuse existing paths (including symlinks), and never append indefinitely. */
    int out = open(output, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (out < 0) {
        perror("receiver output");
        close(fd);
        regfree(&format);
        return 1;
    }
    struct sigaction action = { .sa_handler = interrupt_collection };
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT, &action, NULL) || sigaction(SIGTERM, &action, NULL)) {
        perror("receiver signals");
        close(out);
        close(fd);
        regfree(&format);
        return 1;
    }
    char records[RECORD_LIMIT][RECORD_BYTES];
    size_t sizes[RECORD_LIMIT];
    unsigned int received = 0, accepted = 0;
    int result = 0;
    const char *reason = "deadline";
    int64_t start = now_ms();
    if (start < 0) {
        result = 1;
        reason = "clock-error";
    } else {
        printf("READY loopback=%u seconds=%ld max-records=%ld pid=%ld\n",
               ntohs(address.sin_port), seconds, limit, expected_pid);
        fflush(stdout);
    }
    int64_t deadline = start + seconds * 1000;
    while (!result && !interrupted && accepted < (unsigned long)limit &&
           received < DATAGRAM_LIMIT) {
        int64_t now = now_ms();
        if (now < 0) { result = 1; reason = "clock-error"; break; }
        if (now >= deadline)
            break;
        struct pollfd pfd = { .fd = fd, .events = POLLIN };
        int ready = poll(&pfd, 1, (int)(deadline - now));
        if (ready < 0 && errno == EINTR)
            continue;
        if (ready < 0 || (pfd.revents & (POLLERR | POLLNVAL | POLLHUP))) {
            result = 1; reason = "socket-error"; break;
        }
        if (!ready)
            continue;
        char record[RECORD_BYTES];
        ssize_t bytes = recv(fd, record, sizeof(record), MSG_DONTWAIT | MSG_TRUNC);
        if (bytes < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR))
            continue;
        if (bytes < 0) { result = 1; reason = "receive-error"; break; }
        received++;
        if (bytes <= 0 || bytes >= RECORD_BYTES || memchr(record, 0, (size_t)bytes))
            continue;
        record[bytes] = 0;
        regmatch_t matches[3];
        if (regexec(&format, record, 3, matches, 0))
            continue;
        /* These fields contain only bounded digits after validation. */
        unsigned long sequence = strtoul(record + matches[1].rm_so, NULL, 10);
        unsigned long pid = strtoul(record + matches[2].rm_so, NULL, 10);
        if (sequence > RECORD_LIMIT || pid > INT_MAX ||
            (expected_pid && pid != (unsigned long)expected_pid))
            continue;
        memcpy(records[accepted], record, (size_t)bytes);
        sizes[accepted++] = (size_t)bytes;
    }
    if (interrupted) { result = 130; reason = "interrupted"; }
    else if (received == DATAGRAM_LIMIT) { result = 4; reason = "datagram-limit"; }
    else if (accepted == (unsigned long)limit) reason = "record-limit";
    else if (!result && !accepted) result = 3;
    close(fd);
    regfree(&format);
    for (unsigned int i = 0; i < accepted; i++) {
        if (write_all(out, records[i], sizes[i])) {
            perror("receiver write");
            result = 1; reason = "output-error"; break;
        }
    }
    if (close(out)) { perror("receiver close"); result = 1; reason = "output-error"; }
    fprintf(stderr, "receiver: accepted=%u rejected=%u reason=%s\n",
            accepted, received - accepted, reason);
    return result;

usage:
    fputs("usage: stage2-config-receiver --port 1024..65535 --output NEW_FILE "
          "[--seconds 1..120] [--max-records 1..128] [--pid PID]\n", stderr);
    return 2;
}
