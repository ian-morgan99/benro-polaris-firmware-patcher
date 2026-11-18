# Polaris plate-solve protocol extension — issue #366

Status: **design checkpoint, not implemented or hardware-qualified**.

## Verified source baseline
- `container/astro/polaris-solve.c` already emits `ra_deg`, `dec_deg`, `roll_deg`, `pixscale_arcsec`, `field_w_deg`, `field_h_deg`, `parity`, and a four-element `cd` array from the astrometry.net WCS.
- `container/astro/polaris-httpd.c` already implements an Alpaca Telescope device and a Camera device, but both Telescope and Camera `supportedactions` currently return `[]`.
- `GET /api/astro/solve` is **read-only**, returning `target.json` and `last-frame-solution.json`. It does not start a solve.
- The existing `/api/solve` and `/api/test/solve` paths already provide job infrastructure. Reuse and validate them before adding a second job runner.
- Do not assume `roll_deg` is the required image PA without checking the astrometry.net orientation convention against reference WCS and parity.

## Proposed protocol surface (subject to compatibility review)
The first client-facing interface should be an **ASCOM Alpaca Telescope Action**, avoiding invention of an undocumented raw Polaris command number. Once the firmware protocol dispatcher and command ownership are understood, an optional new Polaris extension command may be added separately. These are distinct interfaces.

- `GET /api/v1/telescope/0/supportedactions`: advertise `Polaris.PlateSolve.V1` only when the implementation is available.
- `PUT /api/v1/telescope/0/action` with `Action=Polaris.PlateSolve.V1`, `Parameters=<versioned request>`: initiate an existing-image solve or return an active job reference. Exact URL-encoding and Alpaca response envelope must follow existing helpers.
- Follow-up status/result retrieval must be bounded and idempotent. Avoid waiting synchronously for a potentially minutes-long solve.
- Response schema: `schema_version`, `job_id`, `state`, `solved`, `ra_deg`, `dec_deg`, `coordinate_epoch`, `image_pa_deg`, `pa_convention`, `parity`, `cd`, `pixscale_arcsec`, `field_w_deg`, `field_h_deg`, `solver`, `elapsed_ms`, `error`.
- Failure and unknown PA are explicit nulls; never invent 0 degrees. PA is **camera image orientation**, not a rotator setting or Polaris motor angle.
- Solve must never move the mount, sync the telescope, modify camera originals, or write EXIF as an implicit side effect.
- Avoid arbitrary filesystem paths in client input. Prefer already-admitted JPEG IDs and existing validated path rules.

## Implementation order
1. Audit the `/api/solve`, `/api/test/solve`, `/api/astro/solve` handlers and their shell-backed job ownership, cancellation and result lifetime.
2. Add a pure, testable WCS-to-image-PA normalisation helper; establish convention from independently solved reference images, including flips and sensor axes.
3. Add a capability-gated Alpaca Action using existing request parsing, transaction IDs, error handling and job lifecycle. Preserve `supportedactions=[]` on builds without it.
4. Add the **raw Polaris protocol extension only after** identifying an unoccupied command namespace and documenting negotiation, ownership, safety and backwards compatibility. Do not route arbitrary new commands into stock mount control.
5. Add a client example and tests for success, timeout, cancellation, stale result, malformed input, unsupported firmware, concurrency and mount non-movement.
6. Investigate the external Alpaca driver and NINA separately: Telescope Sync carries coordinates, **not camera PA**. Document a concrete supported PA consumer before promising NINA integration.

## Release and review gates
Keep this work in `feature/366-polaris-platesolve-alpaca-pa`, delivered as a draft PR. No automatic merge, release, installation or firmware packaging. Before a candidate build, follow `AGENTS.md`, the repository's documented skills, build-doctor and regression-preservation checks. Hardware validation is a separate explicit gate.

## Open questions
- Which exact source image should an external client solve: last completed JPEG, supplied admitted image ID, or a fresh capture?
- Should the new command be in the *native Polaris wire protocol*, the existing Astro HTTP server's Alpaca interface, or both? This design stages Alpaca first and requires a separate raw-command compatibility audit.
- Which PA convention does NINA/ASTAP require, and what integration mechanism will actually consume it?


