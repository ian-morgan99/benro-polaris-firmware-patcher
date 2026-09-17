# K-3 III Polaris Astro-mode capture lifecycle failure

Date: 2026-09-15
Camera: Pentax K-3 Mark III, USB `25fb:0189`
Polaris runtime: `polestar_app` PID 248, `pgphoto.stage2ondisk` PID 249
Preview: disabled in Benro Connect before test
Polaris mode: Astro mode was active in the Polaris/app workflow; this does not
mean the camera body was in a camera-specific Astro mode.
Raw evidence: `/tmp/pentax82-k3iii-astro-20260915/baseline-capture.txt`

## Result

A K-3 III capture initiated from Polaris Astro mode was dispatched through 9090
and produced:

```text
264@state:1
264@state:4
264@state:-108
```

No successful candidate, transfer, or reconciliation completion followed in the
captured trace. The camera remained enumerated and pgphoto/polestar plus ports
8080/9090 remained alive. This is a Polaris Astro-workflow capture lifecycle
failure, not proof that the camera body was in Astro mode and not the K-1 II
preview/USB failure.

## Next boundary

Do not repeat the Polaris Astro workflow yet. First determine whether `-108` is
the known pending-candidate/transfer lifecycle failure by comparing the full
Clog window with the v9e/v9f evidence. After the session returns READY, run at
most one controlled non-Astro Polaris capture to test recovery. Require
candidate ownership, transfer completion, reconciliation, and READY before
another Astro run.
