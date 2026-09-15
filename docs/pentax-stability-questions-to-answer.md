# Questions the Pentax hardware campaign must answer

1. What is the first abnormal transition in each currently observed crash/lockup family?
2. Does a fixed timer/watchdog fire first around 100 seconds or another threshold?
3. What state/conditions does K-3 III expose during normal exposure, NR dark-frame, Pixel Shift and processing?
4. How many physical exposures occur vs how many candidates/files become visible for Pixel Shift JPEG and DNG+JPEG?
5. Can preview/config/focus/status requests safely occur in each capture phase?
6. Does host capture completion currently precede candidate reconciliation/true READY?
7. Which candidate must be acknowledged/transferred while preserving DNG on camera storage?
8. Does `session already open` occur in healthy histories as well as failed histories?
9. Does pgphoto accumulate memory/fds/threads/state across successful captures?
10. Can PTP become unhealthy while USB fingerprint remains stable?
11. Which failure families reproduce with direct libgphoto2 and which require embedded pgphoto/runtime?
12. After a genuine failure, what minimum deterministic teardown returns a provably fresh lifecycle?
13. Can all of the above pass before OpenPolaris is reintroduced, and what changes when OpenPolaris is then added?
