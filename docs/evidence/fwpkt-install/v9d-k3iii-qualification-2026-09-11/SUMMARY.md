# v9d K-3 III on-Polaris qualification — 2026-09-11

Artifact `o-v9d-model-aware-focus` was installed with embedded libgphoto2
commit `90de508a5`. K-3 III serial 8093033 enumerated as `25fb:0189`; pgphoto
initialised successfully and reported camera state 1.

| Gate | Result | Evidence |
|---|---|---|
| Runtime provenance/processes | PASS | Exact embedded commit; polestar_app and Stage-2 pgphoto running; ports 22, 8080 and 9090 listening. |
| Live-view control | PASS | 291 start returned `state:1;ret:0`; 292 returned `state:1`. Operator confirmed live view worked. |
| Live-view data plane | PASS | One 12 s client received 512,661 bytes, six Content-Length parts and six complete JPEG SOI/EOI pairs. |
| Live-view stability | PASS | One continuous 120 s client received 3,871,480 bytes and 58 complete JPEG frames (~0.483 fps). All 24 five-second health samples retained the route and found ports 22 and 9090 open. |
| Live-view shutdown | PASS | 291 stop returned `state:0;ret:0`; 292 then returned `state:0`. |
| Focus protocol acknowledgement | PASS only as transport | Both bounded 311 requests returned `ret:0`; pgphoto received each once. |
| Physical focus movement | FAIL | Operator observed no focus movement. No model-aware dispatch/0x9017 line appeared in Clog, so the pgphoto 311 adapter acknowledgement is a false positive. |
| Shutter initiation | PARTIAL | Camera visibly/sort-of released and 264 first returned `state:1`. |
| Shutter completion | FAIL | 1.45 s later libgphoto2 returned `-110`: transfer candidate 1 from the preceding capture was still pending. polestar mapped this to `state:-1005` / Shot failed, then camera info recovered to state 1. |

The shutter failure is not caused by an impatient client timeout: the runtime
itself emits a terminal failure. Increasing UI wait time without resolving the
stale candidate would only delay presentation of the same result.

Tracking:

- patcher #37: capture candidate lifecycle and false terminal completion
- patcher #47: 311-to-libgphoto2 focus adapter mapping
- libgphoto2 #59: pgphoto acceptance gate explicitly remains unmet

Raw evidence files in this directory preserve preflight, control replies,
multipart streams and the relevant Clog/Mlog extracts. The binary stream files
are intentionally local evidence and are not required in the public commit.
