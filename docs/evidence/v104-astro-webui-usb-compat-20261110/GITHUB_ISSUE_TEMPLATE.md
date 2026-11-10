# GitHub Issue: Astro webui comes up even when USB compatibility mode is off

**Title:** Astro webui comes up even when USB compatibility mode is off

**Labels:** bug, v104, astro, usb-compatibility

**Device:** Benro Polaris, FwVer:6.0.0.54.104, date:2026.11.10, build_id=v104

---

## Summary

The Astro web UI comes up even when USB compatibility mode is turned off. The original intent was that the USB compatibility mode would control whether the Astro web UI is enabled or disabled.

## Observed Behavior

- USB compatibility mode is OFF
- Astro web UI still comes up/is accessible

## Expected Behavior

- When USB compatibility mode is OFF, the Astro web UI should NOT be accessible/should not come up
- The Astro web UI should only be available when USB compatibility mode is explicitly enabled

## Steps to Reproduce

1. Set USB compatibility mode to OFF on the Polaris
2. Attempt to access the Astro web UI
3. Observe that the Astro web UI is still accessible despite USB compatibility mode being off

## Expected Behavior

- Astro web UI should not be accessible when USB compatibility mode is OFF

---

**Note:** This is v104 test evidence. The device is running build_id=v104, display_fwver=6.0.0.54.104.