/* SPDX-License-Identifier: MIT
 * Host-only WCS image PA regression test: cc -std=c99 -Wall -Wextra -pedantic
 * -Icontainer/astro tests/test-polaris-image-pa.c -lm -o /tmp/test-pa && /tmp/test-pa
 */
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include "polaris-image-pa.h"
static void check(const double cd[2][2], int y, double expected, int parity) {
    double pa = -1; int flip = -1;
    assert(polaris_image_pa_from_cd(cd, y, &pa, &flip));
    assert(fabs(pa-expected) < 1e-7);
    assert(flip == parity);
}
int main(void) {
    const double north[2][2] = {{-1,0},{0,1}};
    const double east[2][2] = {{0,1},{1,0}};
    const double south[2][2] = {{1,0},{0,-1}};
    const double west[2][2] = {{0,-1},{-1,0}};
    const double mirror[2][2] = {{1,0},{0,1}};
    const double singular[2][2] = {{1,2},{2,4}};
    const double bad[2][2] = {{NAN,0},{0,1}};
    double pa=123; int parity=123;
    check(north,1,0,0);
    check(east,1,90,0);
    check(south,1,180,0);
    check(west,1,270,0);
    check(mirror,1,0,1);
    check(north,-1,180,0);
    assert(!polaris_image_pa_from_cd(singular,1,&pa,&parity));
    assert(!polaris_image_pa_from_cd(bad,1,&pa,&parity));
    assert(!polaris_image_pa_from_cd(north,0,&pa,&parity));
    assert(pa==123 && parity==123);
    puts("image PA regression tests passed");
    return 0;
}
