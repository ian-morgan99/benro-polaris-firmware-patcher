# v70 on K-3 III: what the two reported failures actually are

Operator tested `6.0.0.54.70` on a K-3 III. Everything worked except:
1. non-timed bulb (held shutter)
2. an extra "B" entry in the app's list of exposure times

I probed the live rig to reproduce both. **Neither reproduced, and the reason matters more than the
result.**

## The dial was not on B during my probe

Command 268 returned a **56-entry timed list** (`00-01` … `20-00`, current index 0 = `00-01`). Per
#208, when the dial is physically on B the K-3 III collapses this to a single entry (`R:00:00,;`). So
the camera was on a timed dial position for the whole session.

Both reported symptoms are B-mode symptoms. I could not reproduce either one without the dial on B.

## Symptom 1: held bulb did fire and produced files

Sent both app forms — `state:1;bulb:0;c:-1;` and `state:1;c:-1;`. Each produced a full state timeline
`1 -> 4 -> 0` and a real file on the SD card (`SP_0439.dng`, `SP_0440.dng`, ~30 MB each). No `-6`, no
failure.

So at the protocol level the held form is **not** being refused. What I cannot tell from this is
whether the exposure was actually a held shutter or just a short timed one — state went 1→4→0 in about
5 seconds, which looks short, and the DNGs carry no `ExposureTime` tag to confirm duration.

This matches the trampoline's documented behaviour: `bulb:0` is deliberately routed to the stock burst
path, because across every captured session log `bulb:0` is the normal-capture form (108 occurrences)
and a positive `bulb:N` only appears on explicit long-exposure requests.

## Symptom 2: there is no B entry in our list

The 56 entries all parse as durations — zero non-duration entries, no `B`, no `00:00`. And our
libgphoto2 fork does not touch the shutter getter at all: `_get_Ricoh_ShutterSpeed` still just iterates
`dpd->FORM.Enum.NumberOfValues` straight from the camera. Nothing in `container/*.py` injects an entry
either.

So the "B" the operator sees is either the camera's own entry when the dial is on B, or something the
Benro app adds to its own UI list. It is not something we are adding.

## Two captures I fired by accident

The probe script's docstring says "read-only", which was wrong: symptom B sends real capture requests.
Two images were written to `/app/sd/normal/` on the rig during this investigation. They are harmless
test frames but they are mine, not the operator's.

## What this means for a .71 release

There is no fixable defect in these two symptoms that I can currently see:

- The held-bulb path fires and produces files.
- We do not add a B entry to the shutter list.
- Both are B-mode behaviours and the rig was not in B mode when probed.

Cutting `.71` now would ship either nothing functional or changes unrelated to what the operator
reported. It also would not resolve the open question on `.70` — whether the raised poll budget is
ever actually consulted, given the loop exits early once `sp_camera->0xd0` becomes 1.

## What is needed to close this

1. **Dial physically on B**, then re-run the probe: dump 268 (expect the collapsed single-entry list)
   and send the held form. That is the only way to see the B entry and a genuine held exposure.
2. Confirm what "did not work" looked like in the app — refused, hung, wrong duration, or no file. The
   protocol says these fired, so the failure may be in how the app reports the result.
3. For `.70`'s own question, an NR-on long exposure with the poll instrumented.

## Related open issues

#205 (no dial gate — deliberate, documented), #206/#208/#209 (canary-probe mishandles the B-mode list
shape — real bugs, but test tooling, not shipped firmware), #173 (bulb duration ignored), #186.
