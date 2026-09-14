# FwVer Sum Behavior (sw: field)

## Discovery (2026-09-14)

The `sw:` field in code 780 (device info push) is **NOT** the camera FwVer directly. It is the **component-wise sum of gimbal FwVer + camera FwVer**:

```
sw: = gimbalFwVer + cameraFwVer  (component-wise, no carry)
```

### Evidence

| Build | Gimbal FwVer | Camera FwVer | sw: (displayed) |
|-------|-------------|--------------|-----------------|
| Stock | 2.0.0.22 | 4.0.0.32 | **6.0.0.54** |
| o-v7 (no override) | 2.0.0.22 | 4.0.0.32 | **6.0.0.54** |
| o-v9k (our override) | 2.0.0.22 | 6.0.0.54 | **8.0.0.76** |

### Implication

When we override `/app/FwVer` with our build ID (e.g., `6.0.0.54.3`), the displayed `sw:` becomes `2.0.0.22 + 6.0.0.54 = 8.0.0.76`. This is **expected behavior**, not a bug — but it means our build ID choice affects the displayed version.

### Fix Strategy

To control what Benro Connect displays:

1. **If we want stock-like display (6.0.0.54):** Set camera FwVer to `4.0.0.32` (stock). The app shows `2.0.0.22 + 4.0.0.32 = 6.0.0.54`.

2. **If we want a custom display:** Choose camera FwVer = `desired_display - 2.0.0.22` (component-wise). E.g., to show `7.0.0.10`, set camera FwVer to `5.0.0.88` (since `2+5=7`, `0+0=0`, `0+0=0`, `22+88=110` → but no carry, so `22+88=110` wraps? Need to verify).

3. **If we accept 8.0.0.76:** Document that our builds display as `8.0.0.76` (or whatever the sum is) and use that as the build identifier in the app.

### Open Question

Does the sum wrap at 256 per component, or is it simple addition? Need to test with a camera FwVer that would cause overflow (e.g., `4.0.0.200` → `2+4=6`, `0+0=0`, `0+0=0`, `22+200=222` → does it show `6.0.0.222` or wrap to `6.0.0.66`?).

## Action Items

- [ ] Decide on display strategy (stock-like vs custom)
- [ ] Update patch.sh to compute the correct camera FwVer for the desired display
- [ ] Test overflow behavior if using high component values
