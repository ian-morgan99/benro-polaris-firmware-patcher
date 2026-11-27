# #369 / #389 — source-to-artifact implementation matrix

Date: 2026-11-27. Responds to the maintainer direction of 2026-11-27 on #369 (required
action 1) and #389. Every row below was re-derived today from the artifacts named, not
from a prior comment in either thread. Where a claim from #389 is wrong it says so
explicitly and gives the correct statement.

Scope discipline: this matrix establishes **what is implemented, what is packaged, and
what is missing**. It proposes no fix and claims no measurement that was not taken.

---

## 0. What the TA's comment got right (verified, not disputed)

Each of these was checked against the exact blob/commit named in the comment. All are
correct as written.

| TA claim | Verification | Result |
|---|---|---|
| `container/stage2_loader.c` blob `fe322f0962724dc8d0e5853e382a5638636aff01`, lines 1675–1755 | `git rev-parse origin/main:container/stage2_loader.c` → `fe322f0962724dc8d0e5853e382a5638636aff01`; line 1675 is `stage2_shim_gp_camera_get_single_config` | **Correct for `main` — but see the note below: that is not the blob deployed in v118** |
| That shim "resolves and calls the real single-config API on every invocation"; special handling = choice validation + gated shutter fallback, **not** a shared conditions refresh | Line 1690 calls `g_real_gp_camera_get_single_config(...)` unconditionally; success path → `stage2_reject_empty_choice_widget()`; failure path gated by `STAGE2_SHUTTER_FALLBACK` (default OFF) and restricted to `name=="shutterspeed"` | **Correct** |
| libgphoto2 `camlibs/ptp2/config.c` blob `b533f771d7f9ab4d86f121cad1c0a39689d15ddf` | `git rev-parse f48a05e0:camlibs/ptp2/config.c` → `b533f771…` — i.e. this blob **is** the source of the driver packaged in v118 (provenance `git_commit=f48a05e0`) | **Correct, and it is the shipped tree** |
| config.c 15831 / 15893 filter by leaf name in `MODE_SINGLE_GET` | Both lines are `if ((mode == MODE_SINGLE_GET) && strcmp (cursub->name, confname)) continue;` | **Correct** |
| config.c 16182–16198 route full and single calls to `_get_config` | `camera_get_config`, `camera_list_config`, `camera_get_single_config` all call `_get_config`; single passes `confname` | **Correct** |
| config.c 9479 onward calls `ptp_pentax_get_all_conditions` and parses ISO/aperture/EV/mode | `_get_Pentax_Conditions` at 9480; the opcode call is at 9492 | **Correct** |
| "A successful single lookup is not inherently a full-tree rebuild" | See §3. Confirmed by control flow, and independently by the Nov-24 controlled A/B already in #369 | **Correct** |
| Commit `4f38e814` says no fix proposed and defect A remains open | Its FINDINGS.md contains "**No fix proposed.**"; the message states defect A "does not originate in v118" but never closes it | **Correct** |
| 170/375 CONFIG-vs-CONFIG refusals, non-controlled version samples | Commit message: "170 of 375 are that function refusing itself"; and it explicitly declines to attribute the era shift to firmware ("operator activity is a live confound") | **Correct** |

No factual error was found in the maintainer comment. The disagreement below is about
**scope of what was delivered**, not about their reading.

### One source-vs-artifact mismatch worth flagging, since action 1 asks for exactly this

The comment cites loader blob `fe322f09…`, which is `origin/main` **today**. The deployed v118
loader was built from patcher commit `858edfd87`, whose `container/stage2_loader.c` blob is
`ad73ceaf290975e0f721412170e1a47aa00571dd` — a different blob, 2396 lines versus main's 2459.

Consequence: **the cited line numbers do not point at the deployed artifact.** In `858edfd87`
the shim is at line **1644**, not 1675; the slot installation is at **2368**, not 2430. Anyone
opening the `main` permalink to check the shipped behaviour will read a file that is 63 lines
longer than what is on the appliance.

