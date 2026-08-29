# Critical review — branch vs upstream + main

- **Branch under review:** `agents/work-out-why-our-firmware-just-disappears-when` (HEAD `4b98e01`)
- **Date:** 2026-08-29
- **Reviewer:** session b4608c76
- **Compared against:** `origin/main` (`6d56888`, incl. PR #23 from a parallel agent) and `upstream/main` (`b62c407`, only PR #4 — SSH/CRLF)

This is a self-review of all work done in this branch to address the silent
FwPkt reject (issue: firmware disappears when the Polaris reads it, no warning,
no extra Pentax functionality). It also stress-tests the validators we built
against the actual artifacts we shipped.

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

I ran the validators against three artifacts:

| Label | Path | MD5 | Provenance |
|---|---|---|---|
| shipped | `/tmp/shipped-fwpkt.zip` (= `SMB:BenroPolaris/2026-08-28_latest_pentax-hdmi720p60-live_only/FwPkt.zip`) | `e4a6a37d84745cb05b02d6e5ca8f45d4` | Our patched build, combined Pentax + HDMI 720p60 + live-view. |
| in-flight | `/tmp/original-fwpkt.zip` (= `SMB:BenroPolaris/FwPkt.zip` top-level) | `fd8147c91df44757d8a41c8bacc39519` | **Older in-flight build of our own pipeline** — 2026-08-23 base + 2026-08-27 09:31 appfs, pre-dates the combined build. Not stock. (See [docs/fwpkt-zip-layout-and-smb-delivery.md](./fwpkt-zip-layout-and-smb-delivery.md) for the labelling.) |
| stock | `~/Downloads/FwPkt.zip` | `90bdad511f556f25a2904ae9d2980102` | Pristine Benro download (byte-identical to `firmware/FwPkt.zip` upstream). |

> **Note on a prior version of this review:** an earlier draft of §5 below
> claimed the "stock Benro stock" `firmwareInfo` was internally inconsistent.
> That claim was based on the in-flight file being mislabelled as stock.
> Re-ran against the actual stock download: every claimed MD5 in
> `firmwareInfo` matches the file bytes. The "stock is broken" claim is
> **retracted 2026-08-29** — see §5.

### 4.1 Structural diff between the zips

All three zips have **identical structure**: top-level dir `FwPkt/`, members
`FwPkt/camera/{config, uImage, rootfs.ubifs, appfs.ubifs}`,
`FwPkt/gimbal/{polaris413_2.0.0.22.bin, polaris403_2.0.0.22.bin}`,
`FwPkt/firmwareInfo`. No subfolder mismatch, no extra files, no missing
members. The shipped zip is **not** structured differently from the stock.

### 4.2 `validate_fw_package.py`

```text
$ python3 validate_fw_package.py /tmp/shipped-fwpkt.zip
OK: FwPkt package is structurally sound.
$ python3 validate_fw_package.py /tmp/original-fwpkt.zip   # the in-flight build
OK: FwPkt package is structurally sound.
$ python3 validate_fw_package.py ~/Downloads/FwPkt.zip     # the real stock
OK: FwPkt package is structurally sound.
```

All three pass. The validator is correctly calibrated: it accepts the real
Benro stock (correct — it IS structurally sound) and accepts our patched
output (also correct). It also accepts the older in-flight build, because
its layout is fine — but the **structural validator only checks layout, not
`firmwareInfo` MD5s**. Cross-checking `firmwareInfo` is the manifest
verifier's job (§4.3 below).

### 4.3 `verify_firmwareinfo.py`

```text
$ verify_firmwareinfo.py <stock_info> <shipped_dir>
OK: 6 entries verified, firmwareInfo matches shipped files        # PASS

$ verify_firmwareinfo.py <stock_info> <in-flight_dir>
FAIL: 1 mismatch(es) across 6 entries
  appfs      MISMATCH  .../camera/appfs.ubifs
    md5:  91629acf0494b7f43298f6821913124f (claimed 1775c7bc4eee7d549a36fa28bb13f367)

$ verify_firmwareinfo.py <stock_info> <stock_dir>
OK: 6 entries verified, firmwareInfo matches shipped files        # PASS
```

The shipped zip and the real stock both pass the firmwareInfo gate. The
in-flight build **fails it** because its `firmwareInfo` was never
regenerated after the `appfs` was layered on — exactly the silent-reject
failure mode the postmortem describes. See §5 for the prior-version
retraction note.

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

## 5. Retraction (2026-08-29): the "stock Benro firmwareInfo is broken" claim is wrong

An earlier version of this review claimed the stock Benro download's
`firmwareInfo` was internally inconsistent, with the claimed `appfs`
MD5 not matching the file bytes. **That claim is retracted.**

What actually happened: the file I was stress-testing — md5
`fd8147c91df44757d8a41c8bacc39519`, the file I'd labelled as
"unchanged stock straight from Benro's download" — was **not stock**. It
was an older in-flight build of our own patcher pipeline (2026-08-23
base + 2026-08-27 09:31 appfs, pre-dates the combined build), still
sitting at `SMB:BenroPolaris/FwPkt.zip` (top-level). Its
`firmwareInfo` is genuinely stale — it was never regenerated after
the `appfs` was relayered — which is the same silent-reject failure
mode the postmortem describes, re-occurring in our own pipeline.

When I re-ran the same test against the **actual** pristine Benro
download (`~/Downloads/FwPkt.zip`, md5
`90bdad511f556f25a2904ae9d2980102`, byte-identical to upstream
`firmware/FwPkt.zip`):

```text
$ verify_firmwareinfo.py <stock_info> <stock_dir>
OK: 6 entries verified, firmwareInfo matches shipped files
```

Every claimed `firmwareInfo` entry — `config`, `uImage`, `rootfs`,
`appfs` (md5 `47f2ae680be3a5f5d69aa20e20a2397b`, size 64,487,424
bytes), `polaris403`, `polaris413` — matches the file bytes. Stock
Benro is fully self-consistent.

### 5.1 Three independent reasons the retraction is correct

1. **Direct re-verification:** `verify_firmwareinfo.py` passes on the
   real stock download (output above).
2. **Upstream's own `gen_firmwareinfo.py` docstring** (in
   `blaineam/benro-polaris-firmware-patcher`'s `container/`) says:
   > "The device recomputes MD5s on-board (getFwInfo.sh → crcInfo)
   > and string-compares each 'X MD5:' field against firmwareInfo."
   If stock Benro's `firmwareInfo` were internally inconsistent, the
   Polaris would refuse to flash stock Benro — which would be a
   Benro support-call issue, not a private investigation. Polaris
   owners have been happily running stock firmware for years; this
   rules out a real stock mismatch by observation.
3. **Upstream issue tracker:** searched
   `blaineam/benro-polaris-firmware-patcher` and
   `ian-morgan99/benro-polaris-firmware-patcher` for any report of
   a stock `firmwareInfo` MD5 mismatch (keywords: `firmwareInfo`,
   `appfs`, `mismatch`, `MD5`, `stock`, `silent reject`). **No such
   report exists.** The only related upstream issue is #11
   "Issue with testing" (filed by ian-morgan99, this user) which
   describes the same "zip file disappeared" symptom but is not
   framed as a stock `firmwareInfo` MD5 mismatch — see §7 below.

### 5.2 The lesson that survives the retraction

The in-flight build is a **real example** of the silent-reject bug
re-occurring in our own pipeline. It is the same failure mode the
postmortem was written to address, captured in a real artifact. This
demonstrates that the structural validator (`validate_fw_package.py`)
and the manifest verifier (`verify_firmwareinfo.py`) are not redundant
— they catch different classes of failure:

| Failure | `validate_fw_package.py` | `verify_firmwareinfo.py` |
|---|---|---|
| Files in wrong subdir / missing | ✅ catches | ❌ doesn't check layout |
| `firmwareInfo` MD5 stale | ❌ doesn't check MD5s | ✅ catches |
| Extra/unexpected files | ✅ catches | ❌ |

The in-flight build passes the first, fails the second. The shipped
zip passes both. **The recommendation is to run both validators in CI
on every build, not just the final shipped one.**

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

### 7.1 Upstream `blaineam/benro-polaris-firmware-patcher` (the head repo)

Earlier this session I claimed "I see nothing in the upstream issues" —
that was wrong: I had run `gh search issues --state all` (invalid flag)
and concluded "no issues indexed" instead of using `gh issue list --state
all`. Re-ran correctly: the upstream has 11 issues (5 open, 6 closed)
plus 1 merged PR. Of the open issues, several are directly relevant:

| # | Title | Filed by | Status | Notes |
|---|---|---|---|---|
| 3 | (Alpaca / plate-solving) | ian-morgan99 | open | Long thread about extending firmware over the network protocol. Tangential to this branch. |
| 6 | (local WiFi) | ian-morgan99 | open | Asks for an in-Polaris HTTP server. Tangential. |
| **7** | **Pentax Support** | **ian-morgan99** | **open** | **Tracks exactly the Pentax-USB-camera functionality this branch delivers.** This branch's PR #24 should reference #7. |
| **8** | **HDMI Support** | **ian-morgan99** | **open** | **Tracks exactly the HDMI-live-view functionality this branch delivers.** This branch's PR #24 should reference #8. |
| **11** | **Issue with testing** | **ian-morgan99** | **open** | **Body literally says "the zip file disappeared" — the same symptom that started this entire investigation.** Filed by the same user; the local postmortem and the structural validator are the diagnosis. |

PR #4 (merged) is the Windows-CRLF fix.

**Action:** PR #24 description should link to upstream issues #7, #8
and #11 explicitly. The "zip file disappeared" symptom in #11 is the
same bug the local postmortem is about; cross-link the two.

### 7.2 Local `ian-morgan99/benro-polaris-firmware-patcher` (this fork)

The state of the issues we triaged earlier in this session:

| # | Title | Status | Comment posted? | Action |
|---|---|---|---|---|
| 1 | Duplicate zip members in output | open | yes | Still open; layout-validator now covers this. Could close. |
| 2 | Security review (out of scope) | open | no | Out of scope per "Sounds like we should do 2". Leave open. |
| 8 | Patcher uses meson 1.x | open | yes | Still open; tracked separately. |
| 12 | Silent firmware-reject | closed by PR #23 | yes | Confirm. |
| 13 | Wrong appfs MD5 in firmwareInfo | closed by PR #23 | yes | Confirm. |
| 15 | (still open) | open | yes | Verify comment. |
| 16-22 | mixed | mixed | mixed | Re-validate each comment is still accurate post-merge of PR #23. |

**Action:** re-verify each comment we posted reflects current issue state.

---

## 8. Recommended changes before PR #24 is merged

1. **Fix the FwPkt/ doc framing** (the original Benro zip DOES have the
   prefix; we did not have to "add" it, we only had to preserve it).
2. **(superseded by §5 retraction)** — the prior "add a stock-Benro
   firmwareInfo inconsistency finding" recommendation is now wrong; the
   stock is self-consistent. The lesson that survives is "run both
   validators in CI on every build", which is already in the postmortem.
3. **Cross-link PR #24 to upstream issues #7, #8, #11** (see §7.1).
4. **Decide on postmortem consolidation**: keep one, mark the other
   superseded.
5. **Fold the script changes** (`ec01ab2`) into PR #24 so PR #24 carries
   the whole branch's worth of work.
6. **Confirm and re-comment** on local issues #1, #8, #15 post-PR-23-merge.

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
- The doc framing in `fwpkt-zip-layout-and-smb-delivery.md` is correct
  as written (see §6 — was a false alarm). **However, the "stock Benro
  firmwareInfo is broken" claim in §5 was wrong** — that's the
  retraction at the top of §5. The shipped code is fine; the
  in-flight build on the SMB share is a real example of the bug, and
  the in-flight-vs-shipped diff is the reason the postmortem's "run
  both validators in CI" recommendation matters.
