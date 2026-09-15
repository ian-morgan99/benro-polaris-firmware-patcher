# pgphoto process-health stability notes

Instrument pgphoto independently of camera state.

Record PID, exit/signal/restart, RSS, fd/thread counts and watchdog reason. A process restart that happens **before** camera/session divergence may be causal; a restart after divergence is recovery.

E11 looks for cumulative resource/state trends. E8 later tests deliberate process loss by lifecycle phase. E12 compares fresh process vs in-process reset histories.

If an in-process reset cannot prove that abilities, explicit port, PTP/Pentax state and candidates are clean, a fresh pgphoto process is a safer recovery boundary than reusing contaminated objects.
