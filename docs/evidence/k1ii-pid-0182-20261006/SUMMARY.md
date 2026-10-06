# K-1 II "why might that not work" — 2026-10-06

Question asked: analyse the K-1 II implementation and explain why it might not
work. Answer: the body has a second USB product ID that no PID gate in the stack
accepts. Filed as **ian-morgan99/benro-polaris-firmware-patcher#179**.

Headline: this explains "the K-1 II never reaches vendor mode" for a `0182`
attachment. It does **not** explain the preview/`NoUpdateImage` instability seen
on `0183` sessions, which did bind correctly.

## 1. The body declares two PIDs

Extracted from the K-1 II's own firmware image
(`PrivateResearch/pentax_firmware/PENTAX_K-1_Mark_II_FW_v2.51_extracted/k1II_v251/fwdc240b.bin`,
offset `0x95f7c`, duplicate at `0x67ae5a`):

```
0x095f7c  fb 25 82 01 31 0a 83 01 07 4a 12 02 1c 49 4d 47
          ^^^^ ^^^^^^          ^^^^^^
          0x25fb 0x0182        0x0183
```

Same block located in seven bodies by anchoring on the adjacent `IMG`/`DSC_`
filename-template fields:

| body | image | offset | PIDs | in our table |
|---|---|---|---|---|
| K-1 II v2.51 | `fwdc240b.bin` | `0x95f7c` | **`0x0182`, `0x0183`** | `0x0183` |
| K-1 v2.51 | `fwdc228b.bin` | `0x86b87` | `0x0178`, `0x0179` | `0x0179` |
| KP v1.31 | `fwdc232b.bin` | `0x9185f` | `0x017e`, `0x017f` | `0x017f` |
| K-70 v1.16 | `fwdc234b.bin` | `0x8e094` | `0x017c`, `0x017d` | `0x017d` |
| K-3 II v1.12 | `fwdc230b.bin` | `0x172` | `0x017a`, `0x017b` | `0x017b` |
| 645Z v1.30 | `fwdc224b.bin` | `0x170` | `0x0166`, `0x0167` | `0x0167` |
| K-3 v1.43 | `fwdc220b.bin` | `0x16e` | `0x0164`, `0x0165` | `0x0165` |

Not recoverable in plaintext from K-3 III v2.20 (`fwdc233b.bin`).

The documented `fb25 <pid1> <pid2>` pattern (`pentax-utils.c:653`,
`library.c:2830`) is too strict: the K-1 II inserts a 2-byte field (`31 0a`)
between the PIDs, so a naive scan reports "no pair found" for exactly the body
that matters.

## 2. Observed on hardware: detected as `0183`, failed as `0182`

Detected — `docs/evidence/k1ii-k01-ov7-fieldtest-2026-09-10` (commit `46f3e67`),
`Clog_000007`:

```
idVendor: 25fb  idProduct: 0183
--- list count = 1
Setting abilities ('Pentax K-1 Mark II (PTP mode)')...
Pentax init stage vendor enable succeeded; function flags 0x00000003.
----- gp_camera_init ret 0
```

Not detected — `docs/evidence/o-v12n-clean-raw-failure-2026-09-24`,
`Clog_000140`, four consecutive starts (00:11, 00:14, 00:16, 00:17):

```
idVendor: 25fb  idProduct: 0182
[camera-usb] supervisor ready; identity=1-1.2|25fb:0182|1:3
--- list count = 0
Setting abilities ('Pentax K-3 Mark III (MTP mode)')...
The port you specified ('usb:001,005') can not be found.
sp_Gphoto_Init ret -5        (GP_ERROR_UNKNOWN_PORT)
```

The same log rules out "autodetect is broken": minutes later a `25fb:0131` (K-01)
gives `list count = 1` and `ret 0`. The failure tracks the PID.

`0182` appears nowhere else in retained evidence and is absent from upstream
`usb.ids`, which is why it was never triaged.

## 3. Four PID-keyed gates, all fail closed

