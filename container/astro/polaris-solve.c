/* SPDX-License-Identifier: MIT
 *
 * polaris-solve — a minimal astrometry.net front end for the Benro Polaris.
 *
 * Takes a star list (ours, or an astrometry.net .xyls) plus the lens/sensor
 * geometry, and prints the solved sky position as one JSON line. It is a
 * SEPARATE PROCESS on purpose: astrometry.net's FITS layer is GPL, so the
 * licence boundary is the process boundary (see docs/LICENSE-AUDIT.md).
 *
 * Nothing here reads pixels — star extraction is somebody else's job, which is
 * also what keeps GPLv3 `simplexy`/`ctmf` out of the build.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <sys/time.h>
#include <sys/resource.h>
#include <signal.h>
#include <unistd.h>

#include "os-features.h"
#include "solver.h"
#include "index.h"
#include "starxy.h"
#include "matchobj.h"
#include "sip.h"
#include "sip_qfits.h"
#include "sip-utils.h"
#include "xylist.h"
#include "log.h"
#include "errors.h"
#include "starutil.h"
#include "mathutil.h"
#include "fitsioutils.h"

#define MAXIDX 64

/* A WRONG hint is far worse than no hint: the solver searches the hinted region
 * first, finds nothing, and then grinds. Measured on device: a mismatched hint
 * ran 11 minutes before being killed. The align loop must never be able to hang
 * the mount like that, so enforce a hard wall-clock bound with SIGALRM -- it
 * cannot be defeated by anything inside the solver. */
static volatile int g_nfield_for_timeout = 0;
static void on_timeout(int sig) {
    const char* msg;
    (void)sig;
    msg = "{\"solved\":false,\"error\":\"timeout\"}\n";
    /* write(), not printf(): async-signal-safe */
    if (write(1, msg, strlen(msg)) < 0) { /* nothing useful to do */ }
    _exit(3);
}

static void usage(const char* me) {
    fprintf(stderr,
"usage: %s --index <file-or-dir> [...] (--stars FILE | --xyls FILE)\n"
"          --width W --height H [geometry] [hints]\n"
"\n"
"  star input\n"
"    --stars FILE      plain text, one star per line: \"x y [flux]\"\n"
"                      (0,0 = top-left; flux optional, brightest first if absent)\n"
"    --xyls FILE       an astrometry.net .xyls table (X, Y, FLUX columns)\n"
"    --width/--height  image size in pixels (REQUIRED)\n"
"\n"
"  geometry (either form; both set the pixel-scale search range)\n"
"    --focal-mm F      lens focal length\n"
"    --sensor-mm S     sensor width         (default 36.0, full frame)\n"
"    --scale-tol T     fractional tolerance (default 0.20 = +/-20%%)\n"
"    --scale-low A --scale-high B   arcsec/pixel, set directly\n"
"\n"
"  hints (optional, big speedups)\n"
"    --ra R --dec D --radius DEG    search near this sky position only\n"
"    --depth N         stop after the brightest N stars (default 0 = all)\n"
"    --cpulimit SEC    hard wall-clock limit; prints {\"solved\":false,\n"
"                      \"error\":\"timeout\"} and exits 3 (default 0 = no limit).\n"
"                      ALWAYS set this in an automated loop: a wrong hint can\n"
"                      grind for many minutes.\n"
"    --parity 0|1|2    0=normal 1=flipped 2=both (default 2)\n"
"    --no-tweak        skip the 2nd-order SIP refinement (TAN fit only)\n"
"    --timings         add timings_ms{star_read,index_load,solve} and peak_rss_kb\n"
"                      to the JSON, for benchmarking (issue #342). Off by default.\n"
"    --verbose\n", me);
}

/* Monotonic, not wall clock. The Polaris has no RTC and sets its time over NTP
 * once the network is up; a step during a solve would make a gettimeofday delta
 * read as negative or as many minutes. Issue #342 needs stage timings that can
 * be compared across runs, so the clock must not be able to move underneath them.
 * CLOCK_MONOTONIC is in glibc 2.24 (the target) and needs no -lrt on modern glibc. */
