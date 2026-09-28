# Controlled v13j rebuild attempt

A controlled diagnostic rebuild was attempted using the exact v13j `FwPkt`
directory as the input and the same libgphoto2 checkout.  The patcher refused
to proceed while analysing `pgphoto`: the v13j application filesystem already
contains patched/non-stock binaries, so the stock patch-site analyser reports
`ELFError: Magic number does not match`.

This is a useful safety result.  It prevents silently stacking a new patch on
an already modified appfs.  A valid successor must instead be rebuilt from
the original stock package, replaying the exact v13j source/patch set, or the
patcher must gain an explicit, tested rebase mode.  No artifact was produced
or installed by this attempt.
