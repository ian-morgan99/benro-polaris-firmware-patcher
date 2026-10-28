/* SPDX-License-Identifier: MIT */
/* Native Phase-2 independent solver. Hint-bounded triangle prototype. */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { double x, y, flux; } obs_t;
typedef struct { uint64_t id; double ra, dec, mag; } cat_t;

static double rad(double x) { return x * M_PI / 180.0; }
static double deg(double x) { return x * 180.0 / M_PI; }
static double hypot2(double x, double y) { return sqrt(x * x + y * y); }

/* The affine map is pixels per catalogue arcsecond.  Using only its first
 * column makes scale depend on the arbitrary catalogue X axis and is biased
 * by shear/noise.  The geometric mean of the two principal scales is the
 * area-preserving isotropic scale, i.e. the inverse square root of |det|. */
static double inverse_pixel_scale(const double *transform) {
    double determinant = transform[0] * transform[3] - transform[1] * transform[2];
    return fabs(determinant) > 1e-18 ? 1.0 / sqrt(fabs(determinant)) : 0.0;
}

static void sort3(double *a) {
    double t;
    if (a[1] < a[0]) { t = a[0]; a[0] = a[1]; a[1] = t; }
    if (a[2] < a[1]) { t = a[1]; a[1] = a[2]; a[2] = t; }
    if (a[1] < a[0]) { t = a[0]; a[0] = a[1]; a[1] = t; }
}

/* Solve a 3x3 least-squares normal equation.  The independent solver starts
 * with three stars, but once a candidate has more matches we should use all of
 * them rather than leave the answer at the noise-sensitive three-star affine
 * fit. */
static int solve3(double matrix[3][4], double answer[3]) {
    int i, j, k, pivot;
    double q, t;
    for (k = 0; k < 3; k++) {
        pivot = k;
        for (i = k + 1; i < 3; i++)
            if (fabs(matrix[i][k]) > fabs(matrix[pivot][k])) pivot = i;
        if (fabs(matrix[pivot][k]) < 1e-12) return 0;
        for (j = k; j < 4; j++) {
            q = matrix[k][j]; matrix[k][j] = matrix[pivot][j]; matrix[pivot][j] = q;
        }
        t = matrix[k][k];
        for (j = k; j < 4; j++) matrix[k][j] /= t;
        for (i = 0; i < 3; i++) if (i != k) {
            t = matrix[i][k];
            for (j = k; j < 4; j++) matrix[i][j] -= t * matrix[k][j];
        }
    }
    for (i = 0; i < 3; i++) answer[i] = matrix[i][3];
    return 1;
}

static int refine_affine(const double *cat_x, const double *cat_y,
                         const double *obs_x, const double *obs_y,
                         const int *obs_catalogue, int matches,
                         double *answer) {
    double xeq[3][4] = {{0}}, yeq[3][4] = {{0}};
    int i, r, c, q;
    if (matches < 3) return 0;
    for (i = 0; i < matches; i++) {
        q = obs_catalogue[i * 2 + 1];
        {
            double v[3] = {cat_x[q], cat_y[q], 1.0};
            for (r = 0; r < 3; r++) {
                for (c = 0; c < 3; c++) {
                    xeq[r][c] += v[r] * v[c];
                    yeq[r][c] += v[r] * v[c];
                }
                xeq[r][3] += v[r] * obs_x[obs_catalogue[i * 2]];
                yeq[r][3] += v[r] * obs_y[obs_catalogue[i * 2]];
            }
        }
    }
    if (!solve3(xeq, answer) || !solve3(yeq, answer + 3)) return 0;
    return 1;
}

/* Count only one observation per catalogue star.  The old nearest-neighbour
 * count could count two extracted blobs against the same catalogue star and
 * inflate confidence on a bad candidate.  The arrays are pairs of
 * (observation index, catalogue index), followed by a zero sentinel. */
