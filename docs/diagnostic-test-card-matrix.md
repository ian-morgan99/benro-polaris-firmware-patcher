# Diagnostic Test Card Matrix

**Purpose**: Convert the static analysis of `polestar_app` (see
[`POLESTAR_APP_REVERSE_ENGINEERING.md`](./POLESTAR_APP_REVERSE_ENGINEERING.md))
into ground-truth runtime behaviour. Each card is a self-contained `FwPkt.zip`
that isolates one variable. Run them on a real device, watch the boot
sequence, and the result of each card either confirms or refutes a specific
hypothesis.

**Status of each card**:  Built and verified locally on 2026-08-30.
All 10 cards are on the SMB share at
`Projects/Pentax/BenroPolaris/diagnostics/2026-08-30_test-cards/`.
**Runtime results**: not yet captured — these are *designed* to be
run on a device, not assertions about what the device will do.

---

## How to read a card result

The on-device boot path (from `SP_UpgradeCheckFw @ 0x14023c`) is:

1. `rm -r /app/sd/FwPkt`
2. `unzip /app/sd/FwPkt.zip -d /app/sd/`
3. `rm /app/sd/FwPkt.zip`
4. `/app/getFwInfo.sh` (builds `crcInfo` from `firmwareInfo` + file MD5s)
5. `fopen("/app/sd/FwPkt/crcInfo", "r")`
6. `fopen("/app/sd/FwPkt/firmwareInfo", "r")`
7. 6 × `CrcMd5(...)` (one per firmware file, in
   `config` → `uImage` → `rootfs` → `appfs` → `polaris403` → `polaris413` order)
8. All match → return 0, NAND write begins, "55%" appears
9. Any mismatch → return -1, silent reboot (no error message, no log line)

A "successful" card is one where the device reaches the NAND-write phase
(the user-visible "55%" progress bar). Anything else — silent reboot, hang,
ignored, etc. — is a negative result, and which step the failure happened
at tells us what the static analysis got wrong or what variable is actually
the cause.

---

## Variable isolation

| Card | Variable isolated |
|---|---|
| A | (none — baseline) |
| B | appfs `firmwareInfo` MD5 |
| C | config `firmwareInfo` MD5 |
| D | zip integrity (unzip step) |
| E | zip filename case |
| F | `firmwareInfo` filename case |
| G | FwPkt directory location |
| H | host MD5 ↔ device MD5 equivalence |
| I | padded appfs itself (with honest MD5s) |
| J | padded appfs as-built (current symptom) |

---

## The cards

### A — STOCK baseline
**File**: `FwPkt_TEST_A_STOCK_BASELINE_2026-08-30.zip` (68,599,228 bytes)
**Source**: `~/Downloads/FwPkt.zip` (MD5 90bdad51…)
**Modification**: none — byte-identical to the user's stock reference.
**What it tests**: that the device is currently capable of ingesting a
known-good stock zip. **If this fails, the issue is environmental** (SD card,
power, mount, busybox, etc.) — not anything we've changed.
**Expected** (best-evidence, from §13 of RE doc): succeeds, reaches "55%".
**Proves if it succeeds**: the device, card, mount, busybox, and MD5 chain
all work in their current state. Any subsequent failure is therefore
caused by the *change*, not by the environment.
**Proves if it fails**: a *previously-working* configuration is now broken —
regression. Inspect dmesg, mount, busybox version.

### B — NEG CTRL: bad appfs MD5
**File**: `FwPkt_TEST_B_NEGCTRL_BAD_APPFS_MD5_2026-08-30.zip` (68,598,684 bytes)
**Source**: stock zip, then `firmwareInfo`'s `appfs MD5:` line rewritten to
`appfs MD5: 00000000000000000000000000000000` and nothing else changed.
**What it tests**: that the on-device `CrcMd5` actually does check the
appfs entry (vs silently skipping the appfs column, or treating it as
"unverified"). The appfs MD5 being invalid is the only change.
**Expected** (from §13.5 of RE doc): silent reboot (return -1 from
`SP_UpgradeCheckFw`, exactly like the current symptom).
**Proves if it fails-as-expected**: appfs *is* MD5-checked, and a bad
appfs MD5 *is* enough to trigger the silent-reboot path. The current
padded-build failure is therefore "because the MD5 mismatches" — i.e.
the device's MD5 of the padded appfs ≠ what we put in `firmwareInfo`.
**Proves if it succeeds**: appfs is NOT MD5-checked, or its MD5 is
forgotten somewhere along the path. We need to re-examine §13.5 of
the RE doc.