| # | gate | location | effect at `0182` |
|---|---|---|---|
| 1 | camera table | `library.c:2821` (`0x0183` only) | no abilities → `list count = 0` |
| 2 | R0 research containment | `pentax-utils.c:1112` | capture/preview/config never advertised (`library.c:11743`, `:3257`) |
| 3 | model lookup | `pentax-utils.c:626` | `supported_model = 0` → vendor mode off → preview returns `GP_ERROR_NOT_SUPPORTED` |
| 4 | `pentax_candidate` | `library.c:11742` | issue #33 stale-session recovery skipped |

Gate 3 additionally uses exact `strcmp` where siblings use `strncmp` prefixes, so
even with the PID fixed a mode suffix would still disable vendor mode — and
`stage2_policy.c:48` already records that MTP-mode bodies emit suffixed/spaced
runtime strings.

## 4. Cross-repo predicate disagreement

`container/stage2_policy.c` `stage2_model_is_k1_mark_ii()` matches the
case-insensitive substring `"k-1 mark ii"`; the camlib requires an exact string
plus PID. The two can disagree about which body is attached. Today the camlib is
stricter, so the symptom is "no Pentax support" rather than "wrong policy" — but
that only holds while it stays the stricter of the two.

## 5. Unverifiable citation behind the 8 s preview interval

`docs/evidence/k1ii-live-test-2026-09-15/stream-probe-8080.md` is cited as the
measurement behind `STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_K1II_SECS` (= 8,
`stage2_loader.c:599`) in five places: `stage2_loader.c:375`, `:595`, `:704`,
`stage2_policy.c:62`, `stage2_policy.h:10`. The path does not exist and
`git log --all` shows no record of it ever existing. The value may be correct;
the evidence is not retrievable.

## 6. Corrections made while investigating

- An earlier note recorded #136 as the report of the K-1 II enumerating as
  `25fb:0182`. That is wrong: #136 in the LibGphoto2 repo is "Livestream slow on
  Canon EOS 650D". The `0182` observation is in
  `o-v12n-clean-raw-failure-2026-09-24` only.
- `0182` and `0189` in that log are different physical bodies on the same port
  (`1-1.2`), not one body switching USB modes: dmesg identifies the `0189` as
  `PENTAX K-3 Mark III`, serial 8093033.

## 7. Fix implemented (not yet in a qualified build)

Committed to the libgphoto2 fork at **`1b65cbe0a`** ("ptp2: accept the K-1 II's
second product ID"), pushed to `ian-morgan99/libgphoto2` `main`. It adds the
`0x0182` camera-table row, accepts either PID in `pentax_lookup_model()` and
`pentax_pid_is_research_capable()`, and adds unit coverage including a negative
test that the original K-1 (`0x0179`) is not reachable through either K-1 II PID.

Two implementation notes worth keeping:

- The table row needed a distinct model name — `tests/test-camera-list.c` fails
  the build on duplicate model names. The row is therefore
  `Pentax:K-1 Mark II (PTP mode, USB id 0182)`. That is safe because
  `pentax_lookup_model()` matches the PTP `deviceinfo.Model`, not the abilities
  name, and the stage2 predicates match the `pentax` / `k-1 mark ii` substrings,
  both of which survive unchanged.
- The exact `strcmp` on the model string was deliberately **not** relaxed. It
  matches the K-3 III's own guard and no observed string has ever failed it;
  changing it would be an untested widening.

`meson test` after the change: 14 OK, 2 fail (`test-gp-port`, `test-gphoto2`) —
byte-identical to the pre-change baseline, so no regression.

This SHA is **not** a qualified source pointer. Per
[`canonical-pentax-source.md`](../../canonical-pentax-source.md) that pointer
moves only with a complete matched-stack upgrade, so the fix reaches hardware only
when the next candidate is built from a source input containing `1b65cbe0a`.

## 8. Testable now, without the body

- `grep -c "list count = 0" docs/evidence/o-v12n-clean-raw-failure-2026-09-24/Clog_000140.log`
- the descriptor extraction in §1;
- unit coverage for `0x0182` in `tests/test-pentax-utils.c` (`:287`, `:611`).

With the body on the Polaris: read `idProduct` from `scanUsb` and establish
whether it changes with the camera's USB Compatibility menu setting. That is the
one open question the offline evidence cannot settle — §1 proves the body
*declares* both IDs but not which menu state selects which.
