# o-v15i matched Pentax Bulb deployment

Status: **INSTALLED; physical camera validation pending**

Candidate `o-v15i-pentax-bulb-matched-20261002` was built from pristine stock
firmware and clean `libgphoto2` `main`, privately archived, staged through the
mounted SD card, and installed by the normal boot-time updater.

- Build id: `6.0.0.54.52-o-v15i-pentax-bulb-matched`
- Displayed firmware version: `6.0.0.54.52`
- libgphoto2: `6979070597ebddbaa5f1cff1e56b7597e4594ed2`
- patcher build input: `d94767291c36b6dee9086490a2e9ae04ae88bd94`
- ZIP MD5: `4ddbe3754fc7832750f0ee6b895fe616`
- ZIP SHA-256: `d4623510357125e25c2e9a7c512bae238a686e1e5eab3db47d66956f0bfb0e75`
- appfs MD5: `e10d206ce758f6d534677f881557cd6c`
- PrivateResearch artifact commit: `77dc1ee0e`

Offline gates were green: libgphoto2 `14/14`, deterministic patcher `16
passed / 2 skipped`, Python regression suite `121 passed`, and package gates
`4/4`.

The post-install runtime identity and all matched Stage-2 component hashes
were verified. The camera was not connected (`lsusb` contained no `25fb`
device), so no capture or Bulb canary was attempted.