### C — NEG CTRL: bad config MD5
**File**: `FwPkt_TEST_C_NEGCTRL_BAD_CONFIG_MD5_2026-08-30.zip` (68,598,684 bytes)
**Source**: stock zip, then `firmwareInfo`'s `config MD5:` line rewritten to
zeros. Only the config column is broken.
**What it tests**: that the config column is also MD5-checked.
**Expected**: silent reboot.
**Proves**: config is MD5-checked. Pair with card B to establish that the
on-device MD5 machinery *is* live for these columns.

### D — NEG CTRL: truncated zip
**File**: `FwPkt_TEST_D_NEGCTRL_TRUNCATED_10MB_2026-08-30.zip` (10,485,760 bytes)
**Source**: stock zip truncated to its first 10 MB.
**What it tests**: that the unzip step actually runs (and the on-device
`unzip` is busybox, which may behave differently than host `unzip`).
**Expected**: silent reboot. `unzip` should fail (CRC error or missing
central directory), so `FwPkt/crcInfo` never appears, and `fopen`
returns NULL — `SP_UpgradeCheckFw` returns -1.
**Proves if it fails-as-expected**: the unzip step is reached, and the
device's unzip can't recover from a truncated archive.
**Proves if the device ignores the truncated file entirely** (no reboot,
just sits): the unzip step is NOT reached — the file isn't being
detected as a valid upgrade payload at all. This would be a much more
fundamental "file not picked up" failure.

### E — NEG CTRL: lowercase zip filename
**File**: `fwPkt_TEST_E_LOWERCASE_NAME_2026-08-30.zip` (68,598,708 bytes)
**Source**: stock zip, renamed to `fwPkt.zip` (lowercase 'w'). Internal
zip contents are untouched.
**What it tests**: whether the on-device lookup is case-sensitive. The
binary hardcodes `unzip /app/sd/FwPkt.zip` (capital W) at offset 0x1402e4
(per §13.5 of the RE doc). Busybox `unzip` is invoked with that literal
argument; the shell glob/case-sensitivity depends on how the upgrade
shell-script ultimately mounts the card. (Note: this is the *upgrade
daemon's* hardcoded path, not a glob — it cannot match `fwPkt.zip`
case-insensitively.)
**Expected**: silent ignore (file picked up, but `unzip` returns nonzero,
or `/app/sd/FwPkt/` never created, so `fopen` fails later).
**Proves**: confirms the case-sensitivity of the FwPkt.zip lookup
(either at the unzip shell-command level or upstream where the card
is scanned).

### F — NEG CTRL: renamed `firmwareInfo`
**File**: `FwPkt_TEST_F_RENAMED_FWINFO_2026-08-30.zip` (68,598,710 bytes)
**Source**: stock zip, internal `firmwareInfo` renamed to `firmware_info`.
**What it tests**: that the `fopen("/app/sd/FwPkt/firmwareInfo", "r")`
path is case-sensitive. The binary hardcodes the lowercase path at
offset 0x1404bc.
**Expected**: silent reboot (fopen returns NULL on step 6 of the
upgrade flow, then `CrcMd5` reads from NULL — return -1).
**Proves**: confirms that the firmwareInfo filename matters and
must be lowercase.

### G — NEG CTRL: FwPkt nested in subdir
**File**: `FwPkt_TEST_G_NESTED_FWPKT_2026-08-30.zip` (68,599,026 bytes)
**Source**: stock zip but with the entire `FwPkt/` directory moved
inside a new `MyFirmware/` wrapper. Zip layout is
`MyFirmware/FwPkt/camera/...` so `/app/sd/` after unzip contains
`/app/sd/MyFirmware/FwPkt/...` instead of `/app/sd/FwPkt/...`.
**What it tests**: that the device's lookup is *not* recursive. The
upgrade binary checks the literal path `/app/sd/FwPkt/` and would never
see `MyFirmware/FwPkt/`.
**Expected**: silent ignore (or silent reboot — depends on whether the
device even tries to load).
**Proves**: confirms FwPkt.zip must be at SD card root and unzip
to root, not in any subdirectory.

### H — STOCK with re-computed MD5s
**File**: `FwPkt_TEST_H_FWINFO_RECOMPUTED_MD5S_2026-08-30.zip` (68,598,698 bytes)
**Source**: stock zip, all 6 MD5 entries in `firmwareInfo` recomputed
from the actual file bytes (host-side, with the same MD5 algorithm).
**What it tests**: that the host's `md5sum` and the device's `md5sum`
produce identical results on the same bytes. This is a sanity check
on the equivalence assumption underlying all our MD5 reasoning.
**Expected**: succeeds (reaches "55%") — because the on-device MD5 of
each file should still match (the files are byte-identical to stock,
and the claimed MD5s are now the true MD5s).
**Proves if it succeeds**: the host/device MD5 algorithm is
interchangeable for these inputs. **This card must succeed before
any other MD5-related conclusion is trustworthy.**
**Proves if it fails**: there is a *systematic* MD5 mismatch between
host and device (very unlikely — both are MD5 — but worth confirming
once).