The *substance* of the claim survives unchanged, which I verified rather than assumed: in the
deployed blob the shim body is byte-for-byte the same logic — resolve the real core fn, call it
unconditionally (`int ret = g_real_gp_camera_get_single_config(camera, name, widget_out, context);`),
validate choices on success, gated shutter fallback on failure. And `grep GetAllConditions\|cachetime\|snapshot`
on the **deployed** blob is also zero hits, so "no shared conditions refresh" holds for what is
actually running, not just for `main`.

The 66 lines `main` adds over the deployed loader are unrelated to reads: a
`STAGE2_CAPTURE_STOREFULL_REMAP` gate and capture-path comments. So no read-path behaviour
differs between `main` and deployment — but the line-number drift is real and is recorded so
future citations name the blob that is on the device.

---

## 1. Shipped artifact chain (v118, currently installed on o-v15r)

Device `192.168.0.1`, read live on 2026-11-27. `/app/sd/polaris-astro/VERSION`:
`build_id=astro-v118-stage2-gate-wedge-fix-20261126`, `firmware_version=6.0.0.54.118`.

| Artifact on device | sha256 | Built from |
|---|---|---|
| `/app/lib/stage2/pgphoto.stage2ondisk` | (manifest) | **vendor binary, never patched by us**; md5 `79d4454f` identical for v115/v117/v118 |
| `/app/lib/stage2/libpolaris_stage2.so` | `ec18c1648b8253d417f53589cb34b3807ec262ee7877e9587bd2d6671e63a9cb` | patcher `858edfd87be3681d26cbfee4810dff2c25c8696f`, source `container/stage2_loader.c` blob **`ad73ceaf290975e0f721412170e1a47aa00571dd`** |
| `/app/lib/stage2/libgphoto2.so.6` | `cefa7b399b8c25ad8801a74bad6db3124f15187190528266b4b36116f13d2b62` (199 356 B) | libgphoto2 `f48a05e08b54d6d433a556c2df512987a51ce742` |
| `/app/lib/stage2/libgphoto2/2.5.34/ptp2.so` | (manifest) | same commit; **this is where the Pentax batch code actually lives** |
| `/app/lib/libgphoto2.so.6.1.0` | `8b461f8ac31f7df156fd77bd973a7562ff708b6c5da1203a0eb9eaedd965feed` (409 296 B) | **stock vendor** copy, untouched |

`/app/openpolaris-libgphoto2-provenance.txt` on the device:
```
actual_version=2.5.34
git_commit=f48a05e08b54d6d433a556c2df512987a51ce742
patcher_commit=858edfd87be3681d26cbfee4810dff2c25c8696f
selected_camlibs=ptp2,pentax
build_id=astro-v118-stage2-gate-wedge-fix-20261126
```

**Correction to a mistake I made while building this matrix.** `ptp_pentax_get_all_conditions`
is compiled into the **camlib plugin** `ptp2.so`, not into the core `libgphoto2.so.6`. My first
check grepped the two core `.so` files, found zero matches, and briefly looked like "the batch
opcode is not shipped". It is shipped — `strings -a ptp2.so` shows `GetAllConditions`, plus the
admission strings `conditions-unreadable`, `unsafe-activity`, `transfer-candidate-available`.
Anyone repeating this check must grep the camlib, not the core. Recorded here so nobody else
draws the wrong conclusion from a zero-hit grep.

---

## 2. The runtime call path for a settings read (the "consumer boundary")

