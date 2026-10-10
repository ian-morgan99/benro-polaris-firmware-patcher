#!/usr/bin/env python3
"""Verify that a polestar_app binary does not contain the disproven Bulb patch."""
import sys

ANCHOR = bytes.fromhex("1c301be5 fa2fa0e3 920303e0 1c300be5")
DISABLED_PATCH = bytes.fromhex("1c301be5 0030a0e3 000000e1 1c300be5")


def main():
    if len(sys.argv) != 2:
        print("usage: polestar_bulb_patch.py <polestar_app>", file=sys.stderr)
        return 2
    with open(sys.argv[1], "rb") as firmware:
        data = firmware.read()
    anchor_count = data.count(ANCHOR)
    patch_count = data.count(DISABLED_PATCH)
    if anchor_count == 1 and patch_count == 0:
        print("[polestar_bulb_patch] safe: original Bulb duration branch is intact")
        return 0
    if patch_count:
        print(
            "[polestar_bulb_patch] FATAL: retired patch found; it zeros bulb_ms "
            "and routes requests to plain capture",
            file=sys.stderr,
        )
    else:
        print(
            "[polestar_bulb_patch] FATAL: expected one original Bulb branch "
            f"(found {anchor_count}); refusing an unverified firmware binary",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
