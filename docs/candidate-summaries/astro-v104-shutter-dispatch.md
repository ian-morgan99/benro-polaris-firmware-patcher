# astro-v104 — source-aligned shutter release (#309)

Supersedes 6.0.0.54.103. Published bytes of .102 and .103 are immutable under this
project's release policy, so the #309 fix ships as a new candidate rather than by
re-writing a published archive.

## What changed

### The Astro WebUI now follows Benro Connect's shutter contract (#309)

`fire()` in `container/astro/webui/app.js` sent one hardcoded payload for every
press: `state:1;bulb:0;c:0;`. Two defects, both confirmed against the device's own
traffic log rather than inferred from the decompilation alone.

**`c:0` is the wrong trigger.** It belongs to Benro Connect's separate
continuation-shooting stop branch. The ordinary single capture and the ordinary
stop both use `c:-1`. In `/app/sd/system/log/Mlog_*.log` on a live Polaris,
`state:1;bulb:0;c:-1;` appears 27 times against 5 for `c:0`.

**There was no bulb path at all.** A timed long exposure could not be started from
the WebUI, so wanting one meant putting the phone down and opening Benro Connect.
The same log shows `state:1;bulb:5;c:-1;`, `bulb:2` and `bulb:42` — duration rides
in the `bulb` field.

Dispatch and completion reconciliation moved to `container/astro/webui/shutter.js`,
which is DOM-free so it can be asserted under node. Before this the payload lived
inside a pointer-event handler and nothing could test it without a browser, which
is how `c:0` survived. 17 tests cover M-mode single capture, timed B with the
selected duration, cancel-during-exposure including the stop command and terminal
outcome, the queued-is-never-reported-as-shot rule from #279, stale-reply
rejection, negative-state refusals, and silence-past-deadline reporting unknown
rather than failed. Mutation-tested: reintroducing `c:0` fails 5 of them, and node
exits 1 on failure so the pytest wrapper sees it rather than reporting a silent
pass.

### The subsystem field is deliberately not client-settable

`/api/link/send` calls `plink_send(cmd, pol->sub, args)` and ignores anything the
page sends; 264 is registered `{ 264, "photo", 2, 1, ... }`, so shutter commands
already ride subsystem 2 — which the captured traffic confirms (`type:2` for both
M and timed B). A client-side override would be a second source of truth for a
field the head silently ignores when wrong. `test_shutter_module_exists_and_is_shipped`
asserts `index.html` loads the file, because a JS suite can pass while the page
never references it.

### B mode is an explicit user intent, never an inference

#309 asks for B to be verified from the camera's mode information and an unknown
read rejected rather than guessed. That cannot be satisfied as written: no opcode
in our documented set reports the camera's exposure mode. 284 is the *mount's*
operating mode (Photo/Sun/Astro/Free program/Video) and 286 is the connected
camera's identity; neither says M or B. Inferring it from 268's shutter-list shape
is forbidden by the same rule and would be wrong anyway — a body can offer "B" in
its list while sitting in M.

So `bulb:>0` only ever reaches the wire when the user typed it into the new field.
Empty means "the camera's own shutter setting", which is what Benro Connect sends
for an ordinary capture and is safe in any mode. Fractional durations are refused
rather than floored: the markup allows `step 0.5`, and flooring 2.5 to 2 would run
a shorter exposure than was asked for with nothing on screen to say so.

### Stop, not retry

Releasing during a running bulb sends exactly one source-aligned stop
(`state:0;bulb:0;c:-1;`). No blind retry or alternate-subtype fallback anywhere on
264, per the issue's double-fire warning. The hold-to-fire safety gate is unchanged.

## Verification

- `python3 -m pytest tests/` → **657 passed, 15 skipped**.
- `node tests/test_astro_shutter.js` → 17 passed; exits 1 when the defect is
  reintroduced.
- `app.js` and `shutter.js` both boot under a DOM stub with `shutter.js` first, so
  `SHUTTER` is a real browser global and not only `module.exports`. This was the
  failure mode that would have killed the entire page at boot and that no JS unit
  test can catch.
- `embed_webui.py` emits `asset_shutter_js`, so the new file reaches the device
  inside `polaris-httpd`.
- `scripts/build-doctor.sh` → GREEN, 17 checks.

## Not verified on hardware

**No capture has been taken with this code.** The payloads match observed Benro
Connect traffic byte for byte, and the server already puts them on subsystem 2, but
the camera's response to them *from the WebUI* has not been observed. Specifically
unproven: that a timed B started here completes rather than being refused, and that
the stop lands within the window the head expects. That needs the supervised
hardware round (#307).

## Also in this cycle (already published in .103, restated for continuity)

- #310 — eight shipped scripts committed non-executable; `polaris-goto-solve.sh`
  exited 2 and three features silently disabled. Fixed and pinned by a git-mode
  test.
- #311 — published Route A never told anyone to run `install_astro.sh` or to copy
  `astrometry-indexes.zip`; following it flashed firmware and started nothing.
- #292 — the archive-level release gate was absent from the release branch entirely;
  recovered, wired into both producers, and made abortive rather than advisory.
