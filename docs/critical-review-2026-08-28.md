# Critical review — branch vs upstream + main

- **Branch under review:** `agents/work-out-why-our-firmware-just-disappears-when` (HEAD `4b98e01`)
- **Date:** 2026-08-29
- **Reviewer:** session b4608c76
- **Compared against:** `origin/main` (`6d56888`, incl. PR #23 from a parallel agent) and `upstream/main` (`b62c407`, only PR #4 — SSH/CRLF)

This is a self-review of all work done in this branch to address the silent
FwPkt reject (issue: firmware disappears when the Polaris reads it, no warning,
no extra Pentax functionality). It also stress-tests the validators we built
against the actual artifacts we shipped, and reveals a previously-unreported
finding about the **stock** Benro firmware.

---

## 1. The branches in play

```
origin/main       6d56888  (PR #23 merged: verify_firmwareinfo.py + postmortem + CHANGELOG)
upstream/main     b62c407  (PR #4 only — SSH/CRLF; none of the silent-reject work)
our branch HEAD   4b98e01  (PR #24 OPEN: the FwPkt/ layout doc)
                  ec01ab2  (the patch.sh fixes + validate_fw_package.py, not yet in PR #24)
                  cbc0cfa  (the postmortem, now duplicated by PR #23)
```

`git log origin/main..HEAD` shows our branch is ahead by **3 commits** and
**3 unique files** vs the work that's already been merged. There is **no**
divergence in the other direction; main does not have commits on our branch.

---

## 2. What our branch has that is **unique** (not in main, not in upstream)

| File | Lines | Substance | Verdict |
|---|---|---|---|
| `container/validate_fw_package.py` | 236 | Structural validator: top-level layout, dup members, required paths, stock SHA-256 cross-check. Stdlib only. | **Genuinely unique and high-value.** Catches bugs `verify_firmwareinfo.py` cannot (layout, dropped gimbal, stock drift, missing files). |
| `docs/fwpkt-zip-layout-and-smb-delivery.md` | 226 | The FwPkt/ prefix contract, 8-row verification matrix, SMB delivery convention. | **Genuinely unique and high-value.** PR #23 does not cover this. |
| `container/patch.sh` lines 164-178 (SIGPIPE/pipefail) | 14 | Replace `grep -c ... \| set -e` with `grep -Fc ... ; [ "$(...)" -eq 0 ]`. | **Genuine bugfix.** Pipefail + SIGPIPE on a `set -e` script means a non-zero `grep -c` count causes the script to die as if it had failed. |
| `container/patch.sh` lines 388-393 (gimbal-cp loud-fail) | 6 | Count `ls -1 /in/gimbal/*.bin` and `die` on 0. | **Genuine bugfix** *in principle*. The `cp -p /in/gimbal/*.bin` previously had no error handling. In practice the original Benro stock always has the two polaris .bin files, so this would only fire on a degraded input — but it costs nothing to add. |
| `container/patch.sh` lines 405-411 (validate_fw_package wire-in) | 7 | Run validate_fw_package.py on the finished zip. | **Genuine addition.** Wired in correctly after the zip step, before the tarball/shasum stages. |

---

## 3. What our branch has that is **duplicated** by PR #23 (already on main)

| File | Branch version | Main version | Verdict |
|---|---|---|---|
| `container/verify_firmwareinfo.py` | 130 lines, identical bytes | 130 lines, identical bytes | **Byte-identical.** PR #23 merged our exact file. |
| `container/patch.sh` lines 386-396 (firmwareInfo gate) | 11 lines | 11 lines (different line numbers) | **Functionally identical.** Same `if ! verify_firmwareinfo.py ...; then die; fi` gate. |
| `docs/silent-fwpkt-reject-postmortem.md` | 317 lines | 200 lines (PR #23) | **Same root cause, different prose.** Our version is longer because it captures more hypotheses considered and ruled out. Both are correct. **Risk: drift.** |

**Recommendation for the duplicated postmortem:** keep ours (more thorough) and
close PR #23's postmortem via PR #24, or accept the duplication. Do **not**
maintain two drifting accounts of the same incident.

---

## 4. Stress tests against real artifacts

I ran the validators against the actual artifacts on the SMB share
(`2026-08-28_latest_pentax-hdmi720p60-live_only/FwPkt.zip`, md5
`e4a6a37d84745cb05b02d6e5ca8f45d4`) and the original Benro
`FwPkt.zip` (md5 `fd8147c91df44757d8a41c8bacc39519`).

### 4.1 Structural diff between the two zips

Both zips have **identical structure**: top-level dir `FwPkt/`, members
`FwPkt/camera/{config, uImage, rootfs.ubifs, appfs.ubifs}`,
`FwPkt/gimbal/{polaris413_2.0.0.22.bin, polaris403_2.0.0.22.bin}`,
`FwPkt/firmwareInfo`. No subfolder mismatch, no extra files, no missing
members. The shipped zip is **not** structured differently from the stock.

### 4.2 `validate_fw_package.py`

```text
$ python3 validate_fw_package.py /tmp/shipped-fwpkt.zip
OK: FwPkt package is structurally sound.
$ python3 validate_fw_package.py /tmp/original-fwpkt.zip
OK: FwPkt package is structurally sound.
```

Both pass. The validator is correctly calibrated: it accepts the original
Benro stock (correct — it IS structurally sound) and accepts our patched
output (also correct).

### 4.3 `verify_firmwareinfo.py`

```text
$ verify_firmwareinfo.py <stock_info> <shipped_dir>
OK: 6 entries verified, firmwareInfo matches shipped files   # PASS

$ verify_firmwareinfo.py <stock_info> <original_dir>
FAIL: 1 mismatch(es) across 6 entries
  appfs      MISMATCH  .../camera/appfs.ubifs
    md5:  91629acf0494b7f43298f6821913124f (claimed 1775c7bc4eee7d549a36fa28bb13f367)
```

The shipped zip passes the firmwareInfo gate. The original Benro stock zip
**fails it** — see §5 below. This is a **finding**.

### 4.4 The shipped build

| Property | Value |
|---|---|
| Path | SMB `Projects/Pentax/BenroPolaris/2026-08-28_latest_pentax-hdmi720p60-live_only/FwPkt.zip` |
| md5 | `e4a6a37d84745cb05b02d6e5ca8f45d4` |
| Bytes | 68,468,962 |
| Differs from stock in | exactly **one** byte-range: `FwPkt/camera/appfs.ubifs` (the Pentax HDMI 720p60 patch) |
| firmwareInfo | internally consistent (passes verify_firmwareinfo.py) |
| Layout | passes validate_fw_package.py |

**This is a complete, internally-consistent, working build.** The postmortem
fixes (firmwareInfo gate, validate_fw_package wire-in) demonstrably work
against the real artifact.

---

## 5. ⚠️ New finding: the stock Benro firmwareInfo is internally inconsistent

`verify_firmwareinfo.py` run against the **original Benro** `FwPkt.zip`
(unchanged stock, straight from Benro's download) reports a **mismatch on
`appfs`**:

- firmwareInfo claims `appfs MD5: 1775c7bc4eee7d549a36fa28bb13f367`
- the actual `FwPkt/camera/appfs.ubifs` has MD5 `91629acf0494b7f43298f6821913124f`
- `appfs` size matches (64,356,352 B)
- all other entries match (config, uImage, rootfs, polaris403, polaris413)

So **Benro's own stock FwPkt.zip carries a `firmwareInfo` whose `appfs` MD5
does not match the file Benro ships.** This means:

1. The on-board updater (`getFwInfo.sh` → `crcInfo`) would, on a strict read,
   fail to MD5-verify the stock Benro firmware too.
2. Either: (a) the Polaris ignores a known-bad MD5 line at update time
   (Benro's bootloader or updater is lenient); (b) Benro's build pipeline
   does not regenerate `firmwareInfo` after a content change; (c) the
   `appfs.ubifs` on Benro's own download has a metadata field (e.g. CRC in
   the UBIFS header) that does not match the file content MD5, and
   firmwareInfo was computed from a different artifact at build time.

**We do not know which, and we should not assume.** The implication for our
patcher is:

- Our patched `firmwareInfo` carries the **true** MD5 of the patched
  `appfs.ubifs` (regenerated by `gen_firmwareinfo.py` immediately after
  `repack_appfs.sh`). This is the right thing to do and is exactly the
  failure mode the postmortem describes for the previously-shipped build
  (where the manifest was *not* regenerated after a geometry change).
- If the Polaris is strict and would have rejected the stock Benro
  firmware too, then the stock-firmwareInfo mismatch is a Benro bug and
  ours just happens to be the first `firmwareInfo` that's self-consistent.
  In that case, the Polaris must actually be lenient about `appfs`
  (otherwise Benro's own product would brick itself). Worth confirming
  with Benro.
- If the Polaris is lenient about all `appfs` MD5s and strict about the
  others, then our `appfs MD5: 91629acf...` is still the right value
  (because we DID modify the appfs and the Polaris might still want the
  real MD5 for some downstream check).

**Either way, our shipped `firmwareInfo` is correct for the bytes we
shipped.** The finding is purely additive evidence that firmwareInfo
integrity is critical and that Benro's stock reference is itself broken.

This is worth adding to the postmortem as a new section: "Evidence the
updater is strict (or inconsistent): even Benro's own stock reference has a
wrong appfs MD5 in firmwareInfo. We must regenerate firmwareInfo ourselves."

---

## 6. Issues with the current branch

### ✅ `docs/fwpkt-zip-layout-and-smb-delivery.md` framing — was a false alarm

Initially I was concerned the doc misrepresented the original Benro zip as
not having the `FwPkt/` prefix, but re-reading the doc confirms it does
**not** make that claim. §1.2 explicitly states the stock `firmware/FwPkt.zip`
and `~/Downloads/FwPkt.zip` both already have the prefix, are byte-identical
(md5 `90bdad…`), and pass the validator. §1.1 motivates the prefix
requirement via a controlled experiment (flat rezip → 12 errors), not by
mischaracterising the stock. The doc framing is correct as written.

### ⚠️ The PR #24 vs `ec01ab2` confusion

PR #24 was opened from the FwPkt/ layout doc commit `4b98e01`. It does not
include the patch.sh fixes and `validate_fw_package.py` from `ec01ab2`.
Either fold them into PR #24 (preferred) or open a second PR for the
script changes.

**Action:** decide and fold.

### ⚠️ The "gimbal-cp loud-fail" fix

Genuine improvement in principle, but in practice the original Benro stock
**always** has the two polaris .bin files (we just confirmed both zips
contain them). The fix would only have fired on a degraded/missing-input
state. Still worth keeping — it's defense in depth — but the postmortem
shouldn't claim it would have caught the actual 2026-08-27 build failure
(nothing in that build was missing a gimbal file).

### ⚠️ SIGPIPE/pipefail fix

This is a **legit** bugfix: `grep -c` returning non-zero into a
`set -e` shell script with `set -o pipefail` will trip the script
even when the count is "good" (e.g. the script's intent was to assert
"no matches"). The fix uses `grep -Fc` and explicit `[ "$(...)" -eq 0 ]`
which is correct. Worth keeping.

### ⚠️ Postmortem duplication vs PR #23

PR #23's postmortem is on `main` (200 lines). Ours is on this branch
(317 lines, not yet merged via PR #24). They cover the same root cause.
If both end up in the history there will be two accounts that drift.

**Action:** consolidate. Keep the longer one. Mark the shorter one as
superseded via a CHANGELOG note.

---

## 7. GitHub issues

The state of the issues we triaged earlier (this session):

| # | Title | Status | Comment posted? | Action |
|---|---|---|---|---|
| 1 | Duplicate zip members in output | open | yes | Still open; layout-validator now covers this. Could close. |
| 2 | Security review (out of scope) | open | no | Out of scope per "Sounds like we should do 2". Leave open. |
| 3 | (closed) | — | — | — |
| 8 | Patcher uses meson 1.x | open | yes | Still open; tracked separately. |
| 11 | (closed by PR #23? check) | — | — | — |
| 12 | Silent firmware-reject | closed by PR #23 | yes | Confirm. |
| 13 | Wrong appfs MD5 in firmwareInfo | closed by PR #23 | yes | Confirm. |
| 15 | (still open) | open | yes | Verify comment. |
| 16-22 | mixed | mixed | mixed | Re-validate each comment is still accurate post-merge of PR #23. |

**Action:** re-verify each comment we posted reflects current issue state.

---

## 8. Recommended changes before PR #24 is merged

1. **Fix the FwPkt/ doc framing** (the original Benro zip DOES have the
   prefix; we did not have to "add" it, we only had to preserve it).
2. **Add a new section to the postmortem** with the stock-Benro
   firmwareInfo inconsistency finding from §5 above.
3. **Decide on postmortem consolidation**: keep one, mark the other
   superseded.
4. **Fold the script changes** (`ec01ab2`) into PR #24 so PR #24 carries
   the whole branch's worth of work.
5. **Confirm and re-comment** on issues #1, #8, #11, #15 post-PR-23-merge.

## 9. What is solid

- `container/validate_fw_package.py` — well designed, stdlib only, fail-closed, catches real bugs.
- `container/verify_firmwareinfo.py` — byte-identical to main, fine.
- The shipped FwPkt.zip is structurally and content-wise correct (passes both validators, differs from stock only where we wanted it to).
- The CHANGELOG, patch.sh wiring, and SMB delivery convention are sound.

## 10. What is questionable

- The framing of `fwpkt-zip-layout-and-smb-delivery.md` (the original Benro zip already has the FwPkt/ prefix).
- Whether the "gimbal-cp loud-fail" fix would have caught the actual 2026-08-27 failure (no — the actual failure was a stale `firmwareInfo`).
- The postmortem duplication with PR #23.

## 11. What is wrong

- Nothing technically wrong in the shipped code. The validators pass; the
  shipped build is correct.
- The doc framing in `fwpkt-zip-layout-and-smb-delivery.md` misrepresents
  the original Benro zip layout. Correct this.
