/* SPDX-License-Identifier: MIT */
/* Native bounded search front end for the independent POLCAT01 solver.
 *
 * The child solver does the actual triangle matching in C.  This front end
 * only chooses spatial tiles and hint positions, so the device never needs a
 * Python interpreter for the independent path.  It is deliberately bounded:
 * a missing or bad mount hint must not turn a Polaris capture worker into an
 * unbounded CPU job.
 */
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

typedef struct {
    char path[PATH_MAX];
    double ra, dec;
} tile_t;

typedef struct {
    double ra, dec;
} point_t;

static double rad(double x) { return x * M_PI / 180.0; }
static double deg(double x) { return x * 180.0 / M_PI; }

static double angular_distance(double ra1, double dec1, double ra2, double dec2) {
    double c = sin(rad(dec1)) * sin(rad(dec2)) +
               cos(rad(dec1)) * cos(rad(dec2)) * cos(rad(ra1 - ra2));
    if (c < -1.0) c = -1.0;
    if (c > 1.0) c = 1.0;
    return deg(acos(c));
}

static int parse_tile_name(const char *name, int *ra_bin, int *dec_bin) {
    int used = 0;
    if (sscanf(name, "tile-%d-%d.pcat%n", ra_bin, dec_bin, &used) != 2 ||
        name[used] != '\0') return 0;
    return *ra_bin >= 0 && *ra_bin < 360 && *dec_bin >= 0 && *dec_bin < 180;
}

static int tile_compare(const void *a, const void *b) {
    const tile_t *x = (const tile_t *)a, *y = (const tile_t *)b;
    if (x->dec < y->dec) return -1;
    if (x->dec > y->dec) return 1;
    if (x->ra < y->ra) return -1;
    if (x->ra > y->ra) return 1;
    return 0;
}

static int load_tiles(const char *directory, double ra_bin_width,
                      double dec_bin_width, tile_t **out) {
    DIR *dir = opendir(directory);
    struct dirent *entry;
    tile_t *tiles = NULL;
    int count = 0, capacity = 0;
    if (!dir) return 0;
    while ((entry = readdir(dir)) != NULL) {
        int ri, di;
        tile_t *grown;
        if (!parse_tile_name(entry->d_name, &ri, &di)) continue;
        if (count == capacity) {
            capacity = capacity ? capacity * 2 : 64;
            grown = realloc(tiles, (size_t)capacity * sizeof(*tiles));
            if (!grown) { free(tiles); closedir(dir); return 0; }
            tiles = grown;
        }
        if (snprintf(tiles[count].path, sizeof(tiles[count].path), "%s/%s",
                     directory, entry->d_name) >= (int)sizeof(tiles[count].path)) {
            free(tiles); closedir(dir); return 0;
        }
        tiles[count].ra = fmod((ri + 0.5) * ra_bin_width, 360.0);
        tiles[count].dec = -90.0 + (di + 0.5) * dec_bin_width;
        count++;
    }
    closedir(dir);
    qsort(tiles, (size_t)count, sizeof(*tiles), tile_compare);
    *out = tiles;
    return count;
}

static int json_bool(const char *json, const char *key) {
    char needle[64];
    const char *p;
    snprintf(needle, sizeof(needle), "\"%s\":true", key);
    p = strstr(json, needle);
    return p != NULL;
}

static int json_int(const char *json, const char *key, int fallback) {
    char needle[64];
    const char *p;
    char *end;
    long value;
    snprintf(needle, sizeof(needle), "\"%s\":", key);
    p = strstr(json, needle);
    if (!p) return fallback;
    value = strtol(p + strlen(needle), &end, 10);
    return end == p + strlen(needle) ? fallback : (int)value;
}

static double json_double(const char *json, const char *key, double fallback) {
    char needle[64];
    const char *p;
    char *end;
    double value;
    snprintf(needle, sizeof(needle), "\"%s\":", key);
    p = strstr(json, needle);
    if (!p) return fallback;
    value = strtod(p + strlen(needle), &end);
    return end == p + strlen(needle) ? fallback : value;
}