## Implementation checkpoint (draft PR #367)
- \`polaris-solve.c\` now emits \`image_pa_deg\` (numeric or null) and \`image_pa_convention\` alongside the existing roll and WCS fields. FITS +Y PA is computed from CD, not inferred from NINA Sync.
- Telescope \`supportedactions\` now advertises \`Polaris.PlateSolve.Start.V1\` and \`Polaris.PlateSolve.Status.V1\`. Both use HTTP PUT \`/api/v1/telescope/0/action\` with Alpaca form parameters \`Action\` and \`Parameters\`.
- \`Start.V1\` accepts \`Parameters=latest\` or empty and calls the **existing** \`start_solve(apply=0,mode=latest)\`. It does not apply alignment or issue a GOTO.
- \`Status.V1\` takes empty \`Parameters\` and returns an Alpaca string Value containing a JSON document with \`schema_version\`, \`state\` and \`result\`. The result field is a **bounded text excerpt** of the existing solver JSON; it is not yet a guaranteed complete typed result schema. Clients must treat it as diagnostic until a full bounded-result design is implemented.
- This is a first experimental API and **not a native Polaris wire-protocol command**. It is not yet qualified with a real Alpaca driver, NINA or hardware.
- A local host test of the PA helper's axis/parity cases passed on 2026-11-18 using \`cc -std=c99 -Wall -Wextra -pedantic ... -lm\`; a full firmware compile, cross-build and hardware test have **not** been run.
- The provided historical WCS example \`[-0.00285160406,-0.00139008603;-0.001397934,0.0028408417]\` gives FITS +Y PA approximately **333.9265°**; this is a calculation check, **not** independent ASTAP/NINA convention validation.

### Remaining blockers
1. Replace bounded diagnostic \`result\` excerpt with a structured, complete and explicitly versioned result contract, including job identity, timestamps, expiry, stale-result prevention and errors.
2. Check exact Astro build and compiler warnings, test real HTTP Alpaca envelopes, malformed actions and concurrency; the source edits have not yet been built.
3. Confirm PA orientation against real image/ASTAP WCS and mirrored FITS-to-screen transformations.
4. Review network exposure, command authentication assumptions and source-image admission; do not publish or deploy this draft.
5. Native Polaris command namespace and external Alpaca-driver/NINA integration remain separate tasks.

## Next checkpoint — job token and bounded result (PR #367)
- `Start.V1` now returns a **string token** derived from the existing `JOB_START` timestamp. This is **not** a globally unique job ID: two starts within the same second can collide. Do not use for production correlation until fixed.
- `Status.V1` accepts an optional numeric token in `Parameters`, rejects a mismatch against the current job and returns the full solver-result line (up to 4095 bytes), or an explicit Alpaca error if the file is larger. `Value` remains a JSON string containing `schema_version`, `job_id`, `state` and `result` (result itself is a JSON-escaped string, not a typed nested object).
- The previous 1 KiB Alpaca response helper is bypassed with a dynamically allocated response, avoiding silent response truncation.
- **Still unverified:** complete firmware compilation, Alpaca HTTP integration, hardware, security, resource usage and external-driver behaviour. The job token is provisional, and the result file must be checked for freshness relative to the job start before release.
- **Known race:** the existing double-fork job runner records its PID asynchronously; a Status call immediately after Start can see `running` before the PID file is created. The current handler may prematurely report `failed`. Resolve this race and timestamp collision before accepting the protocol.

## Job-correlation update (2026-11-18)
- Start now writes a microsecond-resolution, transaction-salted decimal token to `/tmp/polaris-job.alpaca-id`; every `start_solve` invalidates the previous token, including starts from the WebUI.
- Status compares an optional supplied token with the current persisted token. Its response now reports that token as a **string**. This avoids the earlier whole-second collision; it is not a cryptographic identifier.
- Removed the immediate PID check from Status because the double-fork worker publishes its PID after Start can return. This prevents a false failed state on the first poll.
- **Remaining important work:** a worker that crashes without updating `JOB_STATUS` may now leave `running` visible indefinitely until another start. Implement a bounded, race-safe liveness check with startup grace and hard timeout.
- The Status implementation currently allocates several large fixed buffers on the request stack. Measure actual device stack/RAM usage and move to bounded heap or streaming before any deployment, especially given Polaris resource constraints.
- Still no complete firmware build or hardware qualification for this PR.

## Liveness and memory follow-up (draft)
- Added shared `solve_job_alive()` for the existing WebUI start path and Alpaca Status. If the detached worker PID has not yet been written, it allows up to ten seconds from `JOB_START` before marking the job failed. This is a startup grace, **not** a hard execution timeout.
- Replaced the large temporary Status JSON escaping arrays with size-checked heap allocations and explicit frees. `json_escape()` requires additional trailing headroom, which the allocation now provides.
- **Unresolved:** PID reuse can make a stale job appear alive; a hung but alive solver remains running; wall-clock jumps can distort the grace interval. Use a monotonic clock/process identity or a durable bounded worker watchdog before production.
- **Unresolved:** the full firmware has not been compiled or smoke-tested in this session. Treat all C changes as unqualified until a real build and HTTP test are performed.
