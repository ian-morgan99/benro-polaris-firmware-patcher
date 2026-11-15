# Camera issue disposition at v109 — 2026-11-15

Snapshot: 83 driver, 171 patcher, 53 OpenPolaris and 20 harness open issues:
327 total, including non-camera work. All identities are in the index; full
bodies/update timestamps are preserved privately. This is an acceptance audit,
not a claim that all symptoms were reproduced on v109. Earlier detailed review
is in WBS 8.16–8.17. Historical v104–v106/pre-#304 findings require current
same-boundary reproduction before code changes. No new issues or branches.

| Repository / issues | Disposition and required evidence |
|---|---|
| Driver #165 | daef5b7be routes held-Bulb through shared admission; executable regression included, active-transfer refusals retained. Review/physical confirmation still pending, not full Bulb closure. |
| Driver #164 | 1bf8ba51a bounds source-known UINT16 colour temperature to 2500–10000, step 10; unknown scalar domains withheld. Direct-host application/restoration still required. |
| Driver #143, #119, #141; patcher #235, #313, #314, #325, #327, #328 | Source gates/getter-error propagation included; current -2110 writes and K-3 III failed restoration remain unresolved. Attempted values are not camera truth. Reproduce first failing direct PTP operation before assigning library ownership. |
| Driver #153, #106, #114, #95, #132; patcher #251, #163, #148, #230, #243, #242, #241, #239, #317 | True Bulb duration, early/deferred cancellation, physical closure, NR, M/B transitions and next-shot recovery need supervised hardware qualification. Diagnostics/offline tests do not close them. |
| Driver #142, #115, #73, #74, #60, #55, #54; patcher #145, #192, #191 | Two ordinary v108 captures passed; dual-output publication/duplicate-event ownership remains open. Do not suppress events or delete RAW as a proposed workaround. |
| Driver #138, #133, #83, #33; patcher #146, #147, #270, #319, #252, #238 | Normal-disconnect source fix included; reconnect, preview ownership and USB state need fresh-session tests. Current K-3 III disappearance is a stop condition. |
| Driver #161; patcher #327, #314, #316, #209 | Hyphen parser/source gates exist. List validity, seconds-versus-Tv, application and restoration are different acceptance gates; do not rename fields speculatively. |
| Driver #162, #151, #150, #135, #134, #118, #117, #82, #76, #68, #59, #58, #57, #56, #8; patcher #320, #278, #234, #108, #81, #76, #75, #47 | Source/model/UI gates plus physical AF effect, focus direction, magnitude, zoom/restoration remain. ACK and preview are not proof of lens movement. |
| Driver #77, #75, #67, #66, #52, #51, #130; patcher #323, #326, #219, #109, #85 | Require source-derived domains, real consumer arrays and complete round trips. No artificial array padding or guessed model support. |
| Driver #120–#129, #154–#160; patcher #229, #237, #236, #179, #35 | Per-model physical qualification remains. MSC 0182 is not PTP 0183; generic-only K-3 II/K-01/Optio is not IT2 support. Monochrome/645Z/KF table rows are not physical evidence. |
| Patcher #187, #81, #219; OpenPolaris #62, #63, #56, #101, #100, #99, #96, #94, #90, #80, #61, #60 | App acceptance remains open: real mode-correct arrays, final file event, same-SHA library/Polaris/client differential. First ACK is not capture completion. |
| Patcher #218 | -108 terminal failure and archive-derived totals fixed/tested in bb47558; stock negative-duration logging remains, so issue stays open. |
| Patcher #216, #214, #203, #204, #227; PR #346 | Main/pin/version/isolation/publication fixes delivered. Coordinators stay open for installed/physical evidence. |
| Patcher #340; harness #15, #16, #17, #18, #27 | Exact candidate loader/265 relocations/100k ARM instructions pass; broader runtime/capture modeling remains. No fake PTP/shutter success. |
| Patcher #331 | Actual Astro conformance passes; firmware LGPL source/licences also included in publication. No new redistribution grant inferred for proprietary research. |
| Patcher #345, #344, #343, #342, #321, #288, #271, #329, #309; OpenPolaris #103 | Accepted Astro main changes consumed and offline-tested. On-device corpus/performance/pointing integration remains with Astro owner. |
| Driver #85, #86; patcher #162, #159, #158, #151, #137, #135 | UVC/vendor astronomy cameras are separate work, not Pentax/PTP qualification. |
| Remaining indexed issues | Retained open under their existing acceptance criteria; administrative, security, stock-preservation, install, upstream and research work is not automatically fixed by a new camera candidate. |

The complete inventory is not a complete new physical review of 327 issues.
Only the evidence above supports specific implementation findings; no omitted
or stale issue should be read as closed.
