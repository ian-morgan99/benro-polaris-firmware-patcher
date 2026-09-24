<!-- 
This file represents a GitHub issue that should be created in the BenroPolarisPatcher repository.
Content follows standard GitHub issue format.
-->

# Feature Request: Add support for Orion Starshoot All-in-One (QHY5L-II clone) to libgphoto2

## Description
The Orion Starshoot All-in-One is a rebranded QHY5L-II hardware clone used for astronomical autoguiding and imaging. Like the iOptron iPolar, it enumerates as a standard UVC (USB Video Class) webcam but requires its specific USB ID to be added to libgphoto2's UVC device table for proper recognition and support.

## Motivation
- libgphoto2 has included native UVC support since version 2.5.0 (2016)
- Astronomical cameras like the Orion Starshoot All-in-One are commonly used with guiding software
- Adding support would increase the versatility of the patcher for astronomical use cases
- This follows the same pattern as the iOptron iPolar support request (Issue #135)

## Proposed Solution
### 1. Build Configuration Changes
Modify the build process in `container/build_ptp2.sh` and related scripts to include UVC camlib (if not already added for iOptron iPolar):
```bash
# Ensure this includes uvc:
--with-camlibs=ptp2,pentax,uvc[,others...]
```

### 2. Device Support Addition
Add the Orion Starshoot All-in-One device ID to the UVC device table in libgphoto2 source:
```c
// In camlibs/uvc/uvc-devices.c
{VID_ORION_STARSHOOT_ALLINONE, PID_ORION_STARSHOOT_ALLINONE, "Orion", "Starshoot All-in-One", NULL, NULL, 0, 0, 0},
```
Where the actual IDs need to be determined from the device.

### 3. Testing & Validation
- Verify existing PTP camera functionality remains intact
- Test device detection: `gphoto2 --auto-detect`
- Evaluate device capabilities: `gphoto2 --summary`
- Test basic operations and image capture if applicable
- Assess footprint impact and dependency requirements

## Device Identification Needed
To complete this issue, we need to:
1. Physically connect the Orion Starshoot All-in-One device
2. Run `lsusb` to get the exact USB Vendor ID and Product ID
3. Verify it functions as a UVC device
4. Add the correct IDs to the libgphoto2 UVC device table

## Related Work
- This follows the same approach as the iOptron iPolar support (Issue #135)
- Both devices are astronomical USB cameras that should work with standard UVC drivers
- libgphoto2's UVC support is mature and well-tested

## Definition of Done
- [ ] Orion Starshoot All-in-One device IDs identified via lsusb
- [ ] Build process confirmed to include UVC camlib
- [ ] Device IDs added to uvc-devices.c
- [ ] Expanded libgphoto2 stack built and tested
- [ ] Existing PTP camera functionality verified intact
- [ ] Orion Starshoot All-in-One detectable and operable via gphoto2
- [ ] Basic functionality validated (detection, summary, etc.)

## Notes
This issue should be considered alongside Issue #135 (iOptron iPolar support) as both relate to expanding UVC device support for astronomical cameras. The work can be done together when expanding libgphoto2's UVC support beyond the current Pentax-focused build.

The device is expected to work with minimal changes since it's a QHY5L-II clone, and the QHY5L-II series may already be supported in libgphoto2 - we just need to add this specific vendor/product ID variant.