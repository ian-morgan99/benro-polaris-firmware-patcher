# Polaris runtime and package contract

This file retains the operational conclusions extracted from the archived
reverse-engineering corpus.

- Firmware changes flow through an immutable FwPkt, verified manifest and the
  documented update skill; direct persistent `/app` mutation is not a release.
- Full libgphoto2 upgrades are matched-stack changes: wrapper, Stage-2 binary,
  loader, core, port, camlib, iolib, lookup paths and ABI assumptions move
  together.
- The updater validates the extracted `FwPkt/` payload and `firmwareInfo`;
  stale payload hashes can cause a silent reject.
- Runtime proof requires deployed hashes and `/proc/<pgphoto>/maps`, not merely
  a build directory.
- Direct libgphoto2, Polaris-local and OpenPolaris E2E failures have different
  owners. Compare the first divergent operation.
- A command acknowledgement does not prove physical focus, exposure or a
  completed file transfer.

The full disassembly and installer investigation are in PrivateResearch's
issue 116 archive. Current procedures remain in AGENTS.md, the operational
skills, `LIBGPHOTO2-UPGRADE-PROCESS.md` and the provenance contract.
