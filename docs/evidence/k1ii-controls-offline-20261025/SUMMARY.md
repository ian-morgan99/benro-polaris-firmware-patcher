# K-1 II control failures — plain-English re-analysis of one log file

**What this is:** I read a 12,710-line debug log from a Benro Polaris gimbal that had a Pentax K-1 II
mounted. No hardware work was done; everything here comes from that one file.

**Which firmware:** the log is from `6.0.0.54.65`. It is the newest K-1 II log we have — nothing here
has been re-checked on `.68`, `.69` or `.70`.

---

## Finding 1: issue #232 has the diagnosis backwards

Issue #232 says two camera settings (`0xd02b` = focus peaking, `0xd035` = live-view mode) have a
broken decoder, so those controls never appear in the app.

**The log shows the opposite.** Those same two settings decoded correctly five times earlier in the
same session, then failed four times later:

```
14:21  decoded fine
21:43  decoded fine (four more times)
21:44  FAILED
21:45  FAILED
21:47  FAILED
21:51  FAILED
```

A decoder that is broken is broken every time. It cannot work five times and then fail four. So the
decoder is not the problem.

**What actually changed:** the camera started sending back rubbish. When it works, the reply is a
proper 16-byte description. When it fails:

- `0xd035` sends only **6 bytes**. A valid description needs at least 8 bytes just for its header, so
  there is genuinely nothing to decode.
- `0xd02b` sends 16 bytes, but one field says "data type = 0", which is not a legal value — and the
  same setting reports data type 2 when it works.

So "descriptor parse failed" is the **symptom** of the camera sending short or garbage replies, not
the cause of them.

## Finding 2: nothing is actually missing from the app

Issue #232 also claims these controls never reach the app's menu. I checked all nine times the full
menu was dumped to the log:

| menu dump | did the description fail? | is the real Focus Peaking control there? |
|---|---|---|
| 1-5 | no | **yes** |
| 6-9 | **yes, failed** | **yes** |

The focus-peaking control shows up every single time, including all four times its description failed.
It is labelled "Pentax Focus Peaking", type RADIO, current value "off". The two entries that do fail
are separate read-only diagnostic rows ("...Descriptor"), which exist only to dump raw bytes.

**Consequence:** the fix TA suggested — show unparseable descriptors as "unsupported" instead of
dropping them silently — is solving a problem that is not happening here. Nothing is being dropped,
and no working control is lost because of it.

## Finding 3: three separate issues are really one problem

Issue #233 asks whether exposure-compensation failures share a cause with #232. They do, and it is
cleaner than "probably related". Every menu dump in the log carries a camera state number. Sorting the
failures by that number gives a perfect split with no exceptions:

| what broke | when camera state = 0 | when camera state = 3 |
|---|---|---|
| exposure compensation read | works (2 times) | **fails (11 times)** |
| white balance read | works (2) | **fails (11)** |
| image format read | works (3) | **fails (6)** |
| shutter speed write | never fails (0) | **fails (4)** |

State 0 = everything works. State 3 = basically nothing works. So #232, #233 and the read failures in
#235 are **one problem**, not three. Fixing the write path alone would not bring exposure compensation
back, which is exactly the trap TA warned about.

**What I could not find:** what "state 3" means. It is not documented anywhere in our code — our own
`wait-for-rig.py` only knows state 1 (ready), -5 (no camera) and -2 (present but asleep). I am not
guessing at a meaning.

## Finding 4: TA was right about issue #234, and I confirmed it in the source

TA said `ret:-2` means "bad parameters", not "not supported". Checked directly:

```c
#define GP_ERROR_BAD_PARAMETERS  -2
#define GP_ERROR_NOT_SUPPORTED   -6
```

So the autofocus failure was mislabelled. Issue #234 has been retitled to say focus is simply
**untested**, and that one disable call returned -2.

One thing I looked at and could not settle: the code reads the on/off flag twice and uses it
**opposite ways** — once inverted, once not. That *could* be a bug, or it could be two different
settings that legitimately want opposite values. I could not work out which setting each write targets,
so I am reporting it as unresolved rather than claiming an inversion. TA asked for proof before making
that claim, and I do not have it.

## Finding 5: a mistake I published earlier, now corrected

In my comment on issue #230 (the long-exposure fix) I said the file-waiting loop "breaks when a status
field is **not** 1". **That is backwards.** Having re-read the machine code carefully:

- while the field is **not** 1, the loop **keeps waiting**
- when the field **becomes** 1, the loop **stops early**
- it also stops if it runs out of its attempts (600 before `.70`, 10,000 after)

The field turned out to be the camera's own state variable (`sp_camera`, offset `0xd0`), read the same
way in sixteen places across the program — one of them compares it to 3 and another to 2, so it holds a
small number of states rather than being a yes/no flag.

**Why this matters for the `.70` fix:** if that state flips to 1 shortly after the shutter closes, the
loop exits immediately and never uses the extra time I gave it, meaning `.70` would change nothing.
I cannot tell from this log whether that happens — the log is a K-1 II on old firmware and does not
cover this path. **This is still the main reason `.70` is installed but not confirmed to work.**

---

## What I could not do, and why

- Work out what state 3 means — not documented anywhere we have.
- Work out which camera setting each autofocus write targets.
- Re-test any of this on current firmware. The rig currently reports `state:-5`, meaning no camera is
  attached at all, so nothing here can be confirmed on hardware today.

**Sample size warning:** this is one session, one boot, and only nine menu dumps — four of them in the
bad state. The pattern is perfectly consistent within that small sample, but it is a small sample.