static int score_transform(const double *cat_x, const double *cat_y, int used,
                           const double *obs_x, const double *obs_y, int observation_count,
                           const double *transform, double residual,
                           int *matches_out, double *rms_out, int *pairs,
                           unsigned char *catalogue_used) {
    int u, q, matches = 0;
    double error = 0;
    memset(catalogue_used, 0, (size_t)used);
    for (u = 0; u < observation_count; u++) {
        double nearest = 1e30;
        int nearest_q = -1;
        for (q = 0; q < used; q++) if (!catalogue_used[q]) {
            double dx = transform[0] * cat_x[q] + transform[1] * cat_y[q] + transform[4] - obs_x[u];
            double dy = transform[2] * cat_x[q] + transform[3] * cat_y[q] + transform[5] - obs_y[u];
            double distance = hypot2(dx, dy);
            if (distance < nearest) { nearest = distance; nearest_q = q; }
        }
        if (nearest_q >= 0 && nearest <= residual) {
            catalogue_used[nearest_q] = 1;
            pairs[matches * 2] = u;
            pairs[matches * 2 + 1] = nearest_q;
            matches++;
            error += nearest * nearest;
        }
    }
    *matches_out = matches;
    *rms_out = sqrt(error / (matches ? matches : 1));
    return matches;
}

static int load_catalogue(const char *filename, cat_t **out) {
    FILE *f = fopen(filename, "rb");
    char magic[8]; uint32_t version, count, i; cat_t *catalogue;
    if (!f) return 0;
    if (fread(magic, 1, 8, f) != 8 || memcmp(magic, "POLCAT01", 8) != 0 ||
        fread(&version, 4, 1, f) != 1 || fread(&count, 4, 1, f) != 1 || version != 1) {
        fclose(f); return 0;
    }
    catalogue = calloc(count, sizeof(*catalogue));
    if (!catalogue) { fclose(f); return 0; }
    for (i = 0; i < count; i++) {
        if (fread(&catalogue[i].id, 8, 1, f) != 1 || fread(&catalogue[i].ra, 8, 1, f) != 1 ||
            fread(&catalogue[i].dec, 8, 1, f) != 1 || fread(&catalogue[i].mag, 8, 1, f) != 1) {
            free(catalogue); fclose(f); return 0;
        }
    }
    fclose(f); *out = catalogue; return (int)count;
}

static int load_observations(const char *filename, obs_t **out, int maximum) {
    FILE *f = fopen(filename, "r"); char line[256]; int count = 0;
    obs_t *observations = calloc((size_t)maximum, sizeof(*observations));
    if (!f || !observations) { if (f) fclose(f); free(observations); return 0; }
    while (count < maximum && fgets(line, sizeof(line), f)) {
        if (line[0] == '#' || !line[0]) continue;
        if (sscanf(line, "%lf %lf %lf", &observations[count].x,
                   &observations[count].y, &observations[count].flux) >= 2) count++;
    }
    fclose(f); *out = observations; return count;
}

static int affine(const double *source, const double *destination, double *answer) {
    double matrix[6][7], q, t; int i, j, k, pivot;
    for (i = 0; i < 3; i++) {
        matrix[2*i][0] = source[2*i]; matrix[2*i][1] = source[2*i+1];
        matrix[2*i][2] = 0; matrix[2*i][3] = 0; matrix[2*i][4] = 1; matrix[2*i][5] = 0;
        matrix[2*i][6] = destination[2*i];
        matrix[2*i+1][0] = 0; matrix[2*i+1][1] = 0;
        matrix[2*i+1][2] = source[2*i]; matrix[2*i+1][3] = source[2*i+1];
        matrix[2*i+1][4] = 0; matrix[2*i+1][5] = 1; matrix[2*i+1][6] = destination[2*i+1];
    }
    for (k = 0; k < 6; k++) {
        pivot = k;
        for (i = k + 1; i < 6; i++) if (fabs(matrix[i][k]) > fabs(matrix[pivot][k])) pivot = i;
        if (fabs(matrix[pivot][k]) < 1e-12) return 0;
        for (j = k; j < 7; j++) { q = matrix[k][j]; matrix[k][j] = matrix[pivot][j]; matrix[pivot][j] = q; }
        t = matrix[k][k]; for (j = k; j < 7; j++) matrix[k][j] /= t;
        for (i = 0; i < 6; i++) if (i != k) { t = matrix[i][k]; for (j = k; j < 7; j++) matrix[i][j] -= t * matrix[k][j]; }
    }
    for (i = 0; i < 6; i++) answer[i] = matrix[i][6];
    return 1;
}

