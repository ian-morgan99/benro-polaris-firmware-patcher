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

typedef struct {
    int tile_id;
    int hits;
    double distance;
} tile_candidate_t;

typedef struct {
    FILE *file;
    uint32_t tile_count;
    uint32_t record_count;
    uint32_t ratio_scale;
} triangle_index_t;

static double rad(double x) { return x * M_PI / 180.0; }
static double deg(double x) { return x * 180.0 / M_PI; }
static double length2(double x, double y) { return sqrt(x * x + y * y); }
static double wrap_ra(double value) {
    while (value < 0) value += 360.0;
    while (value >= 360.0) value -= 360.0;
    return value;
}

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

static int candidate_compare(const void *a, const void *b) {
    const tile_candidate_t *x = (const tile_candidate_t *)a;
    const tile_candidate_t *y = (const tile_candidate_t *)b;
    if (x->hits != y->hits) return y->hits - x->hits;
    return x->tile_id - y->tile_id;
}

static int distance_compare(const void *a, const void *b) {
    const tile_candidate_t *x = (const tile_candidate_t *)a;
    const tile_candidate_t *y = (const tile_candidate_t *)b;
    if (x->distance < y->distance) return -1;
    if (x->distance > y->distance) return 1;
    return x->tile_id - y->tile_id;
}

static int load_observations(const char *filename, point_t *observations, int maximum) {
    FILE *file = fopen(filename, "r");
    char line[256];
    int count = 0;
    if (!file) return 0;
    while (count < maximum && fgets(line, sizeof(line), file)) {
        if (line[0] == '#' || !line[0]) continue;
        if (sscanf(line, "%lf %lf", &observations[count].ra,
                   &observations[count].dec) >= 2) count++;
    }
    fclose(file);
    return count;
}

static int triangle_index_open(const char *filename, triangle_index_t *index) {
    char magic[8];
    uint32_t version;
    index->file = fopen(filename, "rb");
    if (!index->file) return 0;
    if (fread(magic, 1, 8, index->file) != 8 ||
        memcmp(magic, "POLTRI01", 8) != 0 ||
        fread(&version, sizeof(version), 1, index->file) != 1 ||
        fread(&index->tile_count, sizeof(index->tile_count), 1, index->file) != 1 ||
        fread(&index->record_count, sizeof(index->record_count), 1, index->file) != 1 ||
        fread(&index->ratio_scale, sizeof(index->ratio_scale), 1, index->file) != 1 ||
        version != 1 || index->ratio_scale == 0) {
        fclose(index->file); index->file = NULL; return 0;
    }
    return 1;
}

static void triangle_index_close(triangle_index_t *index) {
    if (index->file) fclose(index->file);
    index->file = NULL;
}

static int triangle_index_read(const triangle_index_t *index, uint32_t position,
                               uint16_t *ratio1, uint16_t *ratio2,
                               uint32_t *tile_id) {
    uint16_t ratios[2];
    long offset = 24L + (long)position * 8L;
    if (position >= index->record_count || fseek(index->file, offset, SEEK_SET) != 0 ||
        fread(ratios, sizeof(ratios), 1, index->file) != 1 ||
        fread(tile_id, sizeof(*tile_id), 1, index->file) != 1) return 0;
    *ratio1 = ratios[0]; *ratio2 = ratios[1];
    return 1;
}

static uint32_t triangle_key(uint16_t ratio1, uint16_t ratio2) {
    return ((uint32_t)ratio1 << 16) | ratio2;
}

static uint32_t triangle_index_lower_bound(const triangle_index_t *index, uint32_t target) {
    uint32_t low = 0, high = index->record_count;
    while (low < high) {
        uint32_t middle = low + (high - low) / 2, tile;
        uint16_t ratio1, ratio2;
        if (!triangle_index_read(index, middle, &ratio1, &ratio2, &tile)) return index->record_count;
        if (triangle_key(ratio1, ratio2) < target) low = middle + 1;
        else high = middle;
    }
    return low;
}

