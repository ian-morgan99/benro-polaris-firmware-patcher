# Who does what, and where it goes

Plain-language map of this project. Read this first if you are confused about
which repository, branch, or issue number something belongs in. No prior context
needed.

Last updated: 2026-11-05.

## The two repositories

There are two codebases. Almost all confusion in this project comes from mixing
them up, so start here.

| | Patcher repo | Driver repo |
|---|---|---|
| Name | `benro-polaris-firmware-patcher` | `libgphoto2` (our fork) |
| URL | github.com/ian-morgan99/benro-polaris-firmware-patcher | github.com/ian-morgan99/libgphoto2 |
| On this PC | `/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher` | `/home/ian/Documents/VSCodeProjects/LibGphoto2/libgphoto2` |
| What it is | Python and shell scripts that modify the Benro Polaris gimbal's firmware, plus all documentation, release records, and issue tracking | The camera-communication library. Actual C code that talks to Pentax cameras over USB |
| Language | Python, bash | C |
| Issue numbers | `#2xx` (e.g. #251) | `#1xx` (e.g. #145) |
| What ships | A firmware packet (`FwPkt.zip`) you flash onto the Polaris | Source that gets compiled and embedded inside that packet |

**The one-sentence version:** the driver repo is a *library*; the patcher repo is
everything else, including the thing that builds and ships the library.

## How to decide which repo an issue belongs in

Ask: **"Does fixing this require changing C code that talks to the camera?"**

- **Yes** → driver repo (`ian-morgan99/libgphoto2`), a `#1xx` number.
- **No** → patcher repo, a `#2xx` number. This includes firmware patching,
  packaging, releases, documentation, build scripts, and anything about the
  Polaris device itself.

If a fix needs both, the work is tracked in the **patcher** repo, and the driver
change is referenced from it. The patcher issue is the one you follow.

### Worked example: the Bulb cancel bug (#251 / #145)

This is the case that caused the most confusion, so it is spelled out.

The symptom: in Bulb mode on the Polaris, pressing red-cancel does not stop the
exposure, and a photo appears anyway.

Two separate pieces of work exist:

1. **Driver side — was libgphoto2 #145, now CLOSED.** The library must honour a
   cancellation request instead of carrying on and taking the photo. That code
   already exists and is correct. Proven on a real K-3 III camera on 2026-11-05:
   asking to cancel returns "Operation cancelled" and no shutter opens, no file
   is made. Nothing left to do in the driver repo.

2. **Patcher side — patcher #251, still OPEN.** The remaining work is on the
   Polaris side, so it is tracked here.

   An earlier version of this document claimed `pgphoto` never asks to cancel.
   **That was wrong and is retracted.** Disassembly of the shipped binary
   (PrivateResearch `e73e39c73`) shows pgphoto *does* install a cancel callback:
   `ctx_cancel_func` at `0xf6fd8`, installed from `gp_params_init`. The mistaken
   reading came from using `nm -D --undefined-only`, which cannot see symbols
   defined inside the binary itself.

   A second theory — that pgphoto's callback **clears its flag as it reads it**,
   so an earlier poll could consume the single cancel before the driver's guard
   sees it — was tested and **ruled out**. On a real K-3 III, eight conditions
   reads between the Bulb start and stop edges invoked the cancel callback zero
   times, and the guard still returned "Operation cancelled". Reproduced at 0, 3,
   8 and 20 intervening polls.

   **The actual root cause, settled by disassembly** (PrivateResearch `7568b8d83`,
   `polaris-evidence/k1ii-controls-20261104/handoff/K3III-251-GLOB-CANCEL-WRITER.md`):
   **nothing ever writes pgphoto's cancel flag.** It is read in three places and
   written in none, so it stays zero for the whole process. The callback therefore
   always answers "do not cancel", and the driver's correct guard is unreachable
   on the device.

   Consequence: rebuilding from driver main is **necessary but not sufficient**.
   It ships the guard; it does not make anything raise a cancel. Something in
   pgphoto must set the flag when the user cancels — `action_camera_wait_event`
   already polls it with a 1000 ms budget and is the natural place.

**Rule this establishes:** if the driver repo issue turns out to need firmware
work, close it and do the work under the patcher issue. The driver issue is not
the place firmware changes get tracked.

**Second rule, learned the hard way:** do not state what a binary does from an
inference or from one tool's output. `nm -D --undefined-only` cannot see symbols
defined in the binary; disassembly can. Two separate claims in this project were
wrong for that reason and had to be retracted.

**Third rule:** a test that supplies its own precondition proves the mechanism,
not the chain. The K-3 III probe sets the cancel flag itself, so "cancel reached
the guard and was honoured" says nothing about whether anything on the device ever
sets it. Both statements were true at once — the guard works, and it is unreachable
on the device — and passing the test hid that. Ask what a test *cannot* see before
calling it proof.

## Where code goes: branches

Both repos use `main` as the single source of truth.

- **`main`** — the accepted state of the project. Everything that is known-good
  lives here.
- **Feature branches** — temporary working branches. Land in `main` by pull
  request or a fast-forward push.
- **A release "pin"** — the exact commit each shipped firmware version was built
  from. Recorded in `docs/FWPKT-PROVENANCE-CONTRACT.md`.

### Current pin situation (changed 2026-11-05)

Previously the driver pin pointed at a feature branch instead of `main`, which
meant a release could contain code that was never formally accepted. That is now
fixed:

| Repo | `main` is now at | Was |
|---|---|---|
| libgphoto2 (driver) | `3fb26e536` | `43dccb81b` |
| patcher | `eafb143` | `c8d134d` |

Driver `main` at `3fb26e536` contains every commit that any previous release used,
plus the Bulb cancellation fix. Verified with the repo's own gate:
`scripts/pin-divergence-check.sh` reports `RESULT: PASS`. So pinning `main` cannot
lose work from an earlier release.

## What each version was (the v90 / v92 / v94 / v95 question)

Firmware versions are `6.0.0.54.NN`. The last two digits are what people call
"v90", "v92", etc.

| Version | What it added | Was it installed on the device? |
|---|---|---|
| `.90` | Bounded pgphoto startup wait | Yes, verified working |
| `.92` | Bulb cancellation handling + optional legacy Pentax USB support | **Never installed** |
| `.94` | Astro (astrophotography) features on a separate branch | Yes, verified working |
| `.95` | Corrected K-1 II shutter gate for Astro | Built only, never installed |

"v90 was good" is accurate — it is the last standard firmware that was both
installed and confirmed working. `.92` contains fixes that were built and tested
offline but never put on a device. `.94` and `.95` are the Astro line.

Because all of those commits are now ancestors of driver `main`, building from
`main` includes everything from `.90`, `.92`, `.94`, and `.95` at once. There is
nothing left to merge between them.

## Where testing happens

| Kind of test | Where it runs | What it proves |
|---|---|---|
| Offline gate (`python3 -m pytest`) | This PC, no hardware | Scripts and packaging are consistent |
| Driver suite (`meson test`) | This PC, no hardware | C code compiles and unit logic holds |
| Read-only camera probe | This PC, camera plugged in | The library can talk to a real body and read its state |
| Bulb cancel proof | This PC, camera plugged in | Cancellation is honoured before any shutter command |
| Firmware install + qualification | The Polaris device itself | The actual product works. **Cannot be done from this PC** |

The last row matters: building and flashing firmware needs a machine with Docker,
which this PC does not have. Camera tests work here; firmware installation does
not.

### Where the release gates live, and one gap

| Gate | Lives in | What it catches |
|---|---|---|
| `pytest` (542 tests) | patcher repo | Script/packaging regressions |
| `meson test` (24 tests) | driver repo | C unit logic |
| `pin-divergence-check.sh` | patcher repo | A new pin missing work the old pin had |
| `shipped-marker-check.sh` | patcher repo (`scripts/`) | A built binary that does not contain what its pin claims |

`shipped-marker-check.sh` was moved into this repository on 2026-11-05. It existed
only in PrivateResearch before that, outside the repo whose builds it guards, so
nothing ran it — which is why the v95 candidate passed every in-repo gate while
its shipped `ptp2.so` was missing the #251 cancellation fix. The provenance hash
proves an artifact matches *itself*; it never asks whether the artifact contains
the code its pin claims.

It is verified working against a real artifact:

```
bash scripts/shipped-marker-check.sh <ptp2.so> <libgphoto2-src> <built-sha> <baseline-sha>
RESULT: PASS -- nothing to verify
```

**Not yet wired into `build-astro-candidate.sh`.** Doing so needs a Docker host to
confirm where `ptp2.so` lands in the candidate output tree; wiring it blind would
either fail open (defeating the point) or break builds on a wrong path guess.

## Cameras currently attached to this PC

| Camera | USB ID | Port | Used for |
|---|---|---|---|
| Pentax K-3 Mark III | `25fb:0189` | `usb:001,019` | Bulb cancellation proof |
| Pentax K-1 Mark II | `25fb:0183` | `usb:001,020` | Read-only state checks |

Any test that would open a shutter requires explicit human approval first. The
K-1 II is in a mode where a Bulb stop command *would* open the shutter, so it is
deliberately not exercised by automated tests.

## Rules for agents working here

1. **Check which repo you are in before creating an issue.** Driver `#1xx` versus
   patcher `#2xx`. If unsure, use the C-code question above.
2. **Do not open a driver issue for a firmware binary change.** Track it in the
   patcher repo. See #145 → #251.
3. **Never rewrite history in `docs/FWPKT-PROVENANCE-CONTRACT.md`.** Rows for
   already-built versions record what *was* built. Correcting a past pin falsifies
   the record. Add a new row instead.
4. **A live pin is different from a historical pin.** `LIB_BASELINE` in
   `scripts/build-astro-candidate.sh` decides what gets built next. A provenance
   row says what was already built. Changing one does not change the other.
5. **Run `scripts/pin-divergence-check.sh` before changing any pin.** It fails if
   a new pin is missing work from the previous one.
6. **Do not claim hardware success from an offline test.** "The gate passed" and
   "the camera works" are different claims.
