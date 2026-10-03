# o-v15l firmware-version and Bulb candidate

Status: **BUILT; PRIVATELY ARCHIVED; NOT INSTALLED**

This is a stock-based rebuild after finding the 15k version-display defect.
The exact code-780 patch must calculate the ARM PC-relative address from the
`ADD` instruction at `0x13fb84`; `0x00917798` therefore resolves to the
standalone `%s` at `0xa57324`. 15k used `0x0091779c`, which resolved to the
following date format and caused Benro Connect to receive an unusable version
value, displayed as `null`.

## Build identity

- Candidate: `o-v15l-fwver-bulb-20261003-r2`
- Build ID: `6.0.0.54.52-o-v15l-fwver-bulb-r2`
- Patcher `main`: `7dd5ca4d9bb7cdfa9d10ff570bdef15bb8acd33e`
- libgphoto2 `main`: `e0e5135023165b9a4411bba637076b8ca1e63ed1`
- Display/FwVer: `6.0.0.54.52`
- PrivateResearch artifact commit: `a91dbe62c6ac44d4c39faf9d9672bbfe984e8abb`
- PrivateResearch path: `firmware-packets/o-v15l-fwver-bulb-20261003-r2/FwPkt.zip`

## Artifact hashes

- ZIP MD5: `71b6bf98b8fb0e90a220179ae9c5cd0b`
- ZIP SHA-256: `a15e564773230375270ccc0f0210b976fa1715e8963059719a872dfd6a7f60ad`
- appfs MD5: `cef86481bd27ab96f21b60fb094f3ee5`

## Validation

- libgphoto2 regression pack: `14/14 passed`
- patcher deterministic harness: `17 passed`
- Python regression suite: `125 passed`
- package structure: passed
- firmwareInfo manifest against shipped bytes: passed
- exact code-780 target after appfs repack: passed
- Bulb marker after appfs repack: passed
- pre-release gate: `4 passed, 0 failed, 1 skipped` (stock firmware manifest
  cross-check unavailable inside the clean release checkout)
- physical Polaris installation/camera validation: **NOT TESTED**
