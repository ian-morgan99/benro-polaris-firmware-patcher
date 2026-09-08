# Pentax generic-control compatibility on Benro Polaris

Revision: 2026-09-08

The Polaris `pgphoto` integration exposed an important libgphoto2 compatibility gap: it asks for the generic widget vocabulary used by established libgphoto2 clients (`aperture`, `imageformat`, `imagequality`, `autofocusdrive`, `manualfocusdrive`, `manualfocus`, `capturetarget`), while the newer Pentax ptp2 work sometimes exposes the underlying capability only through Pentax-specific names.

The normative protocol/API analysis now lives in `ian-morgan99/libgphoto2` at `docs/pentax/GENERIC_CONTROL_COMPATIBILITY_AUDIT.md` and issue #51. Implementation fixes belong in libgphoto2 unless the failure is specifically a Polaris runtime/packaging problem.

## Polaris responsibilities

- Preserve raw Clog evidence of the exact widget names requested and return codes.
- After each libgphoto2 compatibility change, package the exact tested libgphoto2 SHA through the Stage-2/release-gate path and prove artifact provenance.
- Re-run K-3 III and K-1 II separately; do not infer K-1 II behaviour from K-3 III.
- Treat K-01 as two separate paths: legacy `25fb:0130` USB-SCSI (`camlibs/pentax`) and `25fb:0131` generic PTP/MTP (`ptp2`). The Stage-2 package currently centres on ptp2, so full legacy K-01 support requires explicit packaging/runtime design rather than assuming the ptp2 plugin supplies it.
- Do not patch `pgphoto` to translate Pentax-specific names into generic names unless a libgphoto2 fix is impossible; generic API compatibility belongs in libgphoto2.
- Do not map `pentaxcardwritingmode` to `imageformat`: card-writing mode is slot selection, not JPEG/RAW format.
- Do not map Pentax manual near/far focus directly to `autofocusdrive`: autofocus policy/action/manual-drive are distinct semantics.

## Acceptance evidence per control

For each generic control fixed in libgphoto2, collect on-device evidence showing: exact firmware/patcher/libgphoto2 provenance; config-tree presence; pgphoto lookup success; GET/SET/action result as applicable; independent read-back or visible effect where safe; reconnect/restart behaviour; and no regression to Canon/Nikon/other stock camera paths.

The libgphoto2 hardware matrix remains the authority for camera-support claims. Polaris evidence is the integration confirmation, not a substitute for direct source-repo hardware tests.
