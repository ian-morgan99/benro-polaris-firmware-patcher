# Documentation map

This is the entry point for `docs/`. Read this before opening anything else here.
It exists because the tree contains ~120 Markdown files, most of which are
historical, and an agent that starts at `CURRENT-STATE.md` will absorb a month of
superseded narrative before it learns what is true now.

## Read in this order

| # | File | What it answers |
|---|---|---|
| 1 | [`../AGENTS.md`](../AGENTS.md) | Rules of work. Which skill covers which operation. |
| 2 | [`../.github/skills/polaris-debugging/SKILL.md`](../.github/skills/polaris-debugging/SKILL.md) | How to operate the rig and report to the operator. §0 first. |
| 3 | [`RELEASE-VERSION-STATE.md`](RELEASE-VERSION-STATE.md) | Which display version is current, which are consumed, what is on the device. |
| 4 | [`FWPKT-PROVENANCE-CONTRACT.md`](FWPKT-PROVENANCE-CONTRACT.md) | The provenance row for the specific artifact you are holding. |
| 5 | [`LIBGPHOTO2-UPGRADE-PROCESS.md`](LIBGPHOTO2-UPGRADE-PROCESS.md) | How to build and qualify a candidate. §6/§7 are the ones usually broken. |
| 6 | [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md) | The mechanism being patched: trampolines, shims, the fresh core. |
| 7 | [`../CameraCapabilities.md`](../CameraCapabilities.md) | Where camera capability truth lives (it is not in this repo). |

## Where truth lives, by subject

Duplicated facts go stale. Each subject has one owner; everything else links to it.

| Subject | Owner | Not authoritative for it |
|---|---|---|
| Benro wire protocol (codes 258–812) | `ian-morgan99/OpenPolaris` | Anything in this repo. Codes here are quoted evidence, not a spec. |
| Pentax PTP behaviour, opcodes, condition offsets | `ian-morgan99/libgphoto2` → `docs/pentax/` | This repo's evidence summaries. |
| Camera capability matrix | `libgphoto2/docs/pentax/IMAGE_TRANSMITTER_CAPABILITY_MATRIX.md` | `CameraCapabilities.md`, which only points there. |
| Which firmware is on the device | `RELEASE-VERSION-STATE.md` | `CURRENT-STATE.md` (see below). |
| Artifact hashes and source SHAs | `FWPKT-PROVENANCE-CONTRACT.md` | Build logs, commit messages. |
| What has been qualified on hardware | `TESTED.md` + the candidate's `docs/evidence/*/SUMMARY.md` | Any narrative summary. |

## Superseded and historical

These are kept for provenance. **None of them describes the current state.** Do
not act on them without checking the live owner above.

- `CURRENT-STATE.md` — a 90 KB append-only log. Its newest section is the only
  part that can be current, and it is routinely days behind
  `RELEASE-VERSION-STATE.md`. Treat it as a journal, not a status.
- `HANDOVER-*.md` (5 files, Sep 23 – Oct 4) — point-in-time handovers. Each was
  superseded by the next. Read only the one whose date matches the incident you
  are investigating.
- `docs/archive/` — explicitly archived; see `ARCHIVED-EVIDENCE.md`.
- `docs/evidence/` (73 directories) — one directory per experiment. Only the one
  named by a provenance row is load-bearing; the rest are history.
- `docs/analysis/` — design analysis, not a contract.
- `DOCUMENT-INVENTORY.md` — the issue #116 keep/trim decision list. It is
  **incomplete**: 27 tracked documents are absent from it, including every
  `HANDOVER-*` file and `RELEASE-VERSION-STATE.md`. Absence from that file does
  not mean a document is unmanaged.

## Naming

There is no enforced convention: 28 files use `UPPER-CASE`, 7 use `lower-case`.
New files: use `UPPER-CASE.md` for contracts and processes, `lower-case.md` for
notes, and `docs/evidence/<candidate-or-incident-YYYYMMDD>/SUMMARY.md` for
evidence. Do not add new `HANDOVER-*` files — update this map and the live owner
instead.

## Known open problems in this tree

Tracked so the next agent does not rediscover them:

1. `CURRENT-STATE.md` has no staleness marker and lags the version registry.
2. `DOCUMENT-INVENTORY.md` is incomplete (see above).
3. The Benro-side code table exists only as fragments inside evidence summaries
   (e.g. `evidence/bulb-root-cause-20261005/SUMMARY.md` §on codes 258–275). The
   canonical table belongs in OpenPolaris per `CROSS-PROJECT.md`; nothing here
   links to it.
