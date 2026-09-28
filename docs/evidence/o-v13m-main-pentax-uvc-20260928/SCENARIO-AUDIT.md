# One-off capture scenario and output-format audit

Date: 2026-09-28  
Candidate: `o-v13m-main-pentax-uvc-20260928`  
Source: libgphoto2 `caa3ca8343ba836928587f66ccbbce8dc9c1e04f` (`main`); patcher build input `5f404ee8022337dda9791f88b3fb90fc67e805d3` (`main`).

## Finding

This package is build- and offline-gate-valid. The available evidence does not
show that it is ready for all requested camera modes and output formats. It
must be treated as an uninstalled candidate, not a generally qualified
firmware. The strongest recent physical result is on an earlier package and
does not transfer automatically to this different package.

| Workflow | Format | Evidence found | Assessment for v13m |
|---|---|---|---|
| Normal still | RAW+JPEG | v13g K-3 III canary and two-shot passed, with both same-stem DNG/JPEG files; v13j direct two-shot passed. v13m includes later source and has not been installed. | Earlier versions PASS; v13m NOT TESTED |
| Normal still | RAW only | v13n historical single-shot passed, but its second run lost camera state; gate-oracle fixture exists. | No current-candidate repeated hardware qualification |
| Normal still | JPEG only | No evidence of a current-candidate hardware matrix; older mode-matrix requires three captures. | NOT TESTED |
| Astro | RAW+JPEG | v13g bounded Preview suspend/capture/restore passed once; v13j Benro Connect Astro later crashed during sequence. | Known unstable evidence on v13j; v13m NOT TESTED |
| Astro | RAW only | o-v9p passed five Astro-equivalent DNG captures, but that was a much earlier package. v13c passed an Astro-equivalent sequence, with explicitly limited native-Astro claims. | Historical workload PASS; v13m/native workflow NOT TESTED |
| Astro | JPEG / RAW+JPEG variants | No per-format native Astro matrix found. | NOT TESTED |
| Panorama / Pro Panorama | All formats | Historical v10 lineage reportedly passed some panorama sequence; later divergence record lists panorama and related modes as failing/unqualified. No current candidate result. | NOT TESTED; contradictory historical evidence means no qualification |
| Pixel Shift | RAW+JPEG | v12h was incomplete (one JPEG and a pending RAW candidate); v12m retrieved both but crashed on second-file ownership. No later physical Pixel Shift PASS found. | NOT QUALIFIED; highest-risk output-obligation gap |
| Pixel Shift | RAW only / JPEG only | No evidence found establishing these combinations or support on the tested body. | NOT TESTED |

## Deterministic coverage

The release gate has 13 patcher/container checks and 24 Python checks. It
includes scenario routing and explicit expected-file-count behavior, but those
tests validate the caller/test contract; they do not emulate Pentax USB/PTP or
prove image-format behavior on hardware. libgphoto2 has focused deterministic
Pentax utility, candidate reconciliation, publication ownership and aperture
alias tests. Those do not simulate a complete camera session for each mode.
The Astro multi-shot test is explicitly a workload simulation, not native Astro
or tracking qualification. No panorama/Pixel Shift hardware semantics are
proven by the offline package gate.

## Evidence-based disposition

Do not call v13m ready for all requested scenarios. Keep it as a reviewable
candidate. Before claiming K-3 III coverage, install through the sanctioned
flow and collect at least: normal JPEG x3, RAW x3, RAW+JPEG x2, Astro sequence
with observed exposure/format and resume to normal capture, each panorama mode
that issues still captures (including Pro Panorama), and Pixel Shift RAW+JPEG
with a complete camera-declared output set followed by another safe capture.
For each run, record the installed hashes, mode/config readback, physical
actuations, lifecycle, candidate handles, output transfers/publication, next
shutter admission, USB identity and process/session continuity. Stop after the
first failure; do not send another shutter as an implicit retry.

K-1 II and Canon R5 Mark II are separate regressions and cannot inherit K-3 III
results. If output formats or Pixel Shift settings are unsupported by the
specific body, record that as unsupported after verifying capability/config
readback rather than silently counting it as PASS.