/* Run one native child without going through a shell.  That keeps paths and
 * the catalogue directory data-only, and makes the search safe for filenames
 * that happen to contain shell metacharacters. */
static int run_solver(const char *solver, const tile_t *tile, const char *stars,
                      double width, double height, double focal, double sensor,
                      double ra, double dec, double radius, int max_stars,
                      int max_catalogue, int minimum_matches, double scale_tol,
                      double residual_px, char *result, size_t result_size) {
    int pipefd[2], status;
    pid_t child;
    char width_s[32], height_s[32], focal_s[32], sensor_s[32], ra_s[32], dec_s[32];
    char radius_s[32], stars_s[16], catalogue_s[16], matches_s[16];
    char scale_tol_s[32], residual_s[32];
    ssize_t used = 0, n;
    if (pipe(pipefd) < 0) return -1;
    snprintf(width_s, sizeof(width_s), "%.9g", width);
    snprintf(height_s, sizeof(height_s), "%.9g", height);
    snprintf(focal_s, sizeof(focal_s), "%.9g", focal);
    snprintf(sensor_s, sizeof(sensor_s), "%.9g", sensor);
    snprintf(ra_s, sizeof(ra_s), "%.9g", ra);
    snprintf(dec_s, sizeof(dec_s), "%.9g", dec);
    snprintf(radius_s, sizeof(radius_s), "%.9g", radius);
    snprintf(stars_s, sizeof(stars_s), "%d", max_stars);
    snprintf(catalogue_s, sizeof(catalogue_s), "%d", max_catalogue);
    snprintf(matches_s, sizeof(matches_s), "%d", minimum_matches);
    snprintf(scale_tol_s, sizeof(scale_tol_s), "%.9g", scale_tol);
    snprintf(residual_s, sizeof(residual_s), "%.9g", residual_px);
    child = fork();
    if (child < 0) { close(pipefd[0]); close(pipefd[1]); return -1; }
    if (child == 0) {
        int nullfd = open("/dev/null", 1);
        dup2(pipefd[1], STDOUT_FILENO);
        if (nullfd >= 0) dup2(nullfd, STDERR_FILENO);
        close(pipefd[0]); close(pipefd[1]);
        execl(solver, solver,
              "--catalog", tile->path, "--stars", stars,
              "--width", width_s, "--height", height_s,
              "--focal-mm", focal_s, "--sensor-mm", sensor_s,
              "--ra", ra_s, "--dec", dec_s, "--radius", radius_s,
              "--max-stars", stars_s, "--max-catalog", catalogue_s,
              "--min-matches", matches_s, "--scale-tol", scale_tol_s,
              "--residual-px", residual_s, (char *)NULL);
        _exit(127);
    }
    close(pipefd[1]);
    while ((n = read(pipefd[0], result + used,
                     result_size > (size_t)used + 1 ? result_size - (size_t)used - 1 : 0)) > 0) {
        used += n;
        if ((size_t)used + 1 >= result_size) break;
    }
    close(pipefd[0]);
    result[used < (ssize_t)result_size ? used : (ssize_t)result_size - 1] = '\0';
    waitpid(child, &status, 0);
    return WIFEXITED(status) ? WEXITSTATUS(status) : 128;
}

static int add_start(point_t *starts, int count, int capacity, double ra, double dec) {
    while (ra < 0) ra += 360.0;
    while (ra >= 360.0) ra -= 360.0;
    if (dec < -89.9) dec = -89.9;
    if (dec > 89.9) dec = 89.9;
    if (count >= capacity) return count;
    starts[count].ra = ra; starts[count].dec = dec;
    return count + 1;
}

static void usage(const char *program) {
    fprintf(stderr, "usage: %s --catalog-dir DIR --stars FILE --width W --height H "
                    "--focal-mm F [--sensor-mm S] [--manifest FILE] "
                    "[--solver FILE] [--ra R --dec D] [--radius D] "
                    "[--step-deg D] [--rings N] [--attempts N] "
                    "[--max-stars N] [--max-catalog N] [--min-matches N] "
                    "[--scale-tol F] [--residual-px F]\n", program);
}

