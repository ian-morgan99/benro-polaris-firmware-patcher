# Archived evidence policy

Keep concise conclusions, qualification summaries, provenance rows, runbooks
and reproducible tests in this public repository. Store bulky raw device logs,
firmware-derived binaries, repeated snapshots and superseded planning packages
in the private research archive.

## 2026-09-17 preservation snapshot

- Private repository: `ian-morgan99/PrivateResearch`
- Commits: `a3dc491` and `8deab7e`
- Path: `archives/BenroPolarisPatcher/2026-09-17-pre-context-cleanup/`
- Public source commit captured: `5309bfdd16bfb0c393896fc888d00a98dab99c7d`

The archive includes:

- all tracked public `docs/` content at the source commit;
- the complete working-tree `docs/` snapshot;
- the ignored `LMStudioLogEnhancements.md` ledger;
- the ignored historical `STATE.md` session file;
- the complete pre-cleanup binary Git diff;
- Git-index and per-file SHA-256 manifests.

Nothing was discarded. Git history also retains every formerly tracked public
path. Restore individual evidence by verifying the private archive checksum and
extracting into a temporary directory, never over an active checkout.

## 2026-09-18 issue #116 archive

- Private repository: `ian-morgan99/PrivateResearch`
- Commit: `a6afa37`
- Path: `BenroPolaris/repository-hygiene-116/2026-09-18/original/`
- Public source commit captured: `2b56e8da392b4c7b7a0b7aaacd2ac52075ee522c`

This archive preserves 170 point-in-time reviews, handovers, reverse-
engineering notes, historical run journals, raw evidence files, and the
pre-trim versions of the camera-capability and Pentax capture-budget documents.
`MOVED-PATHS.txt` and `SHA256SUMS` provide the exact inventory and byte-level
verification. `SOURCE-STATUS.txt` and `SOURCE-WORKTREE.patch` preserve the
source checkout state. The active repository retains current operational
contracts and concise P/Q qualification summaries.

## Going forward

For each hardware run, commit a compact `SUMMARY.md` containing identity,
artifact provenance, exact commands, capability verdicts and links to the
private raw-evidence location. Do not commit full rotating device logs or
firmware-derived binaries to the public repository.
