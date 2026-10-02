# o-v15h adversarial Bulb candidate — 2026-10-02

## Source and artifact identity

- Candidate: `o-v15h-adversarial-bulb-20261002`
- Build id: `6.0.0.54.51-o-v15h-adversarial-bulb`
- Patcher `main`: [`96604e38d2dc86b92f1744b6541d8252f5f4a4c9`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/commit/96604e38d2dc86b92f1744b6541d8252f5f4a4c9)
- libgphoto2 `main`: [`4e996e69c0a832a59d0852f8c872510d1b5ce361`](https://github.com/ian-morgan99/libgphoto2/commit/4e996e69c0a832a59d0852f8c872510d1b5ce361)
- ZIP MD5: `fef08d6c994d4296e7f4441ff3528c40`
- ZIP SHA-256: `0515048034ebef079322eb46528bdefdc8b6b5403cc2737cecfbf9a271ec14d7`
- appfs MD5: `e7dfc61e03dfbc9b1f9df9af4001122a`
- PrivateResearch: `firmware-packets/o-v15h-adversarial-bulb-20261002/FwPkt.zip`, commit [`3299e6675`](https://github.com/ian-morgan99/PrivateResearch/commit/3299e6675)

## Adversarial review findings and fixes

1. The previous extra-candidate reconciliation treated count/order/timing as
   ownership. That could consume an unrelated camera file. The production
   path now requires an explicit ownership proof and currently fails closed:
   an ambiguous candidate is left on the camera and the capture returns an
   error with recovery required.
2. A primary file is no longer reported as a completely successful capture
   when an expected companion output was not correlated and published. The
   primary result is preserved, but the next shutter remains blocked.
3. Companion publication now fails closed if collision probing cannot be
   performed or returns an unexpected filesystem error; it cannot silently
   publish over an uncertain name.
4. The existing Bulb display and wait changes are retained: whole seconds are
   emitted as exact `MM:SS` values (`00:04`, `00:08`, `01:10`), the value is
   parsed back losslessly, and the pre-capture timer sizes the bounded wait.
   The firmware-side Polaris patch is included from a stock base and removes
   the redundant pre-shot delay.

## Validation

- Clean libgphoto2 deterministic pack: 14/14 PASS; the serial `no-ci` fixture
  was skipped by the release script because this host has no supported DTR/CTS
  device.
- Polaris package gate: 16 container checks PASS, 26 Python checks PASS,
  package layout PASS; one stock-manifest comparison was skipped because the
  clean release clone has no stock ZIP in its working tree. The build itself
  cross-checked the supplied stock ZIP and the produced `firmwareInfo`.
- ZIP was uploaded to PrivateResearch in the same build session.

## Qualification boundary

This is a provenance-complete candidate, not a physical Bulb qualification.
TA review still requires positive same-exposure candidate ownership/format
evidence and a real K-3 III capture matrix. RAW+JPEG is intentionally
fail-closed until that evidence exists. K-1 II remains a separate
qualification.
