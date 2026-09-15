# Liveness during multi-minute captures

A long Pentax operation needs two independent questions:

1. **Is the camera operation plausibly still in progress?** Mode, requested shutter and observed camera conditions inform this.
2. **Is the transport/process actually healthy?** USB/PTP/process evidence answers this.

Do not make the first question a proxy for the second.

If expected duration is exceeded but safe observations still show a live camera/process/transport, record expectation overrun and continue according to bounded phase policy. If actual transport/process failure occurs, recovery may proceed regardless of nominal shutter duration.

The hardware campaign must determine which observations are genuinely safe while Pentax is busy; a liveness probe that disrupts capture is not a valid probe.
