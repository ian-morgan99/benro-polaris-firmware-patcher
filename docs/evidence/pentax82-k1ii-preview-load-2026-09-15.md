# Issue #82 K-1 II preview/client-load observation

Date: 2026-09-15
Camera: Pentax K-1 Mark II, USB `25fb:0183`
Runtime: `pgphoto.stage2ondisk` PID 249, `polestar_app` PID 248

## Observation

With the iPhone 12 Pro acting as the active keepalive client, K-1 II capture
completed normally (`SP_0032.jpg`, terminal states `3` and `5`) and USB, pgphoto,
8080, and 9090 remained healthy.

During the surrounding preview/client activity, Clog repeatedly showed:

- valid Pentax preview frames (`0x2001`, roughly 27-33 KB in this period);
- repeated app-side `code:266` socket activity and `SOCKET_CLOSE` events;
- repeated `get_single_config` failures with `-2`;
- `waitCameraIdle busy` during capture/control polling;
- no USB removal and no pgphoto/polestar death.

The older iPad crash therefore remains consistent with client-side preview/data
pressure or app-side reconnect churn, but this evidence does not prove that
preview frequency alone is the cause.

## Next A/B test

Keep the K-1 II and iPhone 12 Pro on the same Polaris setup. Compare:

1. normal preview cadence;
2. reduced client preview cadence, with all other controls unchanged;
3. preview disabled.

For each run record preview frame cadence/size, app socket closes, `code:266`,
`waitCameraIdle busy`, capture terminal state, USB identity, pgphoto PID, and
9090/8080 health. The server/runtime preview path should not be modified until
client-side throttling has been tested.
