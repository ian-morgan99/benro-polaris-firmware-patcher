/* Timing is opt-in and lossy; camera calls must survive diagnostic failures. */
#include <errno.h>
#include <time.h>
#include <stdatomic.h>
#include <sys/socket.h>
static atomic_int clock_calls, get_calls, tree_calls, set_calls, send_calls;
static int fail_clock_call, fail_send_errno, fail_socket, socket_calls;
static int fake_clock_gettime(clockid_t clock_id, struct timespec *value)
{
    if (clock_id != CLOCK_MONOTONIC)
        return -1;
    int call = atomic_fetch_add(&clock_calls, 1) + 1;
    if (call == fail_clock_call) {
        errno = EFAULT;
        return -1;
    }
    value->tv_sec = call;
    value->tv_nsec = 0;
    return 0;
}
static int test_socket(int domain, int type, int protocol);
static ssize_t test_sendto(int fd, const void *buf, size_t len, int flags,
                          const struct sockaddr *dest, socklen_t dest_len);
#define clock_gettime fake_clock_gettime
#define socket test_socket
#define sendto test_sendto
#define STAGE2_NO_CONSTRUCTOR 1
#include "stage2_loader.c"
#undef socket
#undef sendto
#include <assert.h>
#include <poll.h>
#include <pthread.h>

static int get_result = -2;
static void *const camera_arg = (void *)0x1234;
static void *const widget_arg = (void *)0x2345;
static void *const context_arg = (void *)0x3456;

static int test_socket(int domain, int type, int protocol)
{
    socket_calls++;
    if (fail_socket) {
        errno = EMFILE;
        return -1;
    }
    return socket(domain, type, protocol);
}

static ssize_t test_sendto(int fd, const void *buf, size_t len, int flags,
                          const struct sockaddr *dest, socklen_t dest_len)
{
    const struct sockaddr_in *address = (const struct sockaddr_in *)dest;
    assert(len > 0 && len < 256);
    assert(flags == (MSG_DONTWAIT | MSG_NOSIGNAL));
    assert(dest_len == sizeof(*address) && address->sin_family == AF_INET);
    assert(address->sin_addr.s_addr == htonl(INADDR_LOOPBACK));
    atomic_fetch_add(&send_calls, 1);
    if (fail_send_errno) {
        errno = fail_send_errno;
        return -1;
    }
    return sendto(fd, buf, len, flags, dest, dest_len);
}

static int fake_get(void *camera, const char *name, void **widget, void *context)
{
    assert(camera == camera_arg && strcmp(name, "exposurecompensation") == 0);
    assert(widget && context == context_arg && errno == EDOM);
    atomic_fetch_add(&get_calls, 1);
    errno = EIO;
    return get_result;
}

static int fake_set(void *camera, const char *name, void *widget, void *context)
{
    assert(camera == camera_arg && strcmp(name, "iso") == 0);
    assert(widget == widget_arg && context == context_arg && errno == EDOM);
    atomic_fetch_add(&set_calls, 1);
    errno = ENOSPC;
    return -6;
}

static int fake_tree(Stage2Camera *camera, Stage2CameraWidget **widget, Stage2Context *context)
{
    assert(camera == camera_arg && widget && context == context_arg && errno == EDOM);
    atomic_fetch_add(&tree_calls, 1);
    *widget = widget_arg;
    errno = EBUSY;
    return 0;
}

static void read_single(void)
{
    void *widget = NULL;
    errno = EDOM;
    assert(stage2_shim_gp_camera_get_single_config(camera_arg, "exposurecompensation", &widget, context_arg) == -2);
    assert(errno == EIO && widget == NULL);
}

static void write_single(void)
{
    errno = EDOM;
    assert(stage2_shim_gp_camera_set_single_config(camera_arg, "iso", widget_arg, context_arg) == -6);
    assert(errno == ENOSPC);
}

static void read_tree(void)
{
    Stage2CameraWidget *widget = NULL;
    errno = EDOM;
    assert(stage2_timed_get_config(camera_arg, &widget, context_arg) == 0);
    assert(errno == EBUSY && widget == widget_arg);
}

