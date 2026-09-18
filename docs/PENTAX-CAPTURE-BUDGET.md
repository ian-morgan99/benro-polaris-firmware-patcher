# Pentax capture-size budget

## Current contract

The patcher currently defaults `PENTAX_MAX_CAPTURE_SIZE` to `268435456` bytes
(256 MiB). `container/patch.sh` substitutes that value into the packaged
`pgphoto` wrapper as `LIBGPHOTO2_PENTAX_MAX_CAPTURE_SIZE`.

The value can be changed at build time with:

```sh
./patch-polaris.sh --fwpkt FwPkt/ --pentax-max-capture-size BYTES
```

The load-bearing implementation is `patch-polaris.sh`, `container/patch.sh`,
`container/ondisk/pgphoto.wrapper.in` and
`container/ondisk/install_stage2.sh`.

## Evidence boundary

The 256 MiB setting is present in the current packaging path and is large
enough for the bounded K-3 III captures recorded for o-v9p. That is not a
standalone boundary test and does not prove every Pentax multi-output or future
high-resolution mode fits the cap. A successor that changes this value must
run the package-content gate and camera capture regression before qualification.

Earlier OOM predictions, destructive boundary experiments and historical
implementation narrative are preserved in PrivateResearch's issue 116 archive;
they are not current qualification claims.