```
pgphoto  deal_camera_control_handler / updateCameraViewFinder   [vendor binary, unpatched]
   │  indirect call through a slot in the exe's own .bss  (ldr pc,[r12])
   ▼
libpolaris_stage2.so   stage2_shim_gp_camera_get_single_config      ← THE CONSUMER BOUNDARY
   │  pass-through, dlsym'd real core fn                            (loader.c:1675)
   ▼
libgphoto2.so.6 (our build)   gp_camera_get_single_config → camera_get_single_config
   ▼
ptp2.so (our build)           _get_config(mode=MODE_SINGLE_GET, confname=<leaf>)
                              ├─ leaf filter 15831/15893: non-matching props `continue`
                              ├─ per matching prop: ptp_generic_getdevicepropdesc (cached, TTL)
                              └─ Pentax paths: ptp_pentax_get_all_conditions (0x900f)
```

Key structural facts, both of which the TA's comment is right about and which constrain
any fix:

1. **pgphoto is never patched.** Its call reaches us only through the slot trampoline. So the
   loader shim is the *only* place we can change read behaviour for reads pgphoto initiates.
   A change inside `config.c` changes what a single read costs; it does not change how many
   reads pgphoto makes.
2. **The loader has no conditions cache.** `grep -n "GetAllConditions\|get_all_conditions\|cachetime\|snapshot" container/stage2_loader.c` → **zero hits**. The batch opcode is
   reachable from the driver, but nothing at the consumer boundary uses it to serve reads.

---

## 3. What #389's title asserts, and what is actually true

**#389 title: "libgphoto2 rebuilds the full widget tree on every get_config — 7.85s / ~62 PTP
ops per single-widget read". This is wrong and must be corrected in the issue body.**

Control flow in `_get_config` (config.c blob `b533f771…`, the shipped v118 tree):

- `mode = MODE_SINGLE_GET` whenever `confname != NULL` (line 15746).
- Every property loop is guarded by `if ((mode == MODE_SINGLE_GET) && strcmp(cursub->name, confname)) continue;`
  at **15831, 15893, 15929, 15960** — non-matching properties are skipped *before* any PTP call.
- On a match it returns early: `if (mode == MODE_SINGLE_GET) { *outwidget = widget; … return GP_OK; }` (16166).
- If nothing matched: `return GP_ERROR_BAD_PARAMETERS` (16173). **There is no internal retry and
  no internal full-tree rebuild.** A failed single get fails; it does not escalate.

So a *successful* leaf read cannot rebuild the tree — the leaf filter prevents the fetch, and
the early return prevents the walk. The 250–251-op / ~28 s figure belongs to **section-qualified
keys** (`/main/imgsettings/iso`), which fail the leaf `strcmp`, return `GP_ERROR_BAD_PARAMETERS`,
and are then retried by the *caller* through a path that walks everything. That is caller-side
escalation on a failed lookup, not driver-side rebuild on every read.

### Retracted numbers — do not reuse any of these

From #389's own comment history:

| Figure | Status | Why |
|---|---|---|
| 7.85 s / ~62 ops per single `--get-config` (issue body + title) | **Retracted** | Mis-parsed debug log; conflates a section-qualified failed lookup with a leaf read |
| "the widget tree is rebuilt per requested widget" | **Retracted** | Not supported by control flow (§3) or by the Nov-24 controlled A/B |
| 2.70 s / 13 ops, 0.02 s, 48.1 s | **Discard** | Taken while the camera was timing out; ops never completed and were never counted |
| `PTP_OC 0x9001` = 1.534 s vendor-mode enable latency | **Not established** | Same degraded window |
| scaling caused by `ptp_pentax_get_device_prop_desc_raw`/`_raw` bypassing cache | **Retracted** | That raw call is a *fallback* on generic-get failure; the trace shows the generic path succeeding |

### What survives, and is consistent with #369's controlled A/B

The Nov-24 four-arm comparison (same body, same port, same driver prefix, isolated 2 s TTL,
two passes each) is the authoritative measurement and contradicts #389's framing:

