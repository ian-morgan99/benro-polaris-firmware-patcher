#!/usr/bin/env python3
"""Confirm the AF fix (#359) is present in a given config.c, and that its scope
is limited to the autofocusdrive getter.

The fix removes `pentax_model_supports_pc_live_view(...)` from
_get_Pentax_AutofocusDrive so the widget exists on old-focus bodies (K-1 II, K-1),
and moves rejection to set time gated on af_mode instead.

Other functions legitimately still gate on PC live view (live-view get/set), so a
repo-wide grep for the symbol is not a valid check -- it must be scoped per function.
"""
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "camlibs/ptp2/config.c"
src = open(path, encoding="utf-8", errors="replace").read()


def func_body(name):
    m = re.search(rf"\n{name}\s*\(CONFIG_GET_ARGS\)\s*\{{", src)
    if not m:
        m = re.search(rf"\n{name}\s*\(CONFIG_SET_ARGS\)\s*\{{", src)
    if not m:
        return None
    i = src.index("{", m.start())
    depth, j = 0, i
    while j < len(src):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
        j += 1
    return None


get = func_body("_get_Pentax_AutofocusDrive")
set_ = func_body("_set_Pentax_AutofocusDrive")
if get is None:
    print("FAIL: _get_Pentax_AutofocusDrive not found")
    sys.exit(1)

ok = True
if "pentax_model_supports_pc_live_view" in get:
    print("FAIL: getter still gates on PC live view (widget hidden on K-1 II)")
    ok = False
else:
    print("OK: getter no longer gates on PC live view -> widget exists on old-focus bodies")

if "supported_model" not in get or "vendor_mode_enabled" not in get:
    print("FAIL: getter dropped the supported_model/vendor_mode preflight")
    ok = False
else:
    print("OK: getter keeps supported_model + vendor_mode preflight")

if set_ is not None:
    if "af_mode" in set_:
        print("OK: setter gates on af_mode (IT2's own CamAutoFocus condition)")
    else:
        print("FAIL: setter does not gate on af_mode -- AF could be sent with AF off")
        ok = False

print("VERDICT:", "fix present and correctly scoped" if ok else "FIX NOT VERIFIED")
sys.exit(0 if ok else 1)