static void triangle_index_add_hits(const triangle_index_t *index, double a, double b,
                                    double c, int tile_count, int *hits) {
    double sides[3] = {a, b, c};
    uint16_t ratio1, ratio2, query1, query2, found1, found2;
    int delta1, delta2, delta_limit = 0;
    uint32_t position, tile, target;
    double t;
    if (sides[0] > sides[1]) { t = sides[0]; sides[0] = sides[1]; sides[1] = t; }
    if (sides[1] > sides[2]) { t = sides[1]; sides[1] = sides[2]; sides[2] = t; }
    if (sides[0] > sides[1]) { t = sides[0]; sides[0] = sides[1]; sides[1] = t; }
    if (sides[0] < 3.0) return;
    {
        double raw1 = floor(index->ratio_scale * sides[1] / sides[0] + 0.5);
        double raw2 = floor(index->ratio_scale * sides[2] / sides[0] + 0.5);
        /* The on-disk format saturates catalogue ratios at 65535, but a
         * query above that range is not equivalent to a saturated triangle.
         * Dropping it avoids turning very skinny observed triangles into a
         * large false candidate set at the saturation key. */
        if (raw1 > 65535.0 || raw2 > 65535.0) return;
        ratio1 = (uint16_t)raw1;
        ratio2 = (uint16_t)raw2;
    }
    /* The packaged index uses 0.1% bins. Keep the initial lookup exact: a
     * broad tolerance creates a candidate flood across an all-sky index, and
     * the native matcher remains the authoritative residual check. */
    for (delta1 = -delta_limit; delta1 <= delta_limit; delta1++) for (delta2 = -delta_limit; delta2 <= delta_limit; delta2++) {
        int candidate1 = (int)ratio1 + delta1, candidate2 = (int)ratio2 + delta2;
        if (candidate1 < 0) candidate1 = 0;
        if (candidate1 > 65535) candidate1 = 65535;
        if (candidate2 < 0) candidate2 = 0;
        if (candidate2 > 65535) candidate2 = 65535;
        query1 = (uint16_t)candidate1;
        query2 = (uint16_t)candidate2;
        target = triangle_key(query1, query2);
        position = triangle_index_lower_bound(index, target);
        for (; position < index->record_count && triangle_index_read(index, position, &found1, &found2, &tile) &&
               triangle_key(found1, found2) == target; position++) {
            if (tile < (uint32_t)tile_count) hits[tile]++;
        }
    }
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
        tiles[count].ra = wrap_ra((ri + 0.5) * ra_bin_width);
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
                      int max_catalogue, int anchor_stars, int minimum_matches, double scale_tol,
                      double residual_px, char *result, size_t result_size) {
    int pipefd[2], status;
    pid_t child;
    char width_s[32], height_s[32], focal_s[32], sensor_s[32], ra_s[32], dec_s[32];
    char radius_s[32], stars_s[16], catalogue_s[16], anchor_s[16], matches_s[16];
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
    snprintf(anchor_s, sizeof(anchor_s), "%d", anchor_stars);
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
              "--anchor-stars", anchor_s,
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
                    "[--triangle-index FILE] [--solver FILE] [--ra R --dec D] [--radius D] "
                    "[--step-deg D] [--rings N] [--attempts N] "
                    "[--max-stars N] [--max-catalog N] [--anchor-stars N] [--min-matches N] "
                    "[--scale-tol F] [--residual-px F]\n", program);
}

