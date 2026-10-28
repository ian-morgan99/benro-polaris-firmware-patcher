# Firmware source verification and offset ledger

## Status

This is mandatory release-control guidance. Every new Benro firmware source,
every new extracted firmware package, and every release candidate must complete
the verification checklist and update the offset ledger before it can be
treated as a supported target.

A firmware version string, filename, registry entry, or apparently successful
build is not sufficient evidence.

## 1. One record per firmware source

Create one immutable record for each source firmware family and exact binary
identity. At minimum record:

- source package filename and SHA-256;
- extracted package tree and manifest hashes;
- /app/FwVer;
- MCU firmware version and hash, if obtainable;
- polestar_app SHA-256, size, ELF identity, and load sections;
- pgphoto and other load-bearing binary hashes;
- patcher commit, source commits, toolchain versions, and analysis-script hashes;
- date, device identity, and operator;
- whether the source is stock, patched, installed, or physically qualified.

Do not merge records merely because two firmware versions have similar names.

## 2. Mandatory checks on every release

Every release or candidate run must explicitly check and record the result of
each item below.

### A. Source and provenance

- exact source package is identified and hashed;
- extracted files match the package manifest;
- target binaries are hashed after extraction;
- the patcher worktree and source commits are recorded;
- no unexplained dirty or generated files affect the build;
- rollback package is identified and independently hashed.

### B. Binary and layout identity

For every patched or relied-upon binary:

- verify architecture, ABI, endianness, ELF sections, load segments, and file
  offsets;
- locate required symbols where available;
- record symbol address, size, section, and function-byte hash;
- re-run instruction and data-flow fingerprints;
- rediscover literal pools, global objects, PLT targets, branch tables, and
  trampolines;
- confirm file-offset to virtual-address mapping;
- fail closed on missing, duplicate, ambiguous, or non-unique matches.

### C. Existing patch inventory

Revalidate every existing patch, including patches that are not part of the
new feature:

- HDMI geometry polestar_app sites;
- firmware-version/code-780 patch;
- any gimbal/UART or protocol-routing patch;
- Stage-2 and pgphoto binary patches;
- loader and camera-stack substitutions;
- manifest, provenance, and package-integrity assumptions.

For each patch, prove that the original bytes and semantic fingerprint still
match the target binary. A patch that is unchanged in source still requires
revalidation if its target binary changed.

### D. Behaviour and protocol contracts

Check that the release still preserves:

- existing application command IDs and reply formats;
- SLOW and FAST gimbal semantics;
- camera command routing and error mapping;
- watchdog and process-lifecycle behaviour;
- USB enumeration and camera admission;
- package updater and reboot behaviour;
- all previously release-qualified camera scenarios within their stated scope.

### E. Packaging and installation

- patched bytes match the recorded output;
- no unrelated binary changed unexpectedly;
- firmware manifests and install manifests agree;
- package hashes are recorded before transfer;
- sanctioned installation path is used;
- post-install hashes, /app/FwVer, provenance, uptime, processes, listeners,
  and USB state are captured;
- rollback is available and tested or explicitly marked pending.

### F. Physical qualification

A release is not physically qualified from static analysis or packaging alone.
Run the required hardware matrix for the target models and record:

- exact installed firmware identity;
- camera USB identity;
- command/result transcript;
- independent read-back or visible effect;
- capture/preview/session recovery;
- reconnect and restart behaviour;
- process, kernel, and watchdog health;
- safe stop and restored control.

Missing hardware evidence is UNQUALIFIED, not PASS.

## 3. Offset and function ledger

Maintain a machine-readable ledger for every load-bearing address or semantic
target. A Markdown rendering may be generated from it, but the structured
record is authoritative.

Recommended fields:

| Field | Required meaning |
|---|---|
| firmware_id | Exact firmware family and binary/package identity |
| component | polestar_app, MCU, pgphoto, loader, or other binary |
| binary_sha256 | Exact analyzed binary |
| semantic_role | What the target does |
| symbol | Symbol name, if present |
| function | Containing function |
| virtual_address | Runtime/ELF virtual address |
| file_offset | Byte offset in the extracted file |
| size | Function or patch span size |
| original_bytes | Expected bytes before patch |
| replacement_bytes | Bytes written by the patch |
| fingerprint | Masked instruction/data-flow pattern |
| dependencies | Literal pools, globals, PLT calls, branch tables |
| verification_method | Symbol, disassembly, data-flow, runtime, or hardware |
| status | verified, moved, changed, missing, or unsupported |
| evidence | Evidence directory, test, and release links |
| last_checked | Date and operator |

The ledger must record semantic targets, not only raw numbers. For example,
record “HDMI input width passed to SP_HdmiViInit” rather than only 0x13c398.

## 4. Required ledger entries

At minimum, each supported firmware record must cover:

- all HDMI LIVE and DEAD sites used by the build;
- code-780/version-reporting sites and their literal dependencies;
- gimbal UART frame construction and queue functions;
- gimbal application dispatcher and command table;
- independent-rate helper and any new command branch;
- camera command handlers and patched dispatch sites;
- Stage-2 loader entry points and policy gates;
- all package-manifest and embedded-provenance files;
- every binary named as load-bearing by the release manifest.

## 5. Detecting moved offsets

An address is considered valid for a new source only when all applicable checks
pass:

1. exact binary identity is recorded;
2. ELF mapping resolves the address to the expected section;
3. expected original bytes match;
4. masked instruction fingerprint matches uniquely;
5. surrounding function and call graph match;
6. literal/global/PLT dependencies resolve correctly;
7. static patch tests pass;
8. runtime or hardware evidence passes where required.

If an address changes but the semantic fingerprint remains uniquely equivalent,
create a new firmware-specific ledger row and patch recipe. Do not silently
edit the old row.

If the fingerprint has zero or multiple matches, mark the target unsupported
and stop the release until it is manually re-analysed.

## 6. Release checklist and sign-off

The release record must link:

- source identity record;
- offset ledger version;
- binary differential report;
- static verification output;
- package and install manifests;
- rollback evidence;
- post-boot identity;
- physical qualification summaries;
- unresolved limitations.

The release owner must explicitly sign off each category:

SOURCE_PROVENANCE=
BINARY_LAYOUT=
EXISTING_PATCHES=
PROTOCOL_CONTRACTS=
PACKAGE_INTEGRITY=
INSTALL_IDENTITY=
ROLLBACK=
PHYSICAL_MATRIX=
FINAL_VERDICT=

A release cannot be marked RELEASE-QUALIFIED while any required field is
missing, ambiguous, unsupported, or only inferred from a previous firmware.

## 7. Upgrade rule

When Benro issues a new firmware, or when a local change modifies a binary
layout:

1. preserve the previous ledger and release evidence;
2. create a new firmware identity record;
3. extract and hash every load-bearing binary;
4. re-run all address, symbol, fingerprint, and dependency checks;
5. classify every target as unchanged, moved, changed, missing, or unsupported;
6. create target-specific patch metadata where needed;
7. rebuild and run the complete release gates;
8. install only after package verification;
9. perform post-boot and physical qualification;
10. update the release record and keep the previous rollback target.

The default for a new firmware is unsupported pending analysis, even if the new
version appears to boot normally or the old patch happens to apply at the same
numeric offset.

## 8. Relationship to other documents

- polestar_app build compatibility warning
- Issue #3 implementation specification
- current repository state
- firmware provenance contract

