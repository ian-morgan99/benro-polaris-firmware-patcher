# Future Work: UVC Support Expansion

## Current Limitation
The BenroPolarisPatcher repository intentionally builds a minimal libgphoto2 stack focused solely on PTP camera control for Pentax devices. The build process in `container/build_ptp2.sh` explicitly limits camlibs to:

```bash
--with-camlibs=ptp2,pentax
```

This excludes UVC (USB Video Class) support and other camlibs to:
- Minimize dependencies and build complexity
- Keep the on-device footprint small for the Polaris gimbal
- Maintain binary compatibility with pgphoto expectations
- Reduce attack surface in the embedded environment

## Planned Expansion
After completing Pentax camera qualification and validation of the core patcher workflow, we plan to expand libgphoto2 support to include additional camlibs. This will involve:

1. **Modifying the build configuration** to include UVC and other relevant camlibs:
   ```bash
   --with-camlibs=ptp2,pentax,uvc[,others...]
   ```

2. **Adding device support** for specific UVC devices like the iOptron iPolar:
   - Add device ID `0x1233:0x1455` to `camlibs/uvc/uvc-devices.c`
   - Test and potentially add quirks if needed
   - Verify video capture functionality works

3. **Testing the expanded stack** to ensure:
   - Existing PTP camera functionality remains intact
   - New UVC devices are properly detected and usable
   - The increased footprint is acceptable for target devices

## Specific Device: iOptron iPolar
The iOptron iPolar (an electronic polar alignment scope for astronomical telescopes) was identified during testing:
- **Vendor ID**: 1233 (0x4D1) - Denver Electronics
- **Product ID**: 1455 (0x5AF) - iOptron iPolar
- **Device Class**: Video (UVC - USB Video Class)
- **Interfaces**: Video Control + Video Streaming
- **Format**: Uncompressed Y16 (16-bit grayscale)
- **Resolutions**: 640×960 (~1.8 fps) and 1280×960 (~0.9 fps)
- **Notes**: Video-only device, no still image capture supported

## Implementation Steps
When ready to expand scope:

1. Update `container/build_ptp2.sh` and related build scripts to include `uvc` in `--with-camlibs`
2. Add the device entry to `libgphoto2-source/camlibs/uvc/uvc-devices.c`:
   ```c
   {0x1233, 0x1455, "iOptron", "iPolar", NULL, NULL, 0, 0, 0},
   ```
3. Test with the iOptron iPolar connected:
   ```bash
   # Using locally built libraries
   CAMLIBS=/path/to/libgphoto2/.libs \
   IOLIBS=/path/to/libgphoto2_port/.libs \
   gphoto2 --auto-detect
   
   CAMLIBS=/path/to/libgphoto2/.libs \
   IOLIBS=/path/to/libgphoto2_port/.libs \
   gphoto2 --summary
   ```
4. Verify video capture capabilities if needed for the use case

## Dependencies Consideration
Enabling UVC may require ensuring:
- Proper USB video stack availability
- Any additional libraries needed for video format handling
- That the increased binary size remains acceptable for target deployment

## Relation to Existing Work
This expansion aligns with the repository's principle that:
> "Camera capability truth is owned by the corresponding libgphoto2 source and its hardware evidence."

Our current build is a purposeful subset for Pentax development, not a reflection of libgphoto2's full capabilities. Expanding the supported camlibs simply brings our packaged stack closer to upstream libgphoto2's feature set.

---
*This document tracks planned future work. Do not consider this as a limitation of libgphoto2 itself, which has included UVC support since version 2.5.0.*