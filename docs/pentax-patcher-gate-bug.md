# Patcher Pentax Marker Gate — SIGPIPE / pipefail bug

**Discovered during:** Plan section 19 ("no overclaim") validation — cross-building
the canonical libgphoto2 master against the Benro Polaris patcher, then validating
that the cross-built driver passes the patcher's Pentax candidate-marker gate.

**Severity:** High (false-negative — gate fails even when the marker IS present)
**Scope:** `BenroPolarisPatcher/container/patch.sh:166-170`
**Affected:** every `--libgphoto2-source` invocation, every upstream libgphoto2
release where the marker string is present.

---

## The bug

`container/patch.sh:22` enables `set -euo pipefail`. Lines 166–168 then run:

```bash
if [ -e /libgphoto2-source-input ]; then
  strings "$NEW_PTP2" | grep -Fq "Pentax vendor mode enabled" ||
    die "local-source ptp2.so lacks the Pentax candidate marker"
  log "local-source Pentax candidate marker: present"
fi
```

`grep -F -q` exits 0 the instant it finds the match. `strings` is still writing
to the pipe, gets a SIGPIPE, exits with status 141. With `set -o pipefail`, the
pipeline's exit status is the rightmost non-zero (141), so the `|| die` clause
fires. The script aborts with "local-source ptp2.so lacks the Pentax candidate
marker" — even though the marker IS in the binary.

### Reproduction (host shell)

```bash
$ set -o pipefail
$ strings /work/out/ptp2.so | grep -Fq 'Pentax vendor mode enabled'
$ echo $?
141          # SIGPIPE — gate fires, die runs
```

Same file, same command, no pipefail:

```bash
$ set +o pipefail
$ strings /work/out/ptp2.so | grep -Fq 'Pentax vendor mode enabled'
$ echo $?
0
```

The marker string `Pentax vendor mode enabled, function flags 0x%08x` IS
present in the cross-built ptp2.so (verified with `strings` and
`grep -F` against a redirect), so this is a false-negative caused by the
shell pipeline, not by the build.

---

## Fix options (any one of these is sufficient)

A — disable pipefail around the gate:

```bash
if [ -e /libgphoto2-source-input ]; then
  ( set +o pipefail
    strings "$NEW_PTP2" | grep -Fq "Pentax vendor mode enabled" ) ||
      die "local-source ptp2.so lacks the Pentax candidate marker"
  log "local-source Pentax candidate marker: present"
fi
```

B — drop `-q` and redirect to `/dev/null` (grep still exits 0/1 on match/no-match,
but the kernel only signals SIGPIPE if the consumer closes early, which it
doesn't because we're consuming the full `strings` output):

```bash
if [ -e /libgphoto2-source-input ]; then
  strings "$NEW_PTP2" | grep -F "Pentax vendor mode enabled" >/dev/null ||
    die "local-source ptp2.so lacks the Pentax candidate marker"
  log "local-source Pentax candidate marker: present"
fi
```

C — temp file (no pipe at all):

```bash
if [ -e /libgphoto2-source-input ]; then
  strings "$NEW_PTP2" >"$W/ptp2.strings"
  grep -Fq "Pentax vendor mode enabled" "$W/ptp2.strings" ||
    die "local-source ptp2.so lacks the Pentax candidate marker"
  log "local-source Pentax candidate marker: present"
fi
```

---

## Why this matters for the consolidation

This bug blocks every cross-build that:
1. mounts `--libgphoto2-source PATH` (i.e. supplies a local libgphoto2 checkout),
2. and rebuilds ptp2.so from a source tree whose `library.c` contains the
   `Pentax vendor mode enabled, function flags 0x%08x` log line.

That is exactly the configuration the consolidation plan validates (the canonical
libgphoto2 master has the marker at `camlibs/ptp2/library.c:10844`). Without
fixing the gate, the consolidation cannot be reproduced end-to-end from the
patcher side.

The bug is independent of the consolidation — it has been latent in the patcher
since the Pentax gate was added. The Pentax v3 build run (cross-built inside
the patcher) likely hit this same failure mode, since the source it consumed
also contained the marker; the failure was attributed to "Pentax gate" rather
than "broken Pentax gate".

---

## Validation status of the consolidation

The cross-build of the canonical libgphoto2 master is otherwise complete and
reproducible:

- `camlibs/ptp2/ptp2.so` — 915,232 bytes, ARM EABI5, soft-float, stripped,
  glibc ceiling 2.24
- `iolibs/usb1/usb1.so` — 30,260 bytes, ARM EABI5
- `libgphoto2.so.6` — 133,508 bytes, ARM EABI5 (full mode)
- `libgphoto2_port.so.12` — 38,620 bytes, ARM EABI5 (full mode)
- `strings camlibs/ptp2/ptp2.so | grep -c "Pentax vendor mode"` = 5 (the
  marker is one of 156 Pentax-related strings preserved from the source)

The only thing standing between the consolidation and a clean patcher-driven
rebuild is this 1-line bug fix.

---

## Note on "no overclaim"

This finding reports the gate's actual behaviour. It does NOT recommend
weakening the gate (e.g. matching on a weaker pattern, removing the check
entirely, or substituting a different marker). The marker string
`"Pentax vendor mode enabled"` is the correct invariant — it is a debug
log line that only exists in Pentax-aware builds, and it is the only
cross-version-stable signal that the local source's Pentax work landed.
The fix preserves the gate's intent.

---

## Resolution (committed in `6d56888` follow-up)

A fourth option (D) was chosen because it adds the smallest possible
behavioural delta: keep the existing pipeline shape, swap `-q` for `-c`,
and route the result through a string compare so the script's exit
behaviour is the natural 0/1 of the inner test.

```bash
if [ -e /libgphoto2-source-input ]; then
  # 'strings | grep -Fq' under 'set -euo pipefail' is a SIGPIPE footgun.
  # Use 'grep -Fc' so grep drains the pipe to EOF (no SIGPIPE), then compare
  # the count to 0 to preserve the gate's "match ⇒ continue" semantics.
  if [ "$(strings "$NEW_PTP2" | grep -Fc 'Pentax vendor mode enabled')" = 0 ]; then
    die "local-source ptp2.so lacks the Pentax candidate marker"
  fi
  log "local-source Pentax candidate marker: present"
fi
```

### Why D over A/B/C

* **A** (`( set +o pipefail; ... )`) disables pipefail across a 1-line scope
  which is harder to audit than the inner `grep -c` swap.
* **B** (`| grep -F "..." >/dev/null`) still has grep exit early on match;
  strings gets SIGPIPE on the *next* write, but only if the next write
  happens before strings exits. In practice the I/O ordering makes this
  rarely reproduce, so it is still racy. D removes the race entirely.
* **C** (temp file) adds a filesystem dependency for no semantic gain.
* **D** keeps the pipeline, makes grep consume its full input (so
  strings always exits 0 with no SIGPIPE), and turns grep's exit into
  a captured integer that the if-test consumes naturally. The
  command-substitution boundary means a `grep -c` exit code of 1
  ("no match") does not trigger `set -e` for the substitution itself.

### Validation

Re-running the build with this fix in place:

```
[log] local-source Pentax candidate marker: present
```

(versus the prior failure: `[abort] local-source ptp2.so lacks the Pentax
candidate marker` even though `strings "$NEW_PTP2" | grep -F "Pentax
vendor mode enabled" | wc -l` confirmed the marker is present 1 time in
the binary.)
