# Repeatable astro multi-shot simulation

This test exercises the camera workload that an astro sequence creates: several
ordinary exposures over one authenticated Polaris control session. Preview is
suspended for exclusive capture ownership and restored to its initial state.
It deliberately does **not** invoke the native timelapse/composite state machine;
those numeric mappings remain unqualified. It also does not prove tracking or a
long Bulb exposure.

## Preconditions

1. Connect to the real `polaris_*` AP and prove the route uses Wi-Fi:

   ```bash
   nmcli -t -f BSSID,SSID device wifi list | grep -i 48:E7:DA
   ip route get 192.168.0.1
   ssh root@192.168.0.1 'cat /app/FwVer; lsusb | grep 25fb'
   ```

2. Confirm `pgphoto`, port 8080, port 9090, and camera state 1 are healthy.
3. Use a charged camera battery and a formatted card with adequate free space.
4. Close other preview consumers. Record any other 9090 client that remains.
5. Qualify one ordinary shot first; only progress if it produces post-request
   code 264 lifecycle evidence and one non-empty code 773 `path`, without a
   negative state.

## Commands

Ordinary baseline:

```bash
python3 scripts/test-astro-multishot.py --execute --shots 1
```

Bounded simulated astro sequence (three shots, ten seconds apart):

```bash
python3 scripts/test-astro-multishot.py --execute --shots 3 --interval 10
```

The script authenticates with `284 -> 820 -> 823`, queries preview, switches it
off if required, then sends the live-qualified shutter frame
`1&264&4&state:1;bulb:0;c:-1;#`. It holds one TCP connection throughout and
stops on a timeout, negative state, missing lifecycle/file correlation,
multiple file paths for one shot, or socket loss. It restores preview before
closing when preview was initially on.

## Pass criteria

- Every shot has post-request code 264 lifecycle evidence and exactly one
  non-empty code 773 `path` event before the next shutter.
- The camera remains present as USB `25fb:*`.
- `pgphoto` and `polestar_app` retain their PIDs.
- Ports 8080 and 9090 remain listening.
- No `GP_ERROR`, negative capture state, USB disconnect, or Wi-Fi pool-exhaustion
  signature appears in the test window.
- Correlate `Clog.txt` with the physical card/file count before claiming that
  each exposure produced a durable image.

Do not require states `2`, `3`, and `5`: live o-v9o evidence showed the useful
K-3 III sequence `1 -> 4 -> 0` while a durable DNG was created. Conversely,
neither idle state `0` nor elapsed time alone proves completion. Stop rather
than issuing the next shutter unless lifecycle and file evidence correlate.

This is a workload simulation, not full native Astro qualification. Full Astro
qualification additionally needs tracking state, intended exposure duration,
camera processing/noise-reduction completion, native interval scheduling, and
output-file verification.
