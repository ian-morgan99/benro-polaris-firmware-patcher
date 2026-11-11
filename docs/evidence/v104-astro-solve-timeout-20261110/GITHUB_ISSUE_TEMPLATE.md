# GitHub Issue: v104 — Add logging for astrometry/solve function to diagnose timeout failures

**Title:** [v104] Add logging for astrometry/solve function to diagnose timeout failures

**Labels:** bug, v104, astro, solve, logging

**Device:** Benro Polaris, FwVer:6.0.0.54.104, date:2026.11.10, build_id=v104

---

## Summary

On v104, the astrometry/solve function times out during capture, but there is no logging to diagnose why. The Polaris mlog/clog only captures the camera stack (pgphoto, ptp2, stage2), not the application's solve function. Without logging, we cannot determine whether the solve is:

- Timing out due to CPU/memory constraints
- Failing due to image quality (too few stars, poor focus)
- Hitting a hard timeout threshold
- Eventually completing if given more time

## Observed Behavior

- Solve function times out without any diagnostic output
- No logging of start time, end time, or duration
- No logging of image resolution, star count, or other capture metadata
- No correlation between camera activity and solve timing

## Expected Behavior

- Log solve start time, end time, and duration
- Log image resolution, star count, and other capture metadata
- Log timeout threshold and whether it was exceeded
- Correlate solve timing with camera stack activity (pgphoto, ptp2, stage2)

## Steps to Reproduce

1. Connect K1 II or K3 III to Polaris running v104
2. Initiate an astrometry/solve capture
3. Observe that the solve times out without any diagnostic output
4. No logs available to diagnose why

## Expected Behavior

- Solve logs start time, end time, and duration
- Solve logs image resolution, star count, and other metadata
- Solve logs timeout threshold and whether it was exceeded
- Correlate solve timing with camera stack activity

## Files

No existing logs exist for solve/astrometry. The v104 evidence directories contain only camera stack logs (mlog/clog from pgphoto, ptp2, stage2).

## Related Issues

- #315: [v104] K1 II Android: capture process overhead ~14.6s for 0.4s exposure, duration reported as 0
- #317: [v104] K-3 III: Bulb mode capture actuates but reports transaction failed, no image file saved

---

**Note:** This is v104 test evidence. The device is running build_id=v104, display_fwver=6.0.0.54.104, libgphoto2 commit=806c3bda62d6c0c23ca7a3091fb42f3d7894172b, patcher commit=1e88637cf61d152f94e23f6e139adec4b9fa80c2.