static void tangent_to_radec(double ra0, double dec0, double east_arcsec,
                             double north_arcsec, double *ra, double *dec) {
    double x = rad(east_arcsec / 3600.0), y = rad(north_arcsec / 3600.0);
    double denominator = cos(dec0) - y * sin(dec0);
    *ra = deg(ra0 + atan2(x, denominator));
    *dec = deg(atan2(sin(dec0) + y * cos(dec0), sqrt(denominator * denominator + x * x)));
    while (*ra < 0) *ra += 360.0;
    while (*ra >= 360.0) *ra -= 360.0;
}

static void usage(const char *program) {
    fprintf(stderr, "usage: %s --catalog FILE --stars FILE --width W --height H --focal-mm F "
                    "[--sensor-mm S] [--ra R --dec D] [--radius D] [--min-matches N] "
                    "[--anchor-stars N]\n", program);
}

int main(int argc, char **argv) {
    const char *catalogue_file = NULL, *stars_file = NULL;
    double width = 0, height = 0, focal = 0, sensor = 36, ra_hint = 0, dec_hint = 0;
    double radius = 15, tolerance = .35, residual = 5, scale, cra, cdec;
    int have_ra = 0, have_dec = 0, max_stars = 30, max_catalogue = 120, minimum_matches = 4;
    int anchor_stars = 15;
    int i, j, k, l, catalogue_count, observation_count, used = 0, best_matches = 0;
    cat_t *catalogue = NULL; obs_t *observations = NULL;
    double *cat_x, *cat_y, *obs_x, *obs_y, *cat_dist;
    int *candidate_pairs;
    unsigned char *catalogue_used;
    double best[6] = {0, 0, 0, 0, 0, 0}, best_scale = 0, best_rms = 1e30;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--catalog")) catalogue_file = argv[++i];
        else if (!strcmp(argv[i], "--stars")) stars_file = argv[++i];
        else if (!strcmp(argv[i], "--width")) width = atof(argv[++i]);
        else if (!strcmp(argv[i], "--height")) height = atof(argv[++i]);
        else if (!strcmp(argv[i], "--focal-mm")) focal = atof(argv[++i]);
        else if (!strcmp(argv[i], "--sensor-mm")) sensor = atof(argv[++i]);
        else if (!strcmp(argv[i], "--ra")) { ra_hint = atof(argv[++i]); have_ra = 1; }
        else if (!strcmp(argv[i], "--dec")) { dec_hint = atof(argv[++i]); have_dec = 1; }
        else if (!strcmp(argv[i], "--radius")) radius = atof(argv[++i]);
        else if (!strcmp(argv[i], "--scale-tol")) tolerance = atof(argv[++i]);
        else if (!strcmp(argv[i], "--residual-px")) residual = atof(argv[++i]);
        else if (!strcmp(argv[i], "--max-stars")) max_stars = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--max-catalog")) max_catalogue = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--min-matches")) minimum_matches = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--anchor-stars")) anchor_stars = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--cpulimit") || !strcmp(argv[i], "--index")) ++i;
        else { usage(argv[0]); return 2; }
    }
    if (!catalogue_file || !stars_file || width <= 0 || height <= 0 || focal <= 0 || have_ra != have_dec) {
        printf("{\"solved\":false,\"failure_reason\":\"incomplete_arguments\"}\n"); return 2;
    }
    if (!have_ra) {
        printf("{\"solved\":false,\"failure_reason\":\"blind_search_index_required\",\"focal_length_mm\":%.3f}\n", focal); return 6;
    }
    catalogue_count = load_catalogue(catalogue_file, &catalogue);
    observation_count = load_observations(stars_file, &observations, max_stars);
    if (catalogue_count <= 0) { printf("{\"solved\":false,\"failure_reason\":\"invalid_catalogue\"}\n"); return 3; }
    if (observation_count < 3) { printf("{\"solved\":false,\"failure_reason\":\"too_few_stars\"}\n"); return 3; }
    if (anchor_stars < 3) anchor_stars = 3;
    if (anchor_stars > observation_count) anchor_stars = observation_count;

    cra = rad(ra_hint); cdec = rad(dec_hint); scale = 206264.806 * atan((sensor / width) / focal);
    cat_x = calloc((size_t)catalogue_count, sizeof(*cat_x)); cat_y = calloc((size_t)catalogue_count, sizeof(*cat_y));
    obs_x = calloc((size_t)observation_count, sizeof(*obs_x)); obs_y = calloc((size_t)observation_count, sizeof(*obs_y));
    cat_dist = calloc((size_t)max_catalogue * (size_t)max_catalogue, sizeof(*cat_dist));
    candidate_pairs = calloc((size_t)observation_count * 2, sizeof(*candidate_pairs));
    catalogue_used = calloc((size_t)max_catalogue, sizeof(*catalogue_used));
    if (!cat_x || !cat_y || !obs_x || !obs_y || !cat_dist || !candidate_pairs || !catalogue_used) return 1;
    for (i = 0; i < observation_count; i++) { obs_x[i] = observations[i].x - width / 2.0; obs_y[i] = observations[i].y - height / 2.0; }
    {
        double radius_cos = cos(rad(radius));
        double sin_cdec = sin(cdec), cos_cdec = cos(cdec);
    for (i = 0; i < catalogue_count && used < max_catalogue; i++) {
        double r = rad(catalogue[i].ra), d = rad(catalogue[i].dec), dr = r - cra;
        double sin_d = sin(d), cos_d = cos(d);
        double denominator = sin_d * sin_cdec + cos_d * cos_cdec * cos(dr);
        if (denominator < radius_cos || denominator <= 0) continue;
        cat_x[used] = cos_d * sin(dr) / denominator * deg(1) * 3600;
        cat_y[used] = (sin_d * cos_cdec - cos_d * sin_cdec * cos(dr)) / denominator * deg(1) * 3600;
        used++;
    }
    }
    if (used < 3) { printf("{\"solved\":false,\"failure_reason\":\"no_index_coverage\"}\n"); return 3; }

    /* Pair distances are invariant across every candidate transform.  Cache
     * them once; this removes thousands of hypot() calls from the triangle
     * search without increasing the catalogue format or runtime dependencies. */
    for (i = 0; i < used; i++) for (j = i + 1; j < used; j++) {
        cat_dist[i * max_catalogue + j] = cat_dist[j * max_catalogue + i] =
            hypot2(cat_x[i] - cat_x[j], cat_y[i] - cat_y[j]);
    }

    for (i = 0; i < anchor_stars; i++) for (j = i + 1; j < anchor_stars; j++) for (k = j + 1; k < anchor_stars; k++) {
        double observed_triangle[3] = { hypot2(obs_x[i]-obs_x[j], obs_y[i]-obs_y[j]), hypot2(obs_x[i]-obs_x[k], obs_y[i]-obs_y[k]), hypot2(obs_x[j]-obs_x[k], obs_y[j]-obs_y[k]) };
        sort3(observed_triangle);
        for (l = 0; l < used; l++) for (int b = l + 1; b < used; b++) for (int c = b + 1; c < used; c++) {
            double catalogue_triangle[3] = { cat_dist[l * max_catalogue + b], cat_dist[l * max_catalogue + c], cat_dist[b * max_catalogue + c] };
            int permutation[3] = {l, b, c};
            sort3(catalogue_triangle);
            if (observed_triangle[0] < 1e-9 || catalogue_triangle[0] < 1 ||
                fabs(observed_triangle[1]/observed_triangle[0] - catalogue_triangle[1]/catalogue_triangle[0]) > .08 ||
                fabs(observed_triangle[2]/observed_triangle[0] - catalogue_triangle[2]/catalogue_triangle[0]) > .08) continue;
            for (int p0 = 0; p0 < 3; p0++) for (int p1 = 0; p1 < 3; p1++) if (p1 != p0) for (int p2 = 0; p2 < 3; p2++) if (p2 != p0 && p2 != p1) {
                int p[3] = {p0, p1, p2}; double source[6] = {cat_x[permutation[p[0]]], cat_y[permutation[p[0]]], cat_x[permutation[p[1]]], cat_y[permutation[p[1]]], cat_x[permutation[p[2]]], cat_y[permutation[p[2]]]};
                double destination[6] = {obs_x[i], obs_y[i], obs_x[j], obs_y[j], obs_x[k], obs_y[k]}, transform[6];
                if (!affine(source, destination, transform)) continue;
                double solved_scale = inverse_pixel_scale(transform);
                int matches, refined_matches; double candidate_rms, refined_rms, refined[6];
                if (solved_scale <= 0 || solved_scale < scale*(1-tolerance) || solved_scale > scale*(1+tolerance)) continue;
                score_transform(cat_x, cat_y, used, obs_x, obs_y, observation_count,
                                transform, residual, &matches, &candidate_rms,
                                candidate_pairs, catalogue_used);
                /* Re-fit with every unique inlier, then score once more.  The
                 * refinement is the accuracy gain; the cached distances and
                 * anchor cap are the speed gains. */
                if (matches >= 3 && refine_affine(cat_x, cat_y, obs_x, obs_y,
                                                   candidate_pairs, matches, refined)) {
                    score_transform(cat_x, cat_y, used, obs_x, obs_y, observation_count,
                                    refined, residual, &refined_matches, &refined_rms,
                                    candidate_pairs, catalogue_used);
                    if (refined_matches > matches ||
                        (refined_matches == matches && refined_rms < candidate_rms)) {
                        memcpy(transform, refined, sizeof(transform));
                        matches = refined_matches;
                        candidate_rms = refined_rms;
                    }
                }
                if (matches > best_matches ||
                    (matches == best_matches && candidate_rms < best_rms)) {
                    memcpy(best, transform, sizeof(best));
                    best_matches = matches; best_scale = inverse_pixel_scale(transform); best_rms = candidate_rms;
                }
            }
        }
    }
    if (best_matches < minimum_matches) { printf("{\"solved\":false,\"failure_reason\":\"no_verified_candidate\",\"matched_count\":%d}\n", best_matches); return 4; }
    {
        double det = best[0]*best[3] - best[1]*best[2], invdet = 1.0 / det;
        double east = (-best[4]*best[3] + best[1]*best[5]) * invdet;
        double north = (best[2]*best[4] - best[0]*best[5]) * invdet, solved_ra, solved_dec;
        tangent_to_radec(cra, cdec, east, north, &solved_ra, &solved_dec);
        printf("{\"solved\":true,\"ra_deg\":%.8f,\"dec_deg\":%.8f,\"scale_arcsec_per_px\":%.6f,\"rotation_deg\":%.6f,\"parity\":%d,\"matched_count\":%d,\"rms_px\":%.6f,\"catalog\":\"independent-POLCAT01\"}\n", solved_ra, solved_dec, best_scale, deg(atan2(best[2], best[0])), det < 0 ? -1 : 1, best_matches, best_rms);
    }
    free(catalogue); free(observations); free(cat_x); free(cat_y); free(obs_x); free(obs_y);
    free(cat_dist); free(candidate_pairs); free(catalogue_used); return 0;
}
