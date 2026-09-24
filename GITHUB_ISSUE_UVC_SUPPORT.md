<!-- 
This file represents a GitHub issue that should be created in the BenroPolarisPatcher repository.
Content follows standard GitHub issue format.
-->

# Feature Request: Expand libgphoto2 support to include UVC devices (e.g. iOptron iPolar)

## Description
Currently, the BenroPolarisPatcher repository builds a minimal libgphoto2 stack focused exclusively on PTP camera control for Pentax devices. The build process intentionally limits camlibs to only `ptp2,pentax` to minimize dependencies and footprint.

However, there is a desire to expand functionality to support UVC (USB Video Class) devices after Pentax qualification is complete. This would enable support for devices like the iOptron iPolar (an electronic polar alignment scope for telescopes) that enumerate as standard UVC webcams.

## Motivation
- libgphoto2 has included native UVC support since version 2.5.0 (2016)
- The iOptron iPolar was discovered connected to the Polaris gimbal's USB port and functions as a standard UVC webcam
- Expanding support would increase the versatility of the patcher beyond Pentax-specific use cases
- This aligns with the repository's principle that "camera capability truth is owned by the corresponding libgphoto2 source"

## Proposed Solution
### 1. Build Configuration Changes
Modify the build process in `container/build_ptp2.sh` and related scripts to include UVC camlib:
```bash
# Change from:
--with-camlibs=ptp2,pentax
# To:
--with-camlibs=ptp2,pentax,uvc[,others...]
```

### 2. Device Support Addition
Add the iOptron iPolar device ID to the UVC device table in libgphoto2 source:
```c
// In camlibs/uvc/uvc-devices.c
{0x1233, 0x1455, "iOptron", "iPolar", NULL, NULL, 0, 0, 0},
```

### 3. Testing & Validation
- Verify existing PTP camera functionality remains intact
- Test iOptron iPolar detection: `gphoto2 --auto-detect`
- Evaluate device capabilities: `gphoto2 --summary`
- Assess footprint impact and dependency requirements
- Consider if additional quirks are needed for specific UVC devices

## Device Details: iOptron iPolar
- **Vendor ID**: 1233 (0x4D1) - Denver Electronics
- **Product ID**: 1455 (0x5AF) - iOptron iPolar
- **USB Class**: Video (UVC - USB Video Class)
- **Interfaces**: 
  - Interface 0: Video Control (UVC 1.00)
  - Interface 1: Video Streaming (Uncompressed Y16 format)
- **Resolutions**: 640×960 (~1.8 fps) and 1280×960 (~0.9 fps) per USB descriptors
- **Current System**: Enumerates as `/dev/video0` and `/dev/video1`

## Testing Results (Host)
Using OpenCV on the host system:
- Successfully opened `/dev/video1`
- Captured frames at 960×640×3 (BGR888 via OpenCV conversion)
- Frame rate ~18 FPS observed
- Saved test frame demonstrating basic functionality

## Related Documentation
- `docs/FUTURE-UVC-SUPPORT.md` - Expansion plan and considerations
- `IOPTRON_IPOLAR_TEST_SUMMARY.md` - Technical test results
- Container build scripts in `container/` directory
- `docs/LIBGPHOTO2-UPGRADE-PROCESS.md` - For updating libgphoto2 versions

## Definition of Done
- [ ] Build process updated to include UVC camlib
- [ ] iOptron iPolar device ID added to uvc-devices.c
- [ ] Expanded libgphoto2 stack built and tested
- [ ] Existing PTP camera functionality verified intact
- [ ] iOptron iPolar detectable and operable via gphoto2
- [ ] Footprint impact assessed and documented
- [ ] Dependency requirements verified

## Notes
This is not a limitation of libgphoto2 itself, but rather a scope limitation of our current custom build process. Expanding to include UVC support simply brings our packaged stack closer to upstream libgphoto2's feature set.

The work should be scheduled after Pentax camera qualification is complete and the core patcher workflow is validated.