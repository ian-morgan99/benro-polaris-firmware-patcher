# firmware/

This directory holds the **stock Benro Polaris firmware ZIP** that
the build scripts consume as input. It is **not committed** to this
repository (see `.gitignore` patterns `FwPkt*.zip`, `*.ubifs`,
`*.bin`).

## How to populate

Drop the user-supplied stock FwPkt into this directory as
`firmware/FwPkt.zip` before running the build. The build
expectations and provenance for the stock file are recorded in
[`firmware/SOURCE.md`](SOURCE.md).

## Patched output

Patched FwPkt ZIPs are written under `builds/` (also gitignored)
and tagged via the `v0.3.0-...` annotated tag sequence recorded in
`CHANGELOG.md`. The combined Pentax+HDMI 720p60 build is at
`builds/2026-08-27-combined-720p60/FwPkt.zip` per the
`v0.3.0-pentax-hdmi-combined-720p60` tag.
