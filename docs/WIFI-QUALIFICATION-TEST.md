# Wi-Fi qualification test (issue #68)

This is the repeatable, read-only evidence collector for Broadcom `bcmdhd`
TCP-ACK tracking failures. It does not open 8080/9090, mutate the device, or
create the workload. Run the workload under test separately and record its
exact client count and timing.

## Driver-change gate

A replacement `bcmdhd.ko` is not currently reproducible from this repository.
The stock artifact is ARM EABI5, has vermagic
`4.9.37 SMP mod_unload ARMv7 p2v8`, and identifies itself as
`1.363.125.19`, built from `drivers/net/wireless/bcmdhd` on 2021-05-13. The
repository has the stock module bytes inside the proprietary appfs input, but
does not have the matching kernel tree/config, Broadcom source revision,
`Module.symvers`, or a module build recipe. Do not substitute a public DHD tree
or binary-patch the module: either could load but violate private kernel ABI or
radio/platform assumptions.

Before a driver candidate is allowed, acquire and record all of:

1. the exact Hi3559V200 Linux 4.9.37 kernel source and `.config`;
2. the exact Broadcom DHD source/revision corresponding to driver 1.363.125.19;
3. generated headers plus `Module.symvers` from the deployed kernel build;
4. the matching ARM toolchain and a reproducible `bcmdhd.ko` build whose
   architecture, vermagic, undefined symbols, module parameters, and baseline
   behaviour match stock;
5. an immutable rollback FwPkt and the full provenance registry record.

## Deterministic collection

First close unrelated desktop/mobile clients. Prove the host is associated to
the real `polaris_*` AP and route to `192.168.0.1` through the chosen Wi-Fi
interface. The script enforces both checks and verifies `/app/FwVer` over SSH.

```bash
WIFI_IFACE=wlp8s0 \
  ./scripts/monitor-wifi-qualification.sh \
  --duration 3600 --interval 5 \
  --output docs/evidence/wifi-single-client-$(date -u +%Y%m%dT%H%M%SZ).tsv
```

The TSV records cumulative kernel error counts, WLAN byte counters, and
established 8080/9090 clients. Save the workload's own frame/capture log beside
it. A valid run has no `WRONG_ROUTE_OR_AP` rows and identifies the expected
firmware on every `UP` row.

Run phases independently, from a cold boot where practical:

1. idle baseline with no preview client;
2. one control client and one preview stream for 60 minutes;
3. preview-off still/multi-shot workload with one control client;
4. separately labelled multi-client stress.

For each phase report the first/last error counters and deltas, first/last WLAN
byte counters, maximum simultaneous client counts, disconnect duration, frame
cadence, and whether recovery required reboot. A workload mitigation passes
issue #68 only when the 60-minute single-client run has zero new
`No more free tdata_psh_info` and `Out of tdata_disc_grp` messages and no AP,
SSH, 9090, or 8080 loss. Multi-client stress is reported separately; it must
not be silently mixed into the single-client result.

Any future driver candidate must additionally regress AP association, DHCP,
SSH, 8080, 9090, Bluetooth coexistence, sleep/wake, and the Canon R5 Mark II,
Pentax K-3 III, and Pentax K-1 II camera matrices after canonical FwPkt install
and cold reboot.