| Path | Seconds | USB requests/pass | Sessions | Direct lookup failures |
|---|---|---|---|---|
| Direct C single-widget API, one session | 2.325 / 2.262 | 16 / 16 | 1 / 1 | 0 / 0 |
| Validator helper, **one** CLI call, four leaf keys | 2.309 / 2.296 | 16 / 16 | 1 / 1 | 0 / 0 |
| Validator helper, **four** CLI calls, leaf keys | 8.563 / 8.505 | 52 / 52 | 4 / 4 | 0 / 0 |
| Shape-test convention, four CLI calls, **section-qualified** keys | 28.035 / 28.209 | 250 / 251 | 4 / 4 | 4 / 4 |

Read correctly, this separates the cost buckets the TA asked to be separated:

| Bucket | Evidence | Cost |
|---|---|---|
| Session startup | 1 session vs 4 sessions for the same 4 reads: 2.3 s → 8.5 s | **~6.2 s of the 8.5 s is session churn**, not reads |
| Successful leaf read, warm session | 4 reads / 1 session = 16 ops | ~0.57 s per read, marginal cost small |
| Failed lookup → caller-side full walk | section-qualified arm: 250–251 ops, 4/4 failures | **~28 s — the dominant cost, and it is a key-format bug in the caller, not a driver rebuild** |
| Descriptor TTL expiry mid-walk | `cachetime` default 2 s (`library.c:12086`); check `timestamp + cachetime > now` (`ptp.c:4901`); one walk spans ~7.95 s so entries expire during it | Real mechanism, **but only observable on the full-walk arm**; not established for leaf reads |
| Admission queue time | 170/375 CONFIG-vs-CONFIG from `deal_camera_control_handler` (commit `4f38e814`) | pgphoto-side serialisation; separate from all of the above |

The one thing I will **not** claim: that TTL expiry explains every refetch. Gaps of +1.409 s
and +1.251 s fall *inside* the 2 s window, so something else resets entries (`ptp.c:3744`,
`5032`, `6111` set `timestamp = 0`). Which one fires is **not determined**. I am not guessing
a third time on this issue.

---

## 4. Implementation status per required action

