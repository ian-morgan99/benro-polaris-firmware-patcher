# o-v13b direct-admission replacement

Status: **INSTALLED; RUNTIME PROVENANCE VERIFIED; CAMERA CANARY PENDING**

## Why o-v13 was superseded

The installed o-v13 candidate passed deterministic/package gates but failed two
bounded live canaries. Preview stop and code-264 admission succeeded, yet the
physical shutter did not fire, no completion or 773 file arrived, and the
camera session ended at `state:-10`. Runtime logs showed that o-v13 still
installed the Stage-2 `gp_camera_capture` shim and never reached the new
libgphoto2 admission/InitiateCapture instrumentation. No second shutter was
sent. This assigns the first divergence to patcher/Stage-2 integration.

o-v13b integrates patcher commit `073f471` on the convergence branch so still
capture uses the exact resolved core target. Readiness and output ownership
remain in libgphoto2.

## Exact inputs

- patcher: `28c1a78bec5ac0909f28c75a41cb4c7e57b961c9` (clean)
- libgphoto2: `50ba504152fe5c7bc8d3576acc4b643828db1de8` (clean standalone clone)
- harness: `a8b65817354dae04f997d1357d7d4914e396c42f`
- build id: `6.0.0.54.26-o-v13b-direct-admission`
- full matched-stack mode; libgphoto2 2.5.34; port 0.12.2; 256 MiB Pentax capture cap; no polestar Bulb patch

## Deterministic and package evidence

- patcher offline gate: 12 container checks + 15 Python tests PASS
- package gate: the same tests plus FwPkt structural validation PASS
- stock-manifest subgate: SKIP because the clean worktree has no stock bytes;
  the build independently verified all six shipped `firmwareInfo` entries
- build failed closed once against a Git-worktree source whose `.git` pointer
  was unavailable in the container; no artifact was produced from that run
- successful build used clean standalone libgphoto2 SHA `50ba504152...`

## Artifact

- zip MD5: `f352f093142ca3f8ce95cac4828b9733`
- zip SHA-256: `b274ef0fdd248a0577394232cde3c2824b46a88ae8599204074dd5f059e2672d`
- appfs MD5: `af18a5cefc9ea3688e93b861b1d05eea`
- appfs SHA-256: `7321a831fe91756202c733ce15ef5327adbbba32f35ae253300bc7eda919034c`
- loader MD5: `cb8a42ab7f8750dddc4dc09e1a83aca4`
- pgphoto MD5: `06a64f846887d40988968009f7698357`
- core/port/ptp2/usb1 MD5: `5973e8c8999b1f4f01be70a9cafdb7ba` / `ad50e83594397aef48b63ed2375890cc` / `ec55c405049ceae290bfa358c19c40eb` / `4423bba29bf8c5d899598841ec3e6310`

## Remaining minimum physical acceptance

The complete tree was staged and all six on-card sizes/MD5s matched
`firmwareInfo`. After the sanctioned reboot, `/app/FwVer` reported the expected
build ID and embedded provenance reported libgphoto2 `50ba504152...` and patcher
`28c1a78bec...`; uptime reset proved the reboot. Run one canary next. Only after
lifecycle completion and one 773 file may the two-shot admission test run.
Stop on any first-shot failure.
