# Pentax stability evidence / issue map

Use #82 as the field-stability umbrella. Do not collapse focused defects into it.

| Issue | Evidence family / role |
|---|---|
| #36 | embedded preview/data-plane NoUpdateImage/session-state investigation |
| #55 | unbounded preview retry / radio-pressure family |
| #57 | stale pgphoto camera selection/port/session state across removal/body swap |
| #61 | multiple RAW / camera-busy lockup family |
| #66 | pgphoto restart churn family |
| #70 | separate physical USB hub flapping signature |
| #72 | broader Pentax regression/release qualification gate |
| #73 | shutter/recovery field symptom; cross-check libgphoto2 candidate issue |
| #77 | camera power/battery change and stale ownership/recovery behaviour |
| #78 | exposure did not terminate / app became unresponsive field scenario |
| #80 | K-3 III recurring Astro capture takes only first shot |
| #82 | external field-stability umbrella and causal coordination |

Also cross-reference `ian-morgan99/libgphoto2#73` for hardware-proven post-capture transfer-candidate contamination.

When new experiment evidence identifies a focused source defect, create/update that focused issue and link it back to #82. Do not leave a reproducible source defect only as a comment on the umbrella issue.
