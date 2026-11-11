# GitHub Issue: v104 K1 II — Focus speed changes work but full range of values not observed

**Title:** [v104] K-3 III/K-1 II: Focus speed changes work but only f:0-f:4 observed, higher values missing

**Labels:** bug, v104, k1-ii, k3-iii, pentax, focus, autofocus

**Device:** Benro Polaris, FwVer:6.0.0.54.104, date:2026.11.10, build_id=v104  
**Camera:** Pentax K-1 Mark II / K-3 Mark III  
**Client:** Android phone (Benro Connect app)  
**Logs:** `docs/evidence/v104-k1ii-liveview-garbled-20261110/`

---

## Summary

On v104 with Pentax cameras, focus mode changes ARE working — they return `ret 0`. However, the full range of focus speed values is not being observed. Only f:0 through f:4 have been seen, while higher values (f:5, f:6, etc.) expected for "far fast" and similar settings are missing.

## Observed Behavior

From `Clog-focus-speed.txt`:

```
f:0  - 9 occurrences
f:1  - 9 occurrences
f:2  - 82 occurrences
f:4  - 6 occurrences
```

Each change returns `ret 0`:
```
setFocusChange configType 4 value: 6 ret 0 fDelay 2
SP_sendMsg success code:262 val[mod:1;f:2;ret:0;]
```

## Expected Behavior

All focus speed values should be available:
- Near slow, near medium, near fast
- Far slow, far medium, far fast  
- AF (auto focus)

Each should map to a distinct focus speed value (f:0 through f:6 or higher).

## Actual Behavior

Only f:0, f:1, f:2, f:4 are observed. Higher values (f:5, f:6, etc.) are missing. The user pressed "near fast", "near medium", "near slow", "far slow", "far medium", "far fast", AF — but only 4 distinct values appear in the logs.

## Steps to Reproduce

1. Connect K1 II or K3 III to Polaris running v104
2. Open liveview in Benro Connect on Android
3. Change focus speed through all available settings (near slow → near medium → near fast → far slow → far medium → far fast → AF)
4. Observe that only f:0, f:1, f:2, f:4 values appear in the logs — higher values are missing

## Expected Behavior

All focus speed values should be available and each should produce a distinct f:N value in the logs.

## Actual Behavior

Only f:0, f:1, f:2, f:4 are observed. Higher focus speed values are not being sent or are being mapped incorrectly.

---

## Files

All logs saved under `docs/evidence/v104-k1ii-liveview-garbled-20261110/`:

| File | Size | Description |
|------|------|-------------|
| `Mlog-focus-speed.txt` | 16,894 bytes | Mlog with focus speed changes |
| `Clog-focus-speed.txt` | 39,267 bytes | Clog with focus speed changes |
| `Mlog-focus-speed-2.txt` | 0 bytes | Empty (device state issue) |
| `Clog-focus-speed-2.txt` | 324 bytes | Minimal log after focus speed presses |

Key log lines:
- `Clog-focus-speed.txt`: `setFocusChange configType 4 value: 6 ret 0 fDelay 2`
- `Clog-focus-speed.txt`: `SP_sendMsg success code:262 val[mod:1;f:2;ret:0;]`
- `Clog-focus-speed.txt`: `f:0` (9x), `f:1` (9x), `f:2` (82x), `f:4` (6x)

---

## Related Issues

- #278: Polaris: AutoFocus mode change never observed in logs — only manual focus (mode:1) seen — **now partially resolved** — focus mode changes work but full range of values not observed

---

**Note:** This is v104 test evidence. The device is running build_id=v104, display_fwver=6.0.0.54.104, libgphoto2 commit=806c3bda62d6c0c23ca7a3091fb42f3d7894172b, patcher commit=1e88637cf61d152f94e23f6e139adec4b9fa80c2.