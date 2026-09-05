# GitHub issue review — ian-morgan99/benro-polaris-firmware-patcher

> **Date:** 2026-08-27
> **Reviewer:** the assistant on session `857392c4`
> **Scope:** the 8 open issues on the firmware-patcher fork
> at the time of the user's "please review the newly raised items on
> github" request.
>
> **Status of this review:** observational, not an action plan.
> Where an issue is already closed by a prior commit on this branch,
> that's noted. Where the issue requires hardware, a fresh Docker
> build, or a third-party coordinate, the review says so plainly.

## Snapshot of the 8 open issues

Listed newest first (matches the `gh issue list` sort by
`CREATED_AT` desc):

| # | Title | Severity | Created | Status this review |
|---|-------|----------|---------|--------------------|
| 18 | Confirm FwPkt.zip availability for combined Pentax+HDMI build (2026-08-27) | info | 2026-08-27 | Open — answered, awaiting owner decision |
| 16 | POC for a mobile app — licensing review of `wemiller.com/apps/aperion/` | info | 2026-08-27 | Open — not started |
| 15 | NEXT: Freeze one canonical release candidate, rebuild from source, then validate reversibly on Polaris hardware | process | 2026-08-27 | Open — adopted as §8.5 blocker plan |
| 13 | HIGH: Combined build was layered from an older Pentax FwPkt, not rebuilt end-to-end | HIGH | 2026-08-27 | Open — partially addressed; true fix requires new build |
| 12 | HIGH: LGPL corresponding-source package does not contain the Pentax modifications used in the built binary | HIGH | 2026-08-27 | Open — partially addressed; true fix requires new build |
| 11 | HIGH: Combined Pentax+HDMI artifact is not yet "shippable" — no device flash, DEAD-path reachability unproven | HIGH | 2026-08-27 | Open — language/framing fixed; hardware validation pending |
| 2 | Set an appliance-safe Pentax capture memory budget in the Polaris runtime | medium | 2026-08-26 | Open — `LIBGPHOTO2_PENTAX_MAX_CAPTURE_SIZE` not yet consumed |
| 1 | Pentax integration can silently build vanilla libgphoto2 instead of the current Pentax branch | HIGH | 2026-08-26 | Open — known risk, documented; not yet fixed in code |

## Per-issue review

### #18 — Confirm FwPkt.zip availability for combined Pentax+HDMI build