static double now_seconds(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

/* Opt-in per-stage timings (issue #342). Off by default so the JSON the mount
 * and the webui parse stays byte-for-byte what it was; --timings appends them.
 * stdout carries only the result line, so these go out on that same line. */
static int g_timings = 0;
static double t_star_ms = 0, t_index_ms = 0, t_solve_ms = 0;

/* Peak resident set of this process, in kB. ru_maxrss is kB on Linux and the
 * solver's index loading is the RAM question #342 asks about. */
static long peak_rss_kb(void) {
    struct rusage ru;
    if (getrusage(RUSAGE_SELF, &ru) != 0) return -1;
    return ru.ru_maxrss;
}

/* Render the timing tail for the result JSON. Empty string when not requested.
 * Kept as one helper so the solved and unsolved lines cannot drift apart. */
static void timings_tail(char* buf, size_t n) {
    if (!g_timings) { buf[0] = '\0'; return; }
    snprintf(buf, n,
             ",\"timings_ms\":{\"star_read\":%.1f,\"index_load\":%.1f,"
             "\"solve\":%.1f},\"peak_rss_kb\":%ld",
             t_star_ms, t_index_ms, t_solve_ms, peak_rss_kb());
}

/* "x y [flux]" per line; '#' comments and blank lines skipped. */
static starxy_t* read_star_text(const char* fn) {
    FILE* f = fopen(fn, "r");
    char line[512];
    double *x = NULL, *y = NULL, *flux = NULL;
    int n = 0, cap = 0, anyflux = 0;
    starxy_t* sxy;
    if (!f) { fprintf(stderr, "cannot open %s\n", fn); return NULL; }
    while (fgets(line, sizeof(line), f)) {
        double xx, yy, ff = 0.0;
        int got;
        if (line[0] == '#' || line[0] == '\n') continue;
        got = sscanf(line, "%lf %lf %lf", &xx, &yy, &ff);
        if (got < 2) continue;
        if (got >= 3) anyflux = 1;
        if (n == cap) {
            cap = cap ? cap * 2 : 256;
            x = realloc(x, cap * sizeof(double));
            y = realloc(y, cap * sizeof(double));
            flux = realloc(flux, cap * sizeof(double));
        }
        x[n] = xx; y[n] = yy; flux[n] = (got >= 3) ? ff : (double)(cap - n);
        n++;
    }
    fclose(f);
    if (!n) { fprintf(stderr, "no stars in %s\n", fn); free(x); free(y); free(flux); return NULL; }
    sxy = starxy_new(n, TRUE, FALSE);
    starxy_set_x_array(sxy, x);
    starxy_set_y_array(sxy, y);
    starxy_set_flux_array(sxy, flux);
    if (anyflux) starxy_sort_by_flux(sxy);
    free(x); free(y); free(flux);
    return sxy;
}

static starxy_t* read_star_xyls(const char* fn) {
    xylist_t* xy = xylist_open(fn);
    starxy_t* sxy;
    if (!xy) { fprintf(stderr, "cannot open xyls %s\n", fn); return NULL; }
    sxy = xylist_read_field(xy, NULL);
    xylist_close(xy);
    if (!sxy) { fprintf(stderr, "cannot read field from %s\n", fn); return NULL; }
    starxy_sort_by_flux(sxy);
    return sxy;
}

/* Add an index file, or every index file in a directory.
 *
 * When a pixel-scale range is known (the normal case: EXIF gives us focal length
 * and sensor width), indexes whose quads cannot possibly fall inside it are
 * dropped here rather than handed to the solver. Upstream astrometry.net does
 * exactly this in onefield.c via index_overlaps_scale_range(); our front end
 * previously loaded every --index it was given, so a solve at 20 arcsec/pixel
 * still paid for parsing and iterating the 1-arcsec indexes. On the device's
 * 2-core ARMv7 that is wall-clock we would rather spend on indexes that can
 * actually match.
 *
 * The quad range is derived the same way upstream derives it, from
 * DEFAULT_QSF_LO/DEFAULT_QSF_HI (0.1 and 1.0, include/astrometry/onefield.h),
 * but widened across the whole scale window instead of a single nominal scale:
 * the smallest possible quad uses funits_lower and the largest uses
 * funits_upper. That errs towards keeping indexes, so the filter can never
 * discard one that was in fact usable -- it only ever removes ones that are
 * certainly out of range.
 */
#define QSF_LO 0.1
#define QSF_HI 1.0

/* add_indexes() outcomes. A skip is not a failure: reporting one as "could not
 * load" would send an operator chasing a corrupt file that is perfectly fine,
 * which is exactly the kind of misleading diagnostic this project has had to
 * clean up elsewhere. */
#define IDX_ADDED     1
#define IDX_SKIPPED   0
#define IDX_FAILED   (-1)

static int add_indexes(solver_t* solver, const char* path, int verbose,
                       double slo, double shi, double W, double H,
                       int scale_filter, int* skipped) {
    index_t* ind = index_load(path, 0, NULL);
    if (!ind) return IDX_FAILED;

    if (scale_filter && slo > 0 && shi >= slo && W > 0 && H > 0) {
        double minside = (W < H) ? W : H;
        double maxside = (W > H) ? W : H;
        double quadlo = QSF_LO * minside * slo;
        double quadhi = QSF_HI * maxside * shi;
        if (!index_overlaps_scale_range(ind, quadlo, quadhi)) {
            if (verbose)
                fprintf(stderr, "[polaris-solve] index %s skipped: quads [%.1f, %.1f] arcmin "
                                "outside image range [%.1f, %.1f] arcmin\n",
                        ind->indexname,
                        arcsec2arcmin(ind->index_scale_lower),
                        arcsec2arcmin(ind->index_scale_upper),
                        arcsec2arcmin(quadlo), arcsec2arcmin(quadhi));
            index_free(ind);
            if (skipped) (*skipped)++;
            return IDX_SKIPPED;
        }
    }

    solver_add_index(solver, ind);
    if (verbose) fprintf(stderr, "[polaris-solve] index %s\n", ind->indexname);
    return IDX_ADDED;
}

int main(int argc, char** argv) {
    solver_t* solver;
    starxy_t* field = NULL;
    const char* idxpaths[MAXIDX];
    int nidx = 0, i;
    const char *starsfn = NULL, *xylsfn = NULL;
    double W = 0, H = 0;
    double focal = 0, sensor = 36.0, tol = 0.20;
    double slo = 0, shi = 0;
    double ra = 0, dec = 0, radius = 0;
    int have_radec = 0, depth = 0, parity = 2, verbose = 0, tweak = 1;
    double cpulimit = 0, t0, dt, ta;

    for (i = 1; i < argc; i++) {
        const char* a = argv[i];
        #define NEXT() (++i < argc ? argv[i] : (usage(argv[0]), exit(2), ""))
        if      (!strcmp(a, "--index"))      { if (nidx < MAXIDX) idxpaths[nidx++] = NEXT(); }
        else if (!strcmp(a, "--stars"))      starsfn = NEXT();
        else if (!strcmp(a, "--xyls"))       xylsfn  = NEXT();
        else if (!strcmp(a, "--width"))      W = atof(NEXT());
        else if (!strcmp(a, "--height"))     H = atof(NEXT());
        else if (!strcmp(a, "--focal-mm"))   focal = atof(NEXT());
        else if (!strcmp(a, "--sensor-mm"))  sensor = atof(NEXT());
        else if (!strcmp(a, "--scale-tol"))  tol = atof(NEXT());
        else if (!strcmp(a, "--scale-low"))  slo = atof(NEXT());
        else if (!strcmp(a, "--scale-high")) shi = atof(NEXT());
        else if (!strcmp(a, "--ra"))         { ra = atof(NEXT()); have_radec = 1; }
        else if (!strcmp(a, "--dec"))        { dec = atof(NEXT()); have_radec = 1; }
        else if (!strcmp(a, "--radius"))     radius = atof(NEXT());
        else if (!strcmp(a, "--depth"))      depth = atoi(NEXT());
        else if (!strcmp(a, "--cpulimit"))   cpulimit = atof(NEXT());
        else if (!strcmp(a, "--parity"))     parity = atoi(NEXT());
        else if (!strcmp(a, "--no-tweak"))   tweak = 0;
        else if (!strcmp(a, "--timings"))    g_timings = 1;
        else if (!strcmp(a, "--verbose"))    verbose = 1;
        else if (!strcmp(a, "-h") || !strcmp(a, "--help")) { usage(argv[0]); return 0; }
        else { fprintf(stderr, "unknown option: %s\n", a); usage(argv[0]); return 2; }
        #undef NEXT
    }
    if (!nidx || (!starsfn && !xylsfn) || W <= 0 || H <= 0) { usage(argv[0]); return 2; }

    log_init(verbose ? LOG_VERB : LOG_MSG);
    log_to(stderr);          /* keep stdout clean: it carries only our JSON */
    fits_use_error_system();

    ta = now_seconds();
    field = starsfn ? read_star_text(starsfn) : read_star_xyls(xylsfn);
    t_star_ms = (now_seconds() - ta) * 1000.0;
    if (!field) return 1;

    /* pixel scale search range, in arcsec/pixel */
    if (slo <= 0 || shi <= 0) {
        if (focal > 0) {
            double pixmm = sensor / W;
            double nominal = rad2arcsec(atan(pixmm / focal));
            slo = nominal * (1.0 - tol);
            shi = nominal * (1.0 + tol);
        } else {
            slo = 0.1; shi = 3600.0;              /* blind */
        }
    }

    solver = solver_new();
    solver->funits_lower = slo;
    solver->funits_upper = shi;
    solver->quadsize_min = 0.1 * (W < H ? W : H);
    solver->distance_from_quad_bonus = TRUE;
    solver->parity = (parity == 0) ? PARITY_NORMAL : (parity == 1) ? PARITY_FLIP : PARITY_BOTH;
    if (depth > 0) solver->endobj = depth;
    if (cpulimit > 0) {
        struct sigaction sa;
        memset(&sa, 0, sizeof(sa));
        sa.sa_handler = on_timeout;
        sigaction(SIGALRM, &sa, NULL);
        alarm((unsigned)(cpulimit + 0.5));
    }
    solver_set_keep_logodds(solver, log(1e12));
    /* Refine with a 2nd-order SIP fit. Camera lenses -- especially the wide
     * ones used for an alignment frame -- have enough distortion that a plain
     * TAN fit biases the field centre by a noticeable fraction of a degree,
     * and the centre is exactly what the mount is told to sync to. */
    if (tweak) {
        solver->do_tweak = TRUE;
        solver->tweak_aborder = 2;
        solver->tweak_abporder = 2;
    }
    solver_set_field(solver, field);
    solver_set_field_bounds(solver, 0, W, 0, H);
    if (have_radec && radius > 0) solver_set_radec(solver, ra, dec, radius);

    /* Two passes. The first keeps only indexes whose quad sizes can overlap the
     * pixel-scale window we are searching. If that rejects every index we retry
     * unfiltered: a wrong focal length in EXIF would otherwise turn "search
     * everything and fail slowly" into "refuse to search at all", which is a
     * worse failure mode than the one the filter is meant to avoid. */
    int nskipped = 0;
    ta = now_seconds();
    for (i = 0; i < nidx; i++)
        if (add_indexes(solver, idxpaths[i], verbose, slo, shi, W, H, 1, &nskipped) == IDX_FAILED)
            fprintf(stderr, "[polaris-solve] WARNING: could not load index %s\n", idxpaths[i]);
    if (solver_n_indices(solver) == 0 && nskipped > 0) {
        fprintf(stderr, "[polaris-solve] scale filter rejected all %i indexes; "
                        "retrying unfiltered\n", nskipped);
        nskipped = 0;
        for (i = 0; i < nidx; i++)
            if (add_indexes(solver, idxpaths[i], verbose, slo, shi, W, H, 0, NULL) == IDX_FAILED)
                fprintf(stderr, "[polaris-solve] WARNING: could not load index %s\n", idxpaths[i]);
    }
    if (verbose && nskipped > 0)
        fprintf(stderr, "[polaris-solve] scale filter skipped %i of %i indexes\n",
                nskipped, nidx);
    if (solver_n_indices(solver) == 0) {
        fprintf(stderr, "[polaris-solve] no indexes loaded\n");
        return 1;
    }
    /* Covers the filtered pass and the unfiltered retry together: #342 asks how
     * much of a solve is index I/O, and the retry is part of that cost. */
    t_index_ms = (now_seconds() - ta) * 1000.0;

    t0 = now_seconds();
    solver_run(solver);
    dt = now_seconds() - t0;
    t_solve_ms = dt * 1000.0;

    char tail[128];
    timings_tail(tail, sizeof tail);

    if (solver->best_match_solves) {
        tan_t* wcs = &(solver->best_match.wcstan);
        double cra, cdec, pscale, orient, det;
        tan_pixelxy2radec(wcs, W / 2.0, H / 2.0, &cra, &cdec);
        pscale = tan_pixel_scale(wcs);
        orient = tan_get_orientation(wcs);
        /* Sign of the CD determinant = handedness of the solution. The caller
         * needs this to turn `roll` into a real camera orientation: a mirrored
         * field rolls the opposite way. */
        det = wcs->cd[0][0] * wcs->cd[1][1] - wcs->cd[0][1] * wcs->cd[1][0];
        printf("{\"solved\":true,"
               "\"ra_deg\":%.6f,\"dec_deg\":%.6f,\"roll_deg\":%.4f,"
               "\"pixscale_arcsec\":%.6f,\"field_w_deg\":%.4f,\"field_h_deg\":%.4f,"
               "\"parity\":\"%s\",\"cd\":[%.9g,%.9g,%.9g,%.9g],"
               "\"index\":\"%s\",\"logodds\":%.3f,\"nmatch\":%i,\"nfield\":%i,"
               "\"solve_seconds\":%.3f%s}\n",
               cra, cdec, orient, pscale,
               arcsec2deg(pscale * W), arcsec2deg(pscale * H),
               (det < 0) ? "normal" : "flipped",
               wcs->cd[0][0], wcs->cd[0][1], wcs->cd[1][0], wcs->cd[1][1],
               solver->best_index ? solver->best_index->indexname : "?",
               solver->best_match.logodds, solver->best_match.nmatch,
               starxy_n(field), dt, tail);
        return 0;
    }
    printf("{\"solved\":false,\"nfield\":%i,\"solve_seconds\":%.3f%s}\n",
           starxy_n(field), dt, tail);
    return 3;
}
