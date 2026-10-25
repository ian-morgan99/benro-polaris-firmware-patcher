#!/usr/bin/env bash
# Offline unit test for the pgphoto post-release file-poll budget patch (issue #230).
# Runs on the host with no container, no qemu and no camera: patch_data() works on bytes.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHONPATH="$ROOT/container" python3 - <<'PY'
import struct

import polaris_bulb_poll_budget_patch as patch


def check(condition, message):
    if not condition:
        raise SystemExit("FAIL: %s" % message)
    print("PASS: %s" % message)


# ---------------------------------------------------------------- encoders
# Two MOVWs lifted from the analysed pgphoto, so the layout is pinned to real bytes rather
# than to a reading of the manual.
check(patch.encode_movw(3, 0xC8D) == 0xE3003C8D, "encode_movw reproduces movw r3,#0xc8d")
check(patch.encode_movw(3, 0x4DD3) == 0xE3043DD3, "encode_movw reproduces movw r3,#0x4dd3")
check(patch.decode_movw(0xE3003C8D) == (3, 0xC8D), "decode_movw round-trips movw r3,#0xc8d")
check(patch.decode_movw(0xE3A03F96) is None, "decode_movw rejects a plain mov")
check(patch.decode_mov_immediate(0xE3A03F96) == (3, 600),
      "decode_mov_immediate reads the stock budget as mov r3,#600")
check(patch.decode_mov_immediate(0xE3A03002) == (3, 2),
      "decode_mov_immediate reads the fast path as mov r3,#2")
check(patch.decode_movw(patch.encode_movw(3, 10000)) == (3, 10000),
      "replacement budget round-trips to movw r3,#10000")

# ---------------------------------------------------------------- synthetic binary
# The stock instruction sequence at gpManager.c:3308, surrounded by unrelated code that
# contains a decoy `mov r3, #600` with the wrong context.
FUNCTION_ADDRESS = 0x2000
FUNCTION_OFFSET = 0x1000
SITE_INDEX = 6

words = [
    0xE51B201C,   # ldr  r2, [fp, #-0x1c]   files seen so far
    0xE51B3024,   # ldr  r3, [fp, #-0x24]   expected file count
    0xE1520003,   # cmp  r2, r3
    0xBA000001,   # blt  <long budget>
    0xE3A03002,   # mov  r3, #2             fast path
    0xEA000000,   # b    <store>            the skipping branch
    0xE3A03F96,   # mov  r3, #0x258         <-- the budget site
    0xE50B3014,   # str  r3, [fp, #-0x14]
    0xE51B3020,   # ldr  r3, [fp, #-0x20]
]
decoy = [0xE3A03F96, 0xE3A03002, 0xE50B3014]   # mov r3,#600 with the wrong neighbours

data = bytearray()
data += b"\x00" * FUNCTION_OFFSET
data += struct.pack("<9I", *words)
data += struct.pack("<3I", *decoy)
target = {"address": FUNCTION_ADDRESS, "size": len(data) - FUNCTION_OFFSET,
          "offset": FUNCTION_OFFSET}

patched, changed, detail = patch.patch_data(bytes(data), target)
check(changed, "stock-shaped binary gets patched")
check(detail["address"] == FUNCTION_ADDRESS + SITE_INDEX * 4,
      "site resolved to the budget instruction, not the decoy")
diff = [i for i in range(len(data)) if data[i] != patched[i]]
check(len(diff) == 3, "exactly three bytes change (mov -> movw keeps one byte identical)")
check(struct.unpack_from("<I", patched, target["offset"] + SITE_INDEX * 4)[0]
      == patch.encode_movw(3, patch.NEW_WAIT_ITERATIONS),
      "budget becomes movw r3,#%d" % patch.NEW_WAIT_ITERATIONS)
check(patched[target["offset"] + 4 * 4:target["offset"] + 5 * 4]
      == data[target["offset"] + 4 * 4:target["offset"] + 5 * 4],
      "fast path mov r3,#2 is untouched")
check(len(patched) == len(data), "binary size is unchanged")
check(patch.NEW_WAIT_ITERATIONS * patch.POLL_INTERVAL_MS // 1000 == 100,
      "budget is 100 s of polling")

# ---------------------------------------------------------------- idempotency
again, changed_again, _ = patch.patch_data(patched, target)
check(not changed_again, "already-patched binary is reported unchanged")
check(again == patched, "re-running the patch is a no-op")

# ---------------------------------------------------------------- fail closed
missing = bytearray(data)
struct.pack_into("<I", missing, target["offset"] + SITE_INDEX * 4, 0xE3A03FFF)
try:
    patch.patch_data(bytes(missing), target)
    raise SystemExit("FAIL: unrecognised budget should be refused")
except ValueError as error:
    check("exactly one" in str(error), "unrecognised budget fails closed")

duplicated = bytearray(data)
duplicated += struct.pack("<3I", 0xEA000000, 0xE3A03F96, 0xE50B3014)
try:
    patch.patch_data(bytes(duplicated), dict(target, size=len(duplicated) - FUNCTION_OFFSET))
    raise SystemExit("FAIL: ambiguous site should be refused")
except ValueError as error:
    check("found 2" in str(error), "two candidate sites fail closed")

# The hold bound must never be the thing that moves: it is a float compare, not this word.
check(patch.STOCK_WAIT_BUDGET != 0xE3A03F96 or patch.decode_mov_immediate(
    patch.STOCK_WAIT_BUDGET)[1] == 600, "budget constant still describes the stock 600")

print("[test_polaris_bulb_poll_budget_patch] ALL PASS")
PY

# ---------------------------------------------------------------- real binary
# The analysed pgphoto is not committed, so this half is skipped when it is absent.
PGPHOTO="$ROOT/out/o-v17d-darkframe-budget-20261023/stage2-ondisk/ondisk/pgphoto.stage2ondisk"
if [ -f "$PGPHOTO" ]; then
  WORK="$(mktemp -d)"
  trap 'rm -rf "$WORK"' EXIT
  cp "$PGPHOTO" "$WORK/pgphoto"
  python3 "$ROOT/container/polaris_bulb_poll_budget_patch.py" "$WORK/pgphoto" --in-place
  CHANGED="$( { cmp -l "$PGPHOTO" "$WORK/pgphoto" || true; } | wc -l | tr -d ' ')"
  [ "$CHANGED" = "3" ] || { echo "FAIL: real binary changed $CHANGED bytes, expected 3"; exit 1; }
  echo "PASS: real pgphoto changed exactly 3 bytes"
  python3 "$ROOT/container/polaris_bulb_poll_budget_patch.py" "$WORK/pgphoto" --check
  echo "PASS: gate accepts the patched real binary"
  python3 "$ROOT/container/polaris_bulb_poll_budget_patch.py" "$PGPHOTO" --check \
    && { echo "FAIL: gate accepted an unpatched binary"; exit 1; } || true
  echo "PASS: gate rejects the unpatched real binary"
else
  echo "SKIP: analysed pgphoto not present, real-binary checks skipped"
fi
