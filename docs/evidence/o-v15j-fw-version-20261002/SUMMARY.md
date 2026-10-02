# o-v15j firmware-version candidate — withdrawn

Status: **WITHDRAWN — DO NOT STAGE**

Static adversarial review found that the generated ARM PC-relative format
literal is four bytes short. The code-780 patch therefore points at `0xa57320`
(`"/\0"`) instead of the intended standalone `%s` at `0xa57324`. The source
patch has been corrected and the regression test now checks the resolved
target address. The operator has reported an unrecoverable failure after
using this candidate; that boot failure is not attributed solely to this
format-string defect without device logs.

This candidate fixes the long-running Benro Connect version mismatch.

## Root cause

`/app/FwVer` and protocol code 780 were not the same version source. The stock
`polestar_app` calculated code 780 `sw` by adding gimbal `2.0.0.22` to the
first four camera-version fields. Thus a camera value of `6.0.0.54` appeared
as `8.0.0.76`, and a fifth component such as `.52` was ignored.

## Change

The patcher now fail-closed patches the unique `SP_GetDeviceVer` version
formatter so code 780 uses the raw camera-version string. The package and
appfs both carry:

```text
FwVer:6.0.0.54.52;
```

The formal release path also now actually applies the existing firmware-side
Bulb pre-shot-delay patch, which had been requested by the build wrapper but
was no longer wired into `container/patch.sh`.

## Build evidence

- patcher main: `065fca4`
- libgphoto2 main: `6979070597ebddbaa5f1cff1e56b7597e4594ed2`
- ZIP MD5: `d30bd6428c1af3e1b18b46a088cf3266`
- ZIP SHA-256: `88600426531627a96c8f4c866316d420e4cf478ac4a8cc25e3d6d940965d4ac2`
- appfs MD5: `238ab41aa77d958cd7e9276d696eead1`
- PrivateResearch artifact commit: `2e95bdd0c`
- libgphoto2 tests: `14/14` passed
- patcher/package gate: `4 passed, 0 failed, 0 skipped`
- exact-version patch regression: fresh patch and idempotent re-run passed
- Bulb patch regression: all checks passed

Physical camera validation is still pending; this document does not claim a
camera capture canary.
