# K-3 III direct-PC preview on 23 November 2026

This corrects the preview conclusion in F9 of k3iii-issue-list.md. The K-3 III returned a decodable 1080 × 720 JPEG on direct USB. The earlier unsupported-operation result depends on how the host driver was compiled.

Both clean builds used driver 0f2f34e0004011136fa75bf43e215acc0c8b9fdb. The default host build returned -6 and zero bytes. Enabling the Meson option pentax_research_capture, corresponding to the macro used by container/build_ptp2.sh for the ARM camera driver, enabled the vendor branch in camera_capture_preview. The body answered operation 0x9006 with 0x2001 on the first attempt in 15 ms, returning 72,611 bytes. Pillow decoded the entire frame in memory. Separate sessions read PC live view off before and after. The camera reported battery 100%, RAW, zoom off and shutter 00:01 before the comparison.

This qualifies one direct-PC preview. Still capture, sustained frame cadence, Android rendering, and the Polaris K-01 path each need their own evidence. The PC test used only USB port 001,013. Copilot's installer retained ownership of Polaris. The local logs are under out/k3iii-readback-20261123-GwTN.
