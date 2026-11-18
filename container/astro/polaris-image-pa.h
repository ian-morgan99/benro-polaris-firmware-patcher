/* SPDX-License-Identifier: MIT
 * Camera image position angle from a linear FITS WCS CD matrix.
 *
 * Convention: PA of increasing image +Y, measured east of north in degrees,
 * normalised to [0, 360). This is an image-axis PA, NOT a mount/rotator angle.
 * The WCS CD matrix maps image (x,y) pixel offsets to tangent-plane
 * (east,north) angular offsets. FITS image coordinates have +Y upwards;
 * screen coordinates may invert Y. Callers must specify the intended axis.
 *
 * Avoid using atan2(cd[0][1],cd[1][1]) blindly near singular WCS.
 */
#ifndef POLARIS_IMAGE_PA_H
#define POLARIS_IMAGE_PA_H
#include <math.h>
#include <stddef.h>

static int polaris_image_pa_from_cd(const double cd[2][2],
                                    int image_y_direction,
                                    double *pa_deg,
                                    int *flipped)
{
    double det, east, north, norm, angle;
    if (!cd || !pa_deg || !flipped ||
        (image_y_direction != 1 && image_y_direction != -1))
        return 0;
    if (!isfinite(cd[0][0]) || !isfinite(cd[0][1]) ||
        !isfinite(cd[1][0]) || !isfinite(cd[1][1]))
        return 0;
    det = cd[0][0] * cd[1][1] - cd[0][1] * cd[1][0];
    east = cd[0][1] * image_y_direction;
    north = cd[1][1] * image_y_direction;
    norm = hypot(east, north);
    if (!isfinite(det) || !isfinite(norm) || norm <= 0.0 ||
        fabs(det) <= 1e-12 * hypot(cd[0][0],cd[1][0]) * norm)
        return 0;
    angle = atan2(east, north) * (180.0 / 3.14159265358979323846);
    if (angle < 0.0) angle += 360.0;
    if (angle >= 360.0) angle -= 360.0;
    *pa_deg = angle;
    *flipped = det > 0.0;
    return 1;
}
#endif
