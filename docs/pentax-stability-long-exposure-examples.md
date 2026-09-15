# Pentax long-operation examples

These examples explain why a single fixed capture timeout is unsafe. They are **not implementation constants**.

For requested shutter `T`:

- normal capture: roughly `T + readout/processing`;
- long-exposure NR: often roughly `2T + processing` because a dark exposure may follow;
- Pixel Shift: multiple physical exposures plus processing; do not assume the number of transfer candidates equals the number of physical exposures;
- Pixel Shift + NR: hardware measurement required; do not blindly multiply two assumptions;
- Bulb/astro: T itself can be many minutes.

Example: a five-minute NR exposure may legitimately keep the camera occupied for ten-plus minutes. A Pixel Shift operation using five-minute component exposures may keep the camera busy for twenty-plus minutes before additional processing. These examples establish why a 100-second generic health deadline cannot be authoritative.

The hardware experiment programme must measure actual K-3 III conditions and outputs, then validate separately on K-1 II.
