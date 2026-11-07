#!/bin/sh
# polaris-astro autostart shim (installed 2026-11-06).
#
# /app is a 68 MB UBIFS that is full, so the 22 KB boot hook cannot live there.
# This shim runs the copy on the microSD instead, which has space and survives a
# re-flash. To update Astro, replace
# /app/sd/polaris-astro/polaris-astro-boot.sh -- nothing here needs changing.
#
# bootapp runs this file at boot and it MUST NOT BLOCK; the script exec'd below
# backgrounds its entire body, so boot is not delayed.
#
# NOTE: flashing firmware replaces /app and deletes this file. Recreate it after
# any flash, or Astro will silently stop autostarting.

exec /bin/sh /app/sd/polaris-astro/polaris-astro-boot.sh
