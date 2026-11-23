# K-1 II active-view policy comparison

The default fails to preserve the continuous-view cadence demonstrated by the body. Replaying the 276 measured direct-USB request start times and call durations through the v115 Stage-2 preview shim admitted six real fetches and returned camera-busy 270 times. Changing only the minimum interval to zero admitted 276 and returned busy zero times. The first real fetch took 1418 ms, so it qualified for the fast branch. Even that branch caps new frames at one every two seconds. This is a software-imposed ceiling.

The TSV contains rounded milliseconds (request start relative to the run, observed fetch duration). Replay uses the existing fake monotonic clock and camera callback; neither a camera nor a network is accessed. Both arms hold call arrivals and success results fixed. A mounted camera could respond differently after a longer gap. These counts are not a prediction of Android frame count, Wi-Fi capacity or safe sustained throughput.

Run from the Patcher repo root with this directory as D:

    cc -std=gnu11 -Icontainer -Icontainer/testdata "$D/replay.c" container/stage2_policy.c -ldl -o /tmp/k1ii-preview-replay
    /tmp/k1ii-preview-replay < "$D/governor-input.tsv"
    /tmp/k1ii-preview-replay 0 < "$D/governor-input.tsv"

Recommendation: reject the 2/8-second policy as the target for healthy active viewing. Qualify a separate demand-driven active mode, allowing one fetch in flight and dropping outdated frames when a consumer falls behind. Keep idle pacing, setter priority, and transport-failure recovery separately testable. Do not ship the zero-interval replay control as the replacement. Compare matched runs with one viewer, the same scene and a verified shutter round trip. Count fresh completed JPEGs at 8080, maximum and p95 frame gaps, setter admission and publication time, queue growth, radio errors and SSH reachability. Only promote a tested rate that improves fresh display while keeping control and connectivity reliable.