int main(int argc, char **argv) {
    const char *catalog_dir = NULL, *manifest = NULL, *stars = NULL;
    const char *solver = "polaris-solve-independent";
    double width = 0, height = 0, focal = 0, sensor = 36;
    double hint_ra = 0, hint_dec = 0, radius = 15, step = 5;
    double ra_bin = 10, dec_bin = 10;
    double scale_tol = 0.15, residual_px = 5;
    int have_ra = 0, have_dec = 0, rings = 5, attempts = 40;
    int max_stars = 30, max_catalogue = 120, minimum_matches = 12;
    int early_matches = 20;
    double early_rms = 1.5;
    int i, s, t, tried = 0, tile_count, start_count = 0;
    tile_t *tiles = NULL;
    point_t *starts = NULL;
    char result[16384];
    char best_result[16384];
    int best_matches = 0;
    double best_rms = 1e30;
    const char *mode;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--catalog-dir") && i + 1 < argc) catalog_dir = argv[++i];
        else if (!strcmp(argv[i], "--manifest") && i + 1 < argc) manifest = argv[++i];
        else if (!strcmp(argv[i], "--solver") && i + 1 < argc) solver = argv[++i];
        else if (!strcmp(argv[i], "--stars") && i + 1 < argc) stars = argv[++i];
        else if (!strcmp(argv[i], "--width") && i + 1 < argc) width = atof(argv[++i]);
        else if (!strcmp(argv[i], "--height") && i + 1 < argc) height = atof(argv[++i]);
        else if (!strcmp(argv[i], "--focal-mm") && i + 1 < argc) focal = atof(argv[++i]);
        else if (!strcmp(argv[i], "--sensor-mm") && i + 1 < argc) sensor = atof(argv[++i]);
        else if (!strcmp(argv[i], "--ra") && i + 1 < argc) { hint_ra = atof(argv[++i]); have_ra = 1; }
        else if (!strcmp(argv[i], "--dec") && i + 1 < argc) { hint_dec = atof(argv[++i]); have_dec = 1; }
        else if (!strcmp(argv[i], "--radius") && i + 1 < argc) radius = atof(argv[++i]);
        else if (!strcmp(argv[i], "--step-deg") && i + 1 < argc) step = atof(argv[++i]);
        else if (!strcmp(argv[i], "--rings") && i + 1 < argc) rings = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--attempts") && i + 1 < argc) attempts = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--max-stars") && i + 1 < argc) max_stars = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--max-catalog") && i + 1 < argc) max_catalogue = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--min-matches") && i + 1 < argc) minimum_matches = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--scale-tol") && i + 1 < argc) scale_tol = atof(argv[++i]);
        else if (!strcmp(argv[i], "--residual-px") && i + 1 < argc) residual_px = atof(argv[++i]);
        else if (!strcmp(argv[i], "--early-matches") && i + 1 < argc) early_matches = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--early-rms") && i + 1 < argc) early_rms = atof(argv[++i]);
        else if (!strcmp(argv[i], "--ra-bin-deg") && i + 1 < argc) ra_bin = atof(argv[++i]);
        else if (!strcmp(argv[i], "--dec-bin-deg") && i + 1 < argc) dec_bin = atof(argv[++i]);
        else { usage(argv[0]); return 2; }
    }
    if (!catalog_dir || !stars || width <= 0 || height <= 0 || focal <= 0 ||
        have_ra != have_dec || radius <= 0 || ra_bin <= 0 || dec_bin <= 0) {
        printf("{\"solved\":false,\"failure_reason\":\"incomplete_arguments\"}\n");
        return 2;
    }
    if (manifest && access(manifest, R_OK) != 0) {
        printf("{\"solved\":false,\"failure_reason\":\"invalid_manifest\"}\n");
        return 3;
    }
    tile_count = load_tiles(catalog_dir, ra_bin, dec_bin, &tiles);
    if (tile_count <= 0) {
        printf("{\"solved\":false,\"failure_reason\":\"no_catalogue_tiles\"}\n");
        return 3;
    }
    if (attempts < 0) attempts = 0;
    if (attempts == 0) attempts = tile_count;
    starts = calloc((size_t)(attempts + 1), sizeof(*starts));
    if (!starts) { free(tiles); return 1; }
    if (have_ra) {
        start_count = add_start(starts, start_count, attempts + 1, hint_ra, hint_dec);
        for (s = 1; s <= rings && start_count < attempts; s++) {
            int n, total = 8 * s;
            for (n = 0; n < total && start_count < attempts; n++) {
                double angle = 2.0 * M_PI * n / total;
                start_count = add_start(starts, start_count, attempts + 1,
                                        hint_ra + step * s * cos(angle),
                                        hint_dec + step * s * sin(angle));
            }
        }
        mode = "hinted-corkscrew";
    } else {
        for (t = 0; t < tile_count && start_count < attempts; t++) {
            start_count = add_start(starts, start_count, attempts + 1,
                                    tiles[t].ra, tiles[t].dec);
        }
        mode = "all-sky-tile-centres";
    }
    if (!have_ra) {
        /* A blind tile-centre pass has one unambiguous tile per attempt.  Do
         * not try every neighbouring tile for the first sky position: that
         * would spend the whole budget around one patch and never reach the
         * rest of the all-sky catalogue. */
        for (t = 0; t < tile_count && tried < attempts; t++) {
            result[0] = '\0';
            run_solver(solver, &tiles[t], stars, width, height, focal, sensor,
                       tiles[t].ra, tiles[t].dec, radius, max_stars,
                       max_catalogue, minimum_matches, scale_tol, residual_px,
                       result, sizeof(result));
            tried++;
            if (json_bool(result, "solved")) {
                int matches = json_int(result, "matched_count", 0);
                double rms = json_double(result, "rms_px", 1e30);
                if (matches > best_matches ||
                    (matches == best_matches && rms < best_rms)) {
                    strncpy(best_result, result, sizeof(best_result) - 1);
                    best_result[sizeof(best_result) - 1] = '\0';
                    best_matches = matches;
                    best_rms = rms;
                }
                if (matches >= early_matches && rms <= early_rms) break;
            }
        }
    } else {
        for (s = 0; s < start_count && tried < attempts; s++) {
            for (t = 0; t < tile_count && tried < attempts; t++) {
                double tile_radius = radius + hypot(ra_bin, dec_bin) / 2.0;
                if (angular_distance(starts[s].ra, starts[s].dec,
                                     tiles[t].ra, tiles[t].dec) > tile_radius) continue;
                result[0] = '\0';
                run_solver(solver, &tiles[t], stars, width, height, focal, sensor,
                           starts[s].ra, starts[s].dec, radius, max_stars,
                           max_catalogue, minimum_matches, scale_tol, residual_px,
                           result, sizeof(result));
                tried++;
                if (json_bool(result, "solved")) {
                    int matches = json_int(result, "matched_count", 0);
                    double rms = json_double(result, "rms_px", 1e30);
                    if (matches > best_matches ||
                        (matches == best_matches && rms < best_rms)) {
                        strncpy(best_result, result, sizeof(best_result) - 1);
                        best_result[sizeof(best_result) - 1] = '\0';
                        best_matches = matches;
                        best_rms = rms;
                    }
                    if (matches >= early_matches && rms <= early_rms) {
                        s = start_count;
                        break;
                    }
                }
            }
        }
    }
    if (best_matches >= minimum_matches) {
        char *end = strrchr(best_result, '}');
        if (end && (size_t)(end - best_result) + 80 < sizeof(best_result)) {
            *end = '\0';
            printf("%s,\"search_attempts\":%d,\"search_mode\":\"%s\"}\n",
                   best_result, tried, mode);
        } else {
            printf("%s\n", best_result);
        }
        free(starts); free(tiles); return 0;
    }
    printf("{\"solved\":false,\"failure_reason\":\"search_exhausted\","
           "\"attempts\":%d,\"search_mode\":\"%s\"}\n", tried, mode);
    free(starts); free(tiles); return 7;
}