int main(int argc, char **argv) {
    const char *catalog_dir = NULL, *manifest = NULL, *stars = NULL;
    const char *triangle_index_file = NULL;
    const char *solver = "polaris-solve-independent";
    double width = 0, height = 0, focal = 0, sensor = 36;
    double hint_ra = 0, hint_dec = 0, radius = 15, step = 5;
    double ra_bin = 10, dec_bin = 10;
    double scale_tol = 0.15, residual_px = 5;
    int have_ra = 0, have_dec = 0, rings = 5, attempts = 40;
    int max_stars = 30, max_catalogue = 120, anchor_stars = 10, minimum_matches = 12;
    int early_matches = 20;
    double early_rms = 1.5;
    int i, s, t, tried = 0, tile_count, start_count = 0;
    tile_t *tiles = NULL;
    point_t *starts = NULL;
    int *candidate_order = NULL;
    tile_candidate_t *candidates = NULL;
    point_t *observations = NULL;
    triangle_index_t triangle_index = {0};
    char result[16384];
    char best_result[16384];
    int best_matches = 0;
    double best_rms = 1e30;
    const char *mode;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--catalog-dir") && i + 1 < argc) catalog_dir = argv[++i];
        else if (!strcmp(argv[i], "--manifest") && i + 1 < argc) manifest = argv[++i];
        else if (!strcmp(argv[i], "--triangle-index") && i + 1 < argc) triangle_index_file = argv[++i];
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
        else if (!strcmp(argv[i], "--anchor-stars") && i + 1 < argc) anchor_stars = atoi(argv[++i]);
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
    candidate_order = calloc((size_t)tile_count, sizeof(*candidate_order));
    if (!candidate_order) { free(tiles); return 1; }
    starts = calloc((size_t)(attempts + 1), sizeof(*starts));
    if (!starts) { free(candidate_order); free(tiles); return 1; }
    if (have_ra) {
        candidates = calloc((size_t)tile_count, sizeof(*candidates));
        if (!candidates) {
            free(candidate_order); free(starts); free(tiles);
            printf("{\"solved\":false,\"failure_reason\":\"out_of_memory\"}\n");
            return 1;
        }
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
        int candidate_count = 0;
        if (triangle_index_file) {
            if (!triangle_index_open(triangle_index_file, &triangle_index) ||
                triangle_index.tile_count != (uint32_t)tile_count) {
                triangle_index_close(&triangle_index);
                free(observations); free(candidate_order); free(starts); free(tiles);
                printf("{\"solved\":false,\"failure_reason\":\"invalid_triangle_index\"}\n");
                return 3;
            }
            double expected_scale = 206264.806 * atan((sensor / width) / focal);
            int observation_count;
            observations = calloc((size_t)max_stars, sizeof(*observations));
            int *hits = calloc((size_t)tile_count, sizeof(*hits));
            if (observations && hits &&
                (observation_count = load_observations(stars, observations, max_stars)) >= 3) {
                int left, right;
                int third, limit = observation_count < 15 ? observation_count : 15;
                for (left = 0; left < limit; left++)
                    for (right = left + 1; right < limit; right++)
                        for (third = right + 1; third < limit; third++)
                            triangle_index_add_hits(&triangle_index,
                        length2(observations[left].ra - observations[right].ra,
                                observations[left].dec - observations[right].dec) * expected_scale,
                                length2(observations[left].ra - observations[third].ra,
                                        observations[left].dec - observations[third].dec) * expected_scale,
                                length2(observations[right].ra - observations[third].ra,
                                        observations[right].dec - observations[third].dec) * expected_scale,
                                tile_count, hits);
                candidates = calloc((size_t)tile_count, sizeof(*candidates));
                if (candidates) {
                    for (t = 0; t < tile_count; t++) if (hits[t] > 0) {
                        candidates[candidate_count].tile_id = t;
                        candidates[candidate_count].hits = hits[t];
                        candidate_count++;
                    }
                    qsort(candidates, (size_t)candidate_count, sizeof(*candidates), candidate_compare);
                    for (t = 0; t < candidate_count; t++) candidate_order[t] = candidates[t].tile_id;
                }
            }
            free(hits);
            if (candidate_count > 0) mode = "all-sky-triangle-index";
            else triangle_index_close(&triangle_index);
        }
        if (!candidate_count) {
            for (t = 0; t < tile_count; t++) candidate_order[t] = t;
            candidate_count = tile_count;
            mode = "all-sky-tile-centres";
        }
        for (t = 0; t < candidate_count && start_count < attempts; t++) {
            start_count = add_start(starts, start_count, attempts + 1,
                                    tiles[candidate_order[t]].ra,
                                    tiles[candidate_order[t]].dec);
        }
    }
    if (!have_ra) {
        /* A blind tile-centre pass has one unambiguous tile per attempt.  Do
         * not try every neighbouring tile for the first sky position: that
         * would spend the whole budget around one patch and never reach the
         * rest of the all-sky catalogue. */
        for (t = 0; t < start_count && tried < attempts; t++) {
            int tile_id = candidate_order[t];
            result[0] = '\0';
            run_solver(solver, &tiles[tile_id], stars, width, height, focal, sensor,
                       starts[t].ra, starts[t].dec, radius, max_stars,
                       max_catalogue, anchor_stars, minimum_matches, scale_tol, residual_px,
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
            int nearby = 0;
            double tile_radius = radius + length2(ra_bin, dec_bin) / 2.0;
            for (t = 0; t < tile_count; t++) {
                double distance = angular_distance(starts[s].ra, starts[s].dec,
                                                   tiles[t].ra, tiles[t].dec);
                if (distance <= tile_radius) {
                    candidates[nearby].tile_id = t;
                    candidates[nearby].distance = distance;
                    nearby++;
                }
            }
            qsort(candidates, (size_t)nearby, sizeof(*candidates), distance_compare);
            for (t = 0; t < nearby && tried < attempts; t++) {
                int tile_id = candidates[t].tile_id;
                result[0] = '\0';
                run_solver(solver, &tiles[tile_id], stars, width, height, focal, sensor,
                           starts[s].ra, starts[s].dec, radius, max_stars,
                           max_catalogue, anchor_stars, minimum_matches, scale_tol, residual_px,
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
        triangle_index_close(&triangle_index);
        free(observations); free(candidates); free(candidate_order); free(starts); free(tiles); return 0;
    }
    printf("{\"solved\":false,\"failure_reason\":\"search_exhausted\","
           "\"attempts\":%d,\"search_mode\":\"%s\"}\n", tried, mode);
    triangle_index_close(&triangle_index);
    free(observations); free(candidates); free(candidate_order); free(starts); free(tiles); return 7;
}