### I — PADDED with re-computed MD5s (SMOKING GUN)
**File**: `FwPkt_TEST_I_PADDED_RECOMPUTED_MD5S_2026-08-30.zip` (68,484,205 bytes)
**Source**: the padded build (from `builds/2026-08-30-padded-appfs/`)
with all 6 MD5 entries in `firmwareInfo` recomputed from the actual
file bytes. The padded appfs's MD5 *was* already correctly recomputed
to `4bd9131bc1bcb283a21c77bf62ff39ea` in the as-built padded zip —
this card verifies that fact and re-affirms the other 5.
**What it tests**: whether the *real* root cause is something other
than a wrong MD5. The padded build has the right MD5s; if the device
still rejects it, the cause is elsewhere (UBIFS node format, device
driver, busybox `unzip` semantic difference on the larger node block,
CRC mismatch in the UBIFS superblock, etc.).
**Expected**: success — this is the canonical "honest" padded build
and should install cleanly if the MD5 chain is the only gate.
**Proves if it succeeds**: the padded appfs is structurally valid;
the original silent failure was a packaging mistake in our end
(most likely a wrong MD5 in some earlier revision, or a stale zip
that didn't get refreshed when appfs was repadded).
**Proves if it still silently rejects**: the issue is NOT an MD5
mismatch. We have to look at the UBIFS internals, the device's
UBIFS driver, or the extraction step (busybox unzip's behaviour on
the larger node-block layout).

### J — PADDED as-is (CURRENT SYMPTOM)
**File**: `FwPkt_TEST_J_PADDED_ASIS_2026-08-30.zip` (68,484,216 bytes)
**Source**: the padded build *exactly as our patcher produced it*
(without further MD5 recomputation). This is the same zip that was
previously on the SMB share as
`FwPkt_padded_appfs_2026-08-30.zip` (MD5 92da8883…).
**What it tests**: the *exact* behaviour the user has been seeing.
**Expected**: silent reboot / ignored (the current symptom).
**Proves**: confirms the regression is reproducible with our current
artifact. If card I succeeds and card J fails, the difference between
them is *purely* the firmwareInfo MD5 lines — proving the bug is in
our packaging, not in the padded appfs itself.

---

## Recommended run order

The order is chosen to *minimise the number of cards* needed to reach a
conclusion if the user wants to stop early.

1. **A** first. If A doesn't reach "55%", the device is broken right
   now and the rest of the matrix is meaningless until that's fixed.
2. **H** second. If H doesn't reach "55%", the host/device MD5
   relationship is suspect and all MD5-based conclusions from the
   RE doc are undermined.
3. **B and C** together (one card per card-swap). These confirm the
   MD5 chain is live. If B silently reboots and C silently reboots,
   the chain is live for both. If one of them is *ignored* (no
   reboot, no "55%"), the corresponding column isn't actually checked.
4. **I** — the smoking gun. If I succeeds, the padded appfs is valid
   and our bug is purely in the as-built packaging.
5. **J** — confirms the current symptom. J should fail (reboot/ignore)
   in the same way the user has been observing.
6. **D, E, F, G** — only run if A through J haven't localised the
   problem. These are environment / packaging-shape probes.

If I succeeds and J fails, the bug is in our packaging (most likely
a stale `firmwareInfo` in some prior build, or a non-recomputed MD5
in the 2026-08-30 padded build). The fix is to ensure the
`firmwareInfo` MD5s always match the bytes that ship in the zip.

If I fails (still silent-rejects) but H succeeds, the bug is in the
padded appfs itself — the UBIFS node-block layout, or the on-device
UBIFS driver's tolerance, or the busybox `unzip` semantic. Static
analysis can't crack that one; it needs on-device debug output.

---

## What "silent reboot" looks like

The user-facing symptom is: the device powers on, shows the splash,
the LED flickers for a few seconds, and then the unit is back at the
splash with no message, no progress bar, no "55%", and no entry in
`/tmp` or `/var/log`. From the user's point of view, the SD card's
`FwPkt.zip` is gone (because step 3 of the upgrade flow is
`rm /app/sd/FwPkt.zip` regardless of MD5 result), and the firmware
version is unchanged.

If the device gets partway through NAND write, the `55%` progress bar
appears on screen (NAND write is the long step) — that is the
*positive* signal. We have to run a card and watch for ~3 minutes
to be sure (the boot + MD5 + unzip + write takes about that long).

---

## Files

| Card | Local | SMB |
|---|---|---|
| A | `/tmp/test-cards/FwPkt_TEST_A_STOCK_BASELINE_2026-08-30.zip` | `diagnostics/2026-08-30_test-cards/FwPkt_TEST_A_STOCK_BASELINE_2026-08-30.zip` |
| B | `/tmp/test-cards/FwPkt_TEST_B_NEGCTRL_BAD_APPFS_MD5_2026-08-30.zip` | `…/FwPkt_TEST_B_NEGCTRL_BAD_APPFS_MD5_2026-08-30.zip` |
| C | `/tmp/test-cards/FwPkt_TEST_C_NEGCTRL_BAD_CONFIG_MD5_2026-08-30.zip` | `…/FwPkt_TEST_C_NEGCTRL_BAD_CONFIG_MD5_2026-08-30.zip` |
| D | `/tmp/test-cards/FwPkt_TEST_D_NEGCTRL_TRUNCATED_10MB_2026-08-30.zip` | `…/FwPkt_TEST_D_NEGCTRL_TRUNCATED_10MB_2026-08-30.zip` |
| E | `/tmp/test-cards/fwPkt_TEST_E_LOWERCASE_NAME_2026-08-30.zip` | `…/fwPkt_TEST_E_LOWERCASE_NAME_2026-08-30.zip` |
| F | `/tmp/test-cards/FwPkt_TEST_F_RENAMED_FWINFO_2026-08-30.zip` | `…/FwPkt_TEST_F_RENAMED_FWINFO_2026-08-30.zip` |
| G | `/tmp/test-cards/FwPkt_TEST_G_NESTED_FWPKT_2026-08-30.zip` | `…/FwPkt_TEST_G_NESTED_FWPKT_2026-08-30.zip` |
| H | `/tmp/test-cards/FwPkt_TEST_H_FWINFO_RECOMPUTED_MD5S_2026-08-30.zip` | `…/FwPkt_TEST_H_FWINFO_RECOMPUTED_MD5S_2026-08-30.zip` |
| I | `/tmp/test-cards/FwPkt_TEST_I_PADDED_RECOMPUTED_MD5S_2026-08-30.zip` | `…/FwPkt_TEST_I_PADDED_RECOMPUTED_MD5S_2026-08-30.zip` |
| J | `/tmp/test-cards/FwPkt_TEST_J_PADDED_ASIS_2026-08-30.zip` | `…/FwPkt_TEST_J_PADDED_ASIS_2026-08-30.zip` |

The local copies in `/tmp/test-cards/` will be deleted on next reboot.
The SMB copies will persist.

---

## Verification (host-side, pre-device)

The `build_test_cards.py` script verifies each card before delivery:

| Card | appfs claim | appfs actual | config claim | config actual | Verdict |
|---|---|---|---|---|---|
| A | `47f2ae68…` | `47f2ae68…` | stock | stock | OK / OK |
| B | `00000000…` | `47f2ae68…` | stock | stock | X / OK *(intentional)* |
| C | `47f2ae68…` | `47f2ae68…` | `00000000…` | stock | OK / X *(intentional)* |
| D | (truncated) | — | — | — | not a zip *(intentional)* |
| E | `47f2ae68…` | `47f2ae68…` | stock | stock | OK / OK *(case probe)* |
| F | (file missing) | — | — | — | no firmwareInfo *(intentional)* |
| G | (file missing) | — | — | — | no firmwareInfo *(intentional)* |
| H | `47f2ae68…` | `47f2ae68…` | recomputed | recomputed | OK / OK |
| I | `4bd9131b…` | `4bd9131b…` | padded | padded | OK / OK |
| J | `4bd9131b…` | `4bd9131b…` | padded | padded | OK / OK |

Cards D, F, G are flagged "intentional" because their structure makes
them unsuitable for full firmwareInfo verification (truncated / renamed
/ nested). They are nonetheless correctly built for their purpose.

---

## Reproducing this matrix

The test cards were generated by
[`docs/tools/build_test_cards.py`](./tools/build_test_cards.py) from two
source zips:

- Stock reference: `~/Downloads/FwPkt.zip`
- Padded build: `builds/2026-08-30-padded-appfs/FwPkt.zip`

The script is self-contained and prints a verification table at the end
showing each card's claimed vs actual MD5s. To rebuild:

```
python3 docs/tools/build_test_cards.py
```

It writes to `/tmp/test-cards/` and copies to the SMB share at
`Projects/Pentax/BenroPolaris/diagnostics/2026-08-30_test-cards/`.

The script does not require a connected device — it's pure host-side
zip rewriting. The only device-side step is loading the SD card and
watching the boot sequence.
