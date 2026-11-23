# K-1 II direct USB descriptor-cache A/B, 23 November 2026

After the earlier busy refusal, the camera enumerated at 001,014 and independently reported shutter 00:01. Tested driver 0f2f34e00040, Pentax capture option enabled. Each row is a fresh gphoto2 session. The ten-widget path list was copied from the prior ten-widget trace. The single-widget case reads ISO. Isolated XDG settings directories selected the cache TTL. Each driver trace confirms the selected TTL. All requested widgets returned, with no property writes.

| TTL (s) | Widgets | Wall time (s) | PTP requests | Descriptor reads | Value reads | GetAllConditions |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 1 | 8.262 | 63 | 30 | 18 | 5 |
| 30 | 1 | 6.624 | 51 | 18 | 18 | 5 |
| 2 | 10 | 58.552 | 500 | 278 | 171 | 41 |
| 30 | 10 | 32.043 | 296 | 74 | 171 | 41 |
| 30 | 10 | 30.338 | 294 | 72 | 171 | 41 |
| 2 | 10 | 57.321 | 492 | 270 | 171 | 41 |

The longer TTL cut roughly 200 descriptor reads per ten-widget walk and about 26–28 seconds. All four ten-widget sessions still made 222 requests other than descriptor reads. Inspect repeated widget-tree construction and uncached reads next. Preserve fresh condition values, writability and mode-specific choices in any optimization. A 30-second global TTL was an experimental control only. The cache compares whole-second time(NULL) timestamps with strict expiry, so a 1.251-second interval can cross two second boundaries; relative time alone cannot establish invalidation. Local raw evidence: out/k1ii-cache-ab-iRi0Ca.
## Follow-up: ten K-1 II controls in 2.89–3.04 seconds

The absolute-path benchmark made ten single-config calls that failed with -2, then returned the requested widgets through the full-tree fallback. The earlier cache experiment measured the cost of that fallback. Repeated the same ten reads with their unique leaf names on USB 001,014, in one fresh gphoto2 session per run, on the same v115 driver and 2-second TTL. All ten returned in 2.887 and 3.044 seconds including startup and teardown, using 20 PTP requests and six descriptor reads per run. The absolute-path runs took 57.321 and 58.552 seconds with 492 and 500 requests. Labels, types, writability and choices matched across methods; all current values matched except the advancing camera clock. Single ISO took 2.223 seconds and 13 requests by leaf. No setting was written or needed restoration. Use leaf names for these tested controls. Do not strip arbitrary paths without checking uniqueness. For appliance latency, verify the names actually passed by pgphoto, per-session init count and timing at the Stage-2 boundary before proposing any cache or firmware change.
