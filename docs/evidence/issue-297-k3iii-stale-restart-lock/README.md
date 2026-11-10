# Issue #297 — K-3 III not recognised: stale restart lock

Captured 2026-11-09 from the live device over read-only SSH, plus one write
(clearing the lock) performed with the operator's explicit approval after this
evidence was archived.

## Files

| file | what it is |
|---|---|
| `clog.txt` | `/app/Clog.txt` in full, **before** any change |
| `device-state.txt` | USB enumeration, interface descriptors, lock stat, filesystem type, process list, binary hashes — before |
| `webui-before.txt` | Astro WebUI probe attempt from the PC. TCP connects (`time_connect=0.022`) but no bytes are returned; recorded as-is rather than dropped |
| `device-after.txt` | Same probes after clearing the lock |

## Before

```
25fb:0189  PENTAX K-3 Mark III          # enumerated, configured, driver=usb
/var/run/openpolaris-pgphoto.restart.lock/   drwxr-xr-x  May 9 2025
pidfile bytes: 0                          # empty -> no owner to honour
df /var/run -> ubi0:ubifs                 # NOT tmpfs: survives reboot
```

`/app/Clog.txt`, every few seconds for the whole boot:

```
[restart_gphoto] another restart owns /var/run/openpolaris-pgphoto.restart.lock; refusing to race
[camera-usb] quarantined identity 1-1.2|25fb:0189|1:4 stable for 9 polls but bounded rebind failed; remaining degraded (issue #119)
```

## After clearing the lock

```
lock: No such file or directory
pgphoto.stage2ondisk  PID 249 -> 10026     # the bounded rebind ran and succeeded
camera-usb|restart_gphoto lines in Clog: 0 # quarantine spam stopped
listening: 00000000:1F90                   # :8080 bound by the new process
25fb / 0189                                # camera still enumerated
```

## What this proves, and what it does not

Proves the diagnosis: the lock was the reason `restart_gphoto` exited 1 on every
attempt, and removing it let the supervisor's bounded rebind succeed. The
`issue #119` quarantine loop stopped dead.

Does **not** prove recognition. After the restart pgphoto has no camlib mapped
(`/proc/10026/maps` lists neither `pentax.so` nor `ptp2.so`) and holds no USB
file descriptor — only stdin/stdout/stderr, `/app/Clog.txt` and one socket. So
`gp_camera_init` has not run yet. Layer 3 is a separate blocker from the lock,
and #297 stays open.

## Caveats on this evidence

- Clearing the lock truncated `/app/Clog.txt` to 0 bytes (the restart helper
  recreates it). The pre-fix content survives only in `clog.txt` here — which is
  exactly why it was archived first.
- The WebUI could not be read from this sandbox at all: TCP connects, no response
  bytes, on every path and both HTTP versions. The TA's opcode readings came from
  a different network position. Do not treat `webui-before.txt` as a baseline for
  comparison; it is a record of a failed probe.
