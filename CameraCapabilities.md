# Camera capability source of truth

Camera capability truth is owned by the corresponding libgphoto2 source and
its hardware evidence. Do not infer current packaged support from a historical
SHA in this repository.

- Pentax capability matrix:
  <https://github.com/ian-morgan99/libgphoto2/blob/master/docs/pentax/IMAGE_TRANSMITTER_CAPABILITY_MATRIX.md>
- Pentax audit notes:
  <https://github.com/ian-morgan99/libgphoto2/blob/master/docs/pentax/CAPABILITY_MATRIX_AUDIT.md>
- The exact libgphoto2 SHA packaged in firmware is defined by
  `docs/FWPKT-PROVENANCE-CONTRACT.md`.
- Bounded device qualification claims live in `docs/TESTED.md` and the current
  candidate's public `SUMMARY.md`.

The pre-2026-09-18 version, including the obsolete `c82d19052` baseline, is
preserved in PrivateResearch under the issue 116 archive.