static void expect_record(int receiver, const char *expected)
{
    struct pollfd pfd = { .fd = receiver, .events = POLLIN };
    assert(poll(&pfd, 1, 1000) == 1);
    char record[256] = {0};
    ssize_t length = recv(receiver, record, sizeof(record), MSG_DONTWAIT);
    assert(length > 0 && (size_t)length < sizeof(record));
    assert(record[length - 1] == '\n' && strstr(record, expected));
    assert(strstr(record, "seq=") && strstr(record, " pid=") && strstr(record, " tid="));
    assert(strstr(record, " start=") && strstr(record, " end="));
}

static void expect_empty(int receiver)
{
    char record[256];
    assert(recv(receiver, record, sizeof(record), MSG_DONTWAIT) == -1);
    assert(errno == EAGAIN || errno == EWOULDBLOCK);
}

static void *concurrent_reads(void *unused)
{
    (void)unused;
    for (int i = 0; i < 64; i++)
        read_single();
    return NULL;
}

int main(void)
{
    FILE *logs = tmpfile();
    assert(logs);
    int saved_stderr = dup(STDERR_FILENO);
    assert(saved_stderr >= 0 && dup2(fileno(logs), STDERR_FILENO) >= 0);
    g_real_gp_camera_get_single_config = fake_get;
    g_real_gp_camera_set_single_config = fake_set;
    unsetenv("STAGE2_SHUTTER_FALLBACK");
    unsetenv("STAGE2_TETHER_CAPTURE");
    unsetenv("STAGE2_CONFIG_TIMING");
    unsetenv("STAGE2_CONFIG_TIMING_PORT");
    stage2_config_timing_init();
    assert(stage2_config_tree_slot_target((void *)fake_tree) == (void *)fake_tree);
    assert(g_real_gp_camera_get_config == NULL);
    read_single();
    write_single();
    assert(get_calls == 1 && set_calls == 1 && clock_calls == 0 && send_calls == 0);
    assert(socket_calls == 0);

    assert(setenv("STAGE2_CONFIG_TIMING", "1", 1) == 0);
    stage2_config_timing_init(); /* missing port */
    const char *bad_ports[] = { "", "0", "1023", "65536", "-1", "+1234", " 1234", "1234x", "99999999999999999999999999" };
    for (size_t i = 0; i < sizeof(bad_ports) / sizeof(bad_ports[0]); i++) {
        assert(setenv("STAGE2_CONFIG_TIMING_PORT", bad_ports[i], 1) == 0);
        stage2_config_timing_init();
        assert(!stage2_config_timing_enabled());
    }
    assert(socket_calls == 0);
    assert(setenv("STAGE2_CONFIG_TIMING_PORT", "12345", 1) == 0);
    assert(setenv("STAGE2_CONFIG_TIMING", "0", 1) == 0);
    stage2_config_timing_init();
    assert(socket_calls == 0);
    assert(setenv("STAGE2_CONFIG_TIMING", "1", 1) == 0);
    fail_socket = 1;
    stage2_config_timing_init();
    assert(!stage2_config_timing_enabled() && socket_calls == 1);
    read_single();
    assert(get_calls == 2 && clock_calls == 0 && send_calls == 0);
    fail_socket = 0;

    int receiver = socket(AF_INET, SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    assert(receiver >= 0);
    struct sockaddr_in address = { .sin_family = AF_INET, .sin_addr.s_addr = htonl(INADDR_LOOPBACK) };
    assert(bind(receiver, (struct sockaddr *)&address, sizeof(address)) == 0);
    socklen_t address_len = sizeof(address);
    assert(getsockname(receiver, (struct sockaddr *)&address, &address_len) == 0);
    char port[6];
    snprintf(port, sizeof(port), "%u", ntohs(address.sin_port));
    assert(setenv("STAGE2_CONFIG_TIMING_PORT", port, 1) == 0);
    stage2_config_timing_init();
    assert(stage2_config_timing_enabled());
    assert(fcntl(g_config_timing_socket, F_GETFL) & O_NONBLOCK);
    assert(fcntl(g_config_timing_socket, F_GETFD) & FD_CLOEXEC);
    stage2_config_timing_init(); /* must not leak another socket */
    assert(socket_calls == 2);
    assert(stage2_config_tree_slot_target((void *)fake_tree) == (void *)stage2_timed_get_config);
    assert(g_real_gp_camera_get_config == fake_tree);
    read_single();
    expect_record(receiver, "op=get-single name=exposurecompensation core-ret=-2");
    write_single();
    expect_record(receiver, "op=set-single name=iso core-ret=-6");
    read_tree();
    expect_record(receiver, "op=get-tree name=- core-ret=0");
    assert(get_calls == 3 && set_calls == 2 && tree_calls == 1 && send_calls == 3);
    fflush(stderr);
    assert(ftell(logs) == 0); /* diagnostics never use stderr */

    get_result = 0;
    void *widget = NULL;
    errno = EDOM;
    assert(stage2_shim_gp_camera_get_single_config(camera_arg, "exposurecompensation", &widget, context_arg) == STAGE2_GP_ERROR_CAMERA_BUSY);
    assert(get_calls == 4 && widget == NULL);
    expect_record(receiver, "op=get-single name=exposurecompensation core-ret=0");
    get_result = -2;
    fflush(stderr);
    rewind(logs);
    char text[2048] = {0};
    assert(fread(text, 1, sizeof(text) - 1, logs) > 0);
    assert(strstr(text, "GP_OK without widget for exposurecompensation"));
    assert(!strstr(text, "config-timing"));
    assert(fseek(logs, 0, SEEK_END) == 0);
    long log_end = ftell(logs);

    fail_clock_call = clock_calls + 1;
    read_single();
    fail_clock_call = clock_calls + 2;
    write_single();
    fail_clock_call = 0;
    assert(get_calls == 5 && set_calls == 3 && send_calls == 4);
    expect_empty(receiver);

    const int failures[] = { EAGAIN, ENOBUFS, EPIPE, EINTR, ECONNREFUSED };
    for (size_t i = 0; i < sizeof(failures) / sizeof(failures[0]); i++) {
        fail_send_errno = failures[i];
        read_single();
        write_single();
        read_tree();
    }
    assert(get_calls == 10 && set_calls == 8 && tree_calls == 6 && send_calls == 19);
    expect_empty(receiver);
    fail_send_errno = 0;

    char long_name[4096];
    memset(long_name, 'x', sizeof(long_name) - 1);
    long_name[sizeof(long_name) - 1] = 0;
    struct timespec start = {0};
    stage2_config_timing_log("get-single", long_name, -2, 1, &start);
    expect_record(receiver, " core-ret=-2 ");
    /* A missing receiver is harmless, including any ICMP-derived send error. */
    close(receiver);
    read_single();
    write_single();
    read_tree();

    /* Concurrent calls must share the hard cap, including failed sends. */
    atomic_store(&g_config_timing_attempts, 0);
    int sends_before = send_calls, reads_before = get_calls;
    fail_send_errno = EAGAIN;
    pthread_t threads[8];
    for (size_t i = 0; i < 8; i++)
        assert(pthread_create(&threads[i], NULL, concurrent_reads, NULL) == 0);
    for (size_t i = 0; i < 8; i++)
        assert(pthread_join(threads[i], NULL) == 0);
    assert(get_calls == reads_before + 512);
    assert(send_calls == sends_before + (int)STAGE2_CONFIG_TIMING_LIMIT);
    assert(atomic_load(&g_config_timing_attempts) == STAGE2_CONFIG_TIMING_LIMIT);
    int clocks_before = clock_calls;
    read_single();
    write_single();
    read_tree();
    assert(clock_calls == clocks_before && send_calls == sends_before + (int)STAGE2_CONFIG_TIMING_LIMIT);
    fflush(stderr);
    assert(ftell(logs) == log_end);
    assert(dup2(saved_stderr, STDERR_FILENO) >= 0);
    close(saved_stderr);
    fclose(logs);
    close(g_config_timing_socket);
    puts("PASS: bounded nonblocking config timing; failures preserve calls, arguments, results and errno");
    return 0;
}
