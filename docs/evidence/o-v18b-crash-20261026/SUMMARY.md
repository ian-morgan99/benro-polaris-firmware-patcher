# `.72` crash on the rig — evidence lost, and why

Operator reported a Benro Connect crash while testing `.72`. When I pulled the
device logs they were **0 bytes**:

```
/app/Mlog.txt   0 bytes      (69,719 bytes earlier the same day)
/app/Clog.txt   0 bytes
/proc/uptime    15144s       -> the device did NOT reboot
pgphoto         running, started ~22 min earlier
```

So `polestar_app` truncated both logs on restart without a reboot. There is no
rotation (`/app/log/` does not exist), no core dump (`/app/sd/core` is a 0-byte
placeholder from Oct 5) and nothing in `dmesg`. The only surviving content is a
couple of lines from after the crash.

**Consequence:** every crash we chase currently erases its own evidence. The Oct 10
session analysed on #241 survived only because it happened to be captured into the
repo at the time.

## What was recovered
`Mlog.txt` / `Clog.txt` as pulled — both empty, kept deliberately as proof of the
truncation, alongside the process and uptime observations above.

## Fix for the evidence gap
`scripts/diagnostic/capture-crash-session.sh` tails both device logs into host-side
files for the whole test session, using `tail -F` (follows by name and re-opens
after a truncate) with a 500-line backlog. The host copy is written continuously, so
it survives an app crash and the subsequent device-side truncation. Run it *before*
touching Benro Connect.

Tracked on #241.
