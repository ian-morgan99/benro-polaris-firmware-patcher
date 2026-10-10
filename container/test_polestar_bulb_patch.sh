#!/bin/sh
# Ensure the disproven zero-bulb patch cannot be applied or shipped.
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT HUP INT TERM

python3 - "$work" "$here" "$root" <<'PY'
import os
import subprocess
import sys

work, here, root = sys.argv[1:]
script = os.path.join(here, "polestar_bulb_patch.py")
test_bin = os.path.join(work, "polestar_app")
anchor = bytes.fromhex("1c301be5 fa2fa0e3 920303e0 1c300be5")
retired = bytes.fromhex("1c301be5 0030a0e3 000000e1 1c300be5")
filler = b"\x00" * 64

def run(path):
    return subprocess.run([sys.executable, script, path], capture_output=True, text=True)

def check(name, cond):
    print(("  PASS: " if cond else "  FAIL: ") + name)
    if not cond:
        sys.exit(1)

with open(test_bin, "wb") as firmware:
    firmware.write(filler + anchor + filler)
before = open(test_bin, "rb").read()
result = run(test_bin)
after = open(test_bin, "rb").read()
check("original branch passes audit without modification", result.returncode == 0 and before == after)

with open(test_bin, "wb") as firmware:
    firmware.write(filler + retired + filler)
before = open(test_bin, "rb").read()
result = run(test_bin)
after = open(test_bin, "rb").read()
check("retired patch fails audit without modification", result.returncode == 1 and "routes requests to plain capture" in result.stderr and before == after)

for path in ("scripts/build-release-candidate.sh", "patch-polaris.sh", "container/patch.sh"):
    with open(os.path.join(root, path), encoding="utf-8") as source:
        text = source.read()
    check(f"{path} does not request retired patch", "--polestar-bulb-patch" not in text and "POLESTAR_BULB_PATCH" not in text)

print("[test_polestar_bulb_patch] ALL PASS")
PY
