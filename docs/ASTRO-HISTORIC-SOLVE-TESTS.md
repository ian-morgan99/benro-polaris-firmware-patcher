# Astro historic-image solve tests

Status: implemented on `feature/astro-native-platesolve`; not yet deployed to Polaris.

## Purpose

The Astro WebUI gallery now has a **Historic image solver test** panel. It is for
repeatable solver experiments before enabling any automatic camera or motor
behaviour. A test can use either:

- a JPEG uploaded from the browser; or
- a JPEG already present in one of the gallery capture directories on the
  Polaris SD card.

The selected image is copied/listed under `test-input/` when uploaded. The solve
job is separate from the live capture solve job. It never calls the mount link,
starts a shutter, performs a goto/alignment, applies a result, or writes EXIF.

## WebUI flow

1. Open **Gallery** and refresh.
2. Choose a local `.jpg`/`.jpeg` and select **Upload JPEG**, or select an existing
   gallery image from **SD image**.
3. Choose **Astrometry.net** (reference) or **Native indexed (research)**.
4. Enter focal length and sensor width only when EXIF/profile data is absent or
   being deliberately overridden. Optional RA/Dec/radius values provide a
   search hint; they are not required for the reference solver.
5. Select **Solve selected image**. The result and bounded job log appear in the
   panel. **Cancel** terminates only the test job process group.

The HTTP API behind the panel is:

- `POST /api/test/upload?name=...` with a raw JPEG body.
- `POST /api/test/solve` with form fields `path`, `solver`, `focal`, `sensor`,
  and optional `ra`, `dec`, `radius`.
- `GET /api/test/state` and `POST /api/test/cancel`.

Uploads are limited to 32 MiB, require a basename JPEG name, validate JPEG
start/end markers, and are atomically published. Media paths remain restricted
by the existing category whitelist and realpath check.

## Solver safety

The independent indexed search now has both a per-child deadline and an optional
whole-search deadline. `polaris-align.sh` defaults to:

- `INDEPENDENT_SOLVER_TIMEOUT=10` seconds per native child;
- `INDEPENDENT_SEARCH_TIMEOUT=45` seconds per indexed search;
- `INDEPENDENT_BLIND_FALLBACK=0`.

A failed RA/Dec hint therefore does not silently start an unbounded all-sky
search during a live capture. Blind fallback can be enabled explicitly for a
controlled research run, but it remains inappropriate for the unattended frame
watcher.

The historic test job additionally sets `MOUNT_HINT=0`, `EXIF_WRITEBACK=0`, and
`EMBED_SOLVE_EXIF=0`. The native solver remains a research option: bounded
execution is now safe to test, but it is not yet a qualified replacement for
Astrometry.net.

## Evidence so far

- Host C compile of `polaris-httpd` with the embedded WebUI: passed.
- Focused Astro tests: 19 passed.
- Repository test suite: passed.
- Local end-to-end HTTP test covering upload, gallery listing, and a non-motor
  test solve: passed.
- Documented ARM bundle build with `./build-astro.sh --no-indexes`: passed;
  output was `out/astro-webui-test3`.
- No firmware was flashed and no device files were changed by this work.
- The native solver still did not solve the supplied real `_EVE4724.JPG` and
  `G7D9gnBg.jpeg` fixtures in earlier research runs; Astrometry.net remains the
  comparison/reference path.

## Tomorrow's test order

1. Build/publish a separately named candidate from the committed branch.
2. Copy the Astro bundle through the normal ZIP/Bluetooth-wake process only; do
   not use SSH code replacement.
3. Verify `/api/test/state`, the gallery, and one small historic JPEG upload.
4. Run the same historic image through both solvers with the known focal/sensor
   values. Record elapsed time, solved flag, RA, Dec, roll, scale, match count,
   RMS, and failure reason.
5. Use existing SD images before any camera capture. Keep native selected only
   for research and leave the reference solver as the live default.
6. If live camera testing is authorized, run one supervised capture after the
   non-motor tests; do not enable automatic correction or EXIF writeback as part
   of this comparison.

## Handover

The next agent should start in the clean worktree
`/home/ian/Documents/VSCodeProjects/PrivateResearch/.astro-v94.TrArG1` on
`feature/astro-native-platesolve`, inspect the latest commit and remote status,
and use this document as the entry point. The original
`/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher` checkout remains dirty
and must not be cleaned or rebased. This branch owns the Astro variant only.
Before any device action, coordinate the single deployment/test window with the
camera owner and verify the candidate manifest, dependency hashes, and packet
hash. Do not claim native-solver qualification from the local build or WebUI
smoke test.