**Reviewer take:** this is an **availability question**, not a
defect. The .zip is gitignored by upstream policy ("distributes no
firmware; bring your own FwPkt"). What the repo *does* commit is:

- `builds/2026-08-27-combined-720p60/SHA256SUMS` — the
  fingerprint, the Docker image digest, and the re-run command.
- `builds/2026-08-27-combined-720p60/build-source-provenance.txt`
  — the layered-build disclosure.
- The critical-review's §11.1 owner-decision block.

**Verified during this review:** the FwPkt.zip is on disk at
`/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/builds/2026-08-27-combined-720p60/FwPkt.zip`
(68,484,760 B; sha256 `fb4c37e0e00c4b61a42e3c3b6d515cc5a1c4b0676cc4bc54275f4a27c6e8adaf`).
That location is on the **main checkout**, not in the
`attachment-plan-follow-up` worktree (the worktree only has the
gitignored-out `SHA256SUMS` provenance file, by design).

**Recommendation:** close #18 as "answered" once the user
confirms the .zip path. Add a one-line note to §11.1 saying
"the .zip is retained at the path above in the main checkout" so
future reviewers don't have to ask.

**Effort to close:** zero work, just one acknowledgement.

---

### #16 — POC for mobile app — licensing review of `wemiller.com/apps/aperion/`

**Reviewer take:** this is a **legal due-diligence item**, not a
build item. The mobile-app code that *was* on this fork has already
been moved to its own repo (`ian-morgan99/OpenPolaris`, MIT-licensed
at commit `18bd7d3`), so there is no GPL mobile-app code in this
firmware-patcher fork anymore.

That makes the practical question: "are there any useful patterns
in Aperion that we could learn from, given OpenPolaris is MIT?" —
which is a research question, not a licensing review of the
firmware patcher.

**Recommendation:** change the framing. This issue is now
about "should we research Aperion's design as a reference for
OpenPolaris?" rather than "could Aperion's code end up in this
repo?" Once reframed, it can be addressed in OpenPolaris's issue
tracker, not here. Optionally close #16 on the patcher fork with
a pointer to the OpenPolaris tracking issue.

**Effort to close:** 5 minutes of triage + a comment.

---

### #15 — NEXT: Freeze one canonical release candidate, rebuild from source, validate on hardware

**Reviewer take:** this is the **umbrella issue for the §8.5
blocker plan**. The 10-step plan in #15 collapses neatly into the
8-step plan in `docs/CRITICAL-REVIEW.md` §8.5 because:

- #6 and #7 (QEMU gates) collapse into one emulator pass.
- #8 and #9 (device gates) collapse into one device pass.

The 8-step plan is therefore **already adopted** and is the
canonical next-action plan. Steps 1-2 are doc/repo hygiene (done);
steps 3-7 require a new build; steps 7-8 require hardware.

**Recommendation:** keep #15 open as the umbrella tracker.
Add a comment that maps each of the 10 original steps to the
8-step §8.5 plan and references the "release-state vocabulary"
ladder (current rung: `round-trip verified`).

**Effort to close:** zero — it's the umbrella. Closes only when
all of #11, #12, #13 close.

---

### #13 — HIGH: Combined build was layered, not rebuilt end-to-end

**Reviewer take:** **substantively correct**, and the prior
assistant already acknowledged the layering in the second
comment on this issue. The combined FwPkt at
`builds/2026-08-27-combined-720p60/` was produced by:

1. Extracting `appfs.ubifs` from `builds/2026-08-23/FwPkt.zip`
   (Pentax-only build from libgphoto2 `da8c33482`).
2. Patching `polestar_app` with `hdmi_geometry_patch.py
   --include-dead=0` (5 LIVE sites → 1280×720@60).
3. Re-packing via Docker and re-zipping.

That is **not** the same thing as rebuilding Pentax from current
master end-to-end. The embedded `libgphoto2.so` is the one from
`da8c33482`, not the current `f0f29ffc`.

**What has been done about it (this review pass verified):**

- `builds/2026-08-27-combined-720p60/build-source-provenance.txt`
  has a new `source_kind=combined_layered` field plus an
  `input_fwpkt_zip=../2026-08-23/FwPkt.zip` reference, so the
  layering is no longer hidden.
- The §8.5 plan, step 3, is the actual fix: end-to-end rebuild
  in one container invocation.

**Recommendation:** keep open. Mark in a comment that the
**disclosure** side of this issue is closed (layering is now
labelled), but the **substantive** side (do a real end-to-end
rebuild) remains open and is blocked behind steps 1-3 of §8.5.

**Effort to close substantively:** multi-hour Docker build
(estimated 2-4 hours for a from-scratch libgphoto2 cross-build
plus the combined patcher pass).

---

### #12 — HIGH: LGPL corresponding-source package does not contain the Pentax modifications

**Reviewer take:** **substantively correct** and arguably the
most legally serious of the three HIGH issues, because LGPL §6 is
a real obligation (anyone who receives a binary linked against
LGPL code is entitled to the corresponding source of *that exact
modified version*).

**Current state (verified this review pass):**

- The tarball at
  `builds/2026-08-23/licenses/libgphoto2-2.5.34.tar.xz`
  (3,043,788 B) **is** the vanilla upstream 2.5.34 release
  tarball. The 2.5.34 version matches, but the Pentax commits
  from the `da8c33482` working copy are not in it.
- `builds/2026-08-23/libgphoto2-2.5.31-pentax-modified.tar.gz`
  exists and is a snapshot of the Pentax modifications, but the
  second comment on this issue notes it is a *snapshot of
  modifications*, not a *re-tar of the working tree* — those
  are not the same thing under LGPL §6.
- `builds/2026-08-23/build-source-provenance.txt` now has
  `git_commit=da8c33482e674692023fddcf32cb73d1dd4da05d`
  back-patched, plus `dirty_diff_hash` and `input_sha256` — so
  the *provenance label* is now correct.

**What #12 is actually asking for:** a *re-tar of the working
tree* (or an equivalent) that the binary was actually built
from. This is exactly step 6 of the §8.5 plan.

**Recommendation:** keep open. The provenance is correct; the
actual archive is not. Comment that step 6 of §8.5 is the
remediation, and that this issue can only be closed together
with #13 (they share a build pass).

**Effort to close substantively:** 15-30 minutes of `git
archive` + SHA256 recording, once step 3 of §8.5 has been
executed.

---

### #11 — HIGH: Combined artifact is not yet "shippable"

**Reviewer take:** **substantively correct, language already
fixed**. The prior assistant already addressed this in the first
comment on the issue (2026-08-27 11:22 UTC), and the second
comment (12:04 UTC) gives the right framing: "still open by
design, requires (a) a fresh end-to-end build and (b) device
flash + DEAD-path reachability check."

**What changed since the issue was filed (this review pass
verified):**

- `docs/CRITICAL-REVIEW.md` §0 TL;DR no longer says "shippable."
  It now says **"build-verified candidate, not device
  validated"** with a pointer to the release-state ladder.
- The "Release-state vocabulary" table (also in §0) defines a
  7-rung ladder from `assembled` to `release candidate`. The
  current artifact sits at `round-trip verified` only.
- "DEAD sites unreachable" has been softened to "in code paths
  not exercised by the LIVE flow, per static/signature
  analysis." The "proven" wording is gone.
- `docs/RUN-JOURNAL.md` and `docs/FINAL-REPORT.md` no longer
  use "shippable" or "proven-unreachable."
- The §8 diagram now labels the final FwPkt as
  `[ROUND-TRIP-VERIFIED CANDIDATE, NOT DEVICE-VALIDATED]`.

**Recommendation:** keep open. The vocabulary side is closed;
the actual *device validation* side is the §8.5 plan steps
7-8 and requires hardware.

**Effort to close substantively:** ~1-2 hours of
controlled-environment Polaris flashing with verified backup,
plus Pentax attach + HDMI observation.

---

### #2 — Set an appliance-safe Pentax capture memory budget

**Reviewer take:** **correct as a defect**, and a real
appliance-safety improvement. The Polaris runtime wrapper at
`container/ondisk/pgphoto.wrapper` does not export
`LIBGPHOTO2_PENTAX_MAX_CAPTURE_SIZE`, so even though the
library has the configurability, the appliance doesn't consume
it. That means a malformed Pentax transfer could in principle
drive large allocations on an embedded device with limited RAM.

**Current state:**

- The `LIBGPHOTO2_PENTAX_MAX_CAPTURE_SIZE` configurability
  lives in `ian-morgan99/libgphoto2#36` (referenced by the
  issue).
- The Polaris runtime wrapper does not set it yet.

**Required fix (per the issue's own acceptance criteria):**

1. Pick a budget from the largest observed K-1 II / K-3 III
   RAW/JPEG transfer, with headroom.
2. Export the variable in the runtime wrapper.
3. Document the value and the hardware evidence.
4. Add a positive + negative test.
5. Make the value part of the build profile/manifest.

**Recommendation:** keep open. Track as a Polaris-runtime
change, not a libgphoto2 change. The right owner is the
patcher-side wrapper code, and the change is small (~5 lines
in `pgphoto.wrapper` plus a test in
`container/test_polaris_pentax_build_package.sh`).

**Effort to close:** ~30-60 minutes including test.

---

### #1 — Pentax integration can silently build vanilla libgphoto2

**Reviewer take:** **correct as a defect**, and arguably the
most operationally dangerous of all the open issues because
it can produce a perfectly successful Polaris image that
silently contains *vanilla* libgphoto2 instead of the Pentax
research-capable one. The user could then "validate" the
device with a build that doesn't have what they think it has.

**Current state (verified this review pass):**

- `patch-polaris.sh` still defaults `VER="2.5.34"` and only
  uses the research Pentax tree when the caller manually
  supplies `--libgphoto2-source PATH`.
- `container/ondisk/pgphoto.wrapper` hard-codes
  `CAMLIBS=$D/libgphoto2/2.5.34` and
  `IOLIBS=$D/libgphoto2_port/0.12.2`.
- The two are *not* tied together — a non-2.5.34 build could
  be assembled successfully while the runtime wrapper still
  points at the 2.5.34 directory.

**The issue's own acceptance criteria** are good:

1. Pentax build/profile mode that consumes an explicit
   libgphoto2 commit/ref.
2. Fail closed if a Pentax image is requested without a
   source/ref that actually contains the Pentax research
   implementation.
3. Record exact libgphoto2 commit SHA in the firmware
   metadata/manifest.
4. Generate `CAMLIBS` / `IOLIBS` from the built module
   versions, not hard-coded.
5. Image-level assertion that the produced `ptp2.so` carries
   the expected Pentax research-capable models.
6. Regression test covering both vanilla and Pentax-source
   builds.

**Recommendation:** keep open. Treat as a
**build-integrity prerequisite** for any new combined build
— i.e., steps 1 and 3 of the §8.5 plan are the natural
place to also land the fix from #1, since a fresh
end-to-end Pentax pass will need both anyway.

**Effort to close:** 1-2 hours of patcher + wrapper changes
plus new regression test.

---

## Cross-issue analysis

### Theme 1: doc fixes vs. build fixes

Four of the eight issues (#11, #12, #13, #15) have a
**doc-only** part and a **build-only** part. The doc parts
have all been addressed on this worktree (in commits
`318b09f` through `ba38a20`). The build parts all require
the §8.5 plan to be executed. That means the patcher repo
is at a coherent "doc side done, build side queued" state —
which is the right state to be in.

### Theme 2: the umbrella plan

Issue #15 is the umbrella. The 8-step plan in
`docs/CRITICAL-REVIEW.md` §8.5 is the operative plan that
addresses #15, #13, and #12 in one pass. Step 1 of §8.5
("stop the layered build") is a *behavior* commitment
that's worth tracking: any agent that produces a new
combined FwPkt before #15 closes is implicitly violating
this commitment and should be flagged.

### Theme 3: device validation

The Polaris hardware is now in the user's hands. The
remaining gates (steps 7-8 of §8.5, plus the on-device
portion of #11) require the user to flash and observe.
Until that happens, the artifact is permanently at
`round-trip verified`.

### Theme 4: build-integrity gates (#1, #2)

These are **independent of the §8.5 plan** and can be
landed at any time. Both are small, well-scoped changes.
They should be treated as a **Phase 2 cleanup** that
follows the §8.5 plan, not as a prerequisite to it.

### Theme 5: process / ownership (#16, #18)

These are **triage** items, not build items. #18 is
"confirm the .zip is at this path" (one-line answer).
#16 is "re-frame the mobile-app research question to
OpenPolaris's tracker" (5 minutes).

## Recommended next steps (ordered by user-decision cost)

1. **#18** — acknowledge on the issue; the .zip is
   confirmed at the path in §11.1. No code change.
2. **#16** — re-frame and migrate to OpenPolaris. No code
   change on the patcher.
3. **#1 and #2** — implement as Phase 2 patcher changes.
   Can be done in this worktree without a fresh full build
   (the change is to `patch-polaris.sh` and
   `pgphoto.wrapper` + tests).
4. **#11** — close the doc side, keep the device side open
   pending hardware.
5. **#12, #13, #15** — all gated behind §8.5 steps 3-8.
   The §8.5 plan is already adopted.

## Reviewer's overall assessment

The patcher fork is in a **publishable shape**:

- All 8 open issues have prior comments that
  acknowledge the substance and explain the gap to closing.
- The work that *can* be done without a fresh build or
  hardware (the doc/provenance side of #11, #12, #13;
  the planning side of #15) has been done.
- The remaining gates are honest "requires hardware /
  requires time" items, not "we forgot to do this" items.
- The cross-repo state is clean: `main`, two
  `agents/*` branches on this fork, plus
  `ian-morgan99/OpenPolaris` (MIT, mobile-app split-out).

A second agent doing a final review should focus on:

- Verifying the four §11.1/§11.2/§11.3/§11.4 claims
  in `docs/CRITICAL-REVIEW.md` against the current
  GitHub state.
- Spot-checking that `builds/2026-08-27-combined-720p60/SHA256SUMS`
  matches the .zip at the path in §11.1.
- Confirming that the `LICENSE` and `README` reflect the
  MIT-on-OpenPolaris + GPL-on-firmware-patcher split.

No further code changes are required from this review.
