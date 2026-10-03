# o-v15n firmware-identity and Bulb-gate candidate

Built from the original stock `firmware/FwPkt.zip` on patcher `main`.

- Candidate: `o-v15n-fwver-strcpy-bulb-20261003`
- Build ID: `6.0.0.54.52-o-v15n-fwver-strcpy-bulb`
- Patcher: [`8e96dec`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/commit/8e96decce989af694c24313ae39c55088d85ac1e)
- libgphoto2: [`e0e5135`](https://github.com/ian-morgan99/libgphoto2/commit/e0e5135023165b9a4411bba637076b8ca1e63ed1)
- PrivateResearch: `firmware-packets/o-v15n-fwver-strcpy-bulb-20261003/FwPkt.zip`, commit `137f75dc1`
- ZIP MD5: `3f55252842ed367b0b0ab36ab439305d`
- ZIP SHA-256: `51af09b81918f8a99a85ee0df60ba4eb0f0e852fa55f572111ad8009dfd5bf8c`
- appfs MD5: `02604af91eb9704249cf5a89a46d8df4`

## Included

- exact app-visible `6.0.0.54.52` value in the package;
- safe `polestar_app` code-780 patch using the existing `strcpy` PLT call,
  avoiding the variadic `sprintf` change that caused 15m to die;
- the verified firmware Bulb pre-shot-delay patch;
- matched libgphoto2 Pentax stack from clean `main`;
- Bulb canary shutter discovery/restore tests and a release gate that fails
  when code 780 returns the wrong version instead of treating that as SKIP.

## Build evidence

- libgphoto2 tests: `14/14` passed;
- package/display regression from stock: passed;
- deterministic patcher harness: `17 passed, 0 failed, 2 skipped`;
- Python suite: `132 passed`;
- package/release gate: `5 passed, 0 failed, 0 skipped`;
- shipped `firmwareInfo` and structural checks: passed;
- private artifact upload: passed.

## Boundary

This is a candidate, not a physical qualification. It has not been staged or
installed on Polaris. The live code-780 response, reboot persistence, and the
K-3 III Manual/Bulb RAW/JPEG/RAW+JPEG/cancellation/recovery matrix are still
required. The candidate does not claim that the unsafe generic K-3 III
held-shutter libgphoto2 action is supported.