| # | TA requirement | Status | Evidence |
|---|---|---|---|
| 1 | Source-to-artifact matrix | **Delivered here** | §1–§3, all hashes re-read from device today |
| 2 | Reconcile #389 with #369; stop reusing discredited numbers | **Delivered**; #389 body/title still carry the retracted claim → corrected in #389 comment | §3 |
| 3a | Resolve capabilities/choices once per session generation + mode transition | **NOT IMPLEMENTED** | No cache at the consumer boundary (§2, zero grep hits). A `gp_camera_init` shim already exists (`loader.c:2376`) and a session-generation concept already exists (`native_gate.generation`, #127) — the invalidation hook is present, nothing consumes it for reads |
| 3b | Avoid redundant optional-property full-tree fallback where proven safe | **BLOCKED, not skipped** | The expensive arm is *section-qualified keys* issued by pgphoto/caller code we do not patch (§3). "Proven safe" requires knowing which caller issues them and at what frequency on the appliance; the v115 binary analysis names `_find_widget_by_name` (0xf2710) → full config (0xf2754) as a candidate but its runtime frequency on Polaris was never measured |
| 3c | One fresh `GetAllConditions` snapshot per logical refresh for supported current values | **NOT IMPLEMENTED** | Opcode shipped in `ptp2.so`; no consumer at the loader boundary. Also cannot be done blindly: which leaf names map to conditions offsets is model-dependent and must be enumerated per field, not assumed |
| 3d | Coalesce duplicate pending read requests | **NOT IMPLEMENTED** | No request coalescing anywhere in `stage2_loader.c` |
| 4 | Regression tests for transaction counts / freshness / invalidation | **NOT IMPLEMENTED** | Nothing today asserts PTP transaction counts. `container/test_pentax_capture_wedge_offline.sh` proves the awk-extract-and-compile pattern works against the fork, so the harness pattern exists — but a transaction-count test needs a device or a PTP fixture, neither of which exists yet |
| 5 | Deliver implementation + tests, not another research note | **Not met by this document** | Stated plainly below |

### The honest disposition on action 3/5

This matrix is documentation, and the TA explicitly said documentation is not progress. I'm
not going to present it as if it were. The real state:

- **The gap is at the loader shim**, which is ours, is packaged, and is patchable. That is the
  correct place for 3a/3c/3d and it does **not** require touching pgphoto or the driver ABI.
- **What blocks shipping it:** a conditions-snapshot cache must map leaf names → conditions
  offsets correctly per model, and serving a wrong value from a stale snapshot is strictly
  worse than a slow read — it is the #316 class ("slider offers values the body rejects"),
  made permanent. Pentax enums are mode-dependent (Bulb shutter list has no fractional values),
  so any cache must be keyed or invalidated on mode change, and live *values* must never be
  served from a descriptor cache at all. Getting that wrong on a shipped driver is how #316
  happened.
- **Therefore the first shippable increment** is not a cache. It is a transaction-counting
  harness that measures the current shipped path, so a cache can be proven to reduce ops and
  proven fresh-after-mode-change before it ships. Building that offline is possible; validating
  it needs a body.

I am not deploying anything on host-only results, and no driver change has been made.

---

## 5. What can be completed offline vs what needs hardware

| Work | Offline? | Blocker if not |
|---|---|---|
| This matrix, bound to device-read hashes | **Done** | — |
| Correct #389 title/body (retracted numbers still published) | **Done today** | — |
| PTP transaction-count harness (extract-and-compile pattern, like the wedge test) | Yes | Needs a PTP fixture or device for the count assertions; without either it must SKIP (77), not PASS |
| Conditions-snapshot cache in the loader shim | Code offline | **Cannot be validated offline.** Serving stale/mode-wrong values is a correctness regression worse than the latency it fixes |
| Leaf-name → conditions-offset map per model | No | Needs each body to enumerate what `0x900f` actually returns vs what each leaf reports |
| Frequency of the section-qualified failed-lookup path on the appliance | No | Needs Clog with the read path instrumented on o-v15r; K-3 III currently not attached (cable), K-1 II hub path clean but uninstrumented for this |
| Thermal / idle-battery comparison (K-3 III "heats after recognition") | No | Hardware. Not causal evidence today; stop if unusually hot |

---

## 6. Direct answers to the TA's framing

**"Do not claim absence globally from a single source file."** Accepted, and this is why §1
greps the camlib. My earlier "batch opcode not shipped" reading was exactly that error — I
grepped the core `.so` instead of `ptp2.so`. Corrected in §1 with the strings evidence.

**"A host validator optimisation is not an appliance optimisation."** Agreed, and nothing here
claims otherwise. The Nov-24 four-arm A/B was run on a PC against a research-feature driver
prefix; it establishes mechanism and relative cost, not appliance latency. Appliance numbers
for the shipped v118 path have never been captured for this question and are listed as
hardware-blocked in §5.

**"No reopening of settled questions without concrete new contrary evidence."** Nothing in §3
reopens a settled question. It does the opposite: it retires #389's title claim, which is the
one still-unretracted wrong statement in either thread, and points at the Nov-24 controlled A/B
as the authoritative measurement.

**Where I disagree with the comment, once, briefly:** "still being presented as a new finding on
27 November". The 27 Nov commit `4f38e814` is not a re-presentation of the parameter-read
finding; it answers a different question (defect A — *who holds the camera*, resolved to
`deal_camera_control_handler`, gpManager.c:2832) and explicitly proposes no fix. That said, the
underlying complaint stands: #369 was opened 18 Nov, the mechanism was understood by 24 Nov,
and no code has shipped since. The correct response to that is an increment, not another
comment — which is why §4 states status per item rather than re-narrating history.
