# Example causal test report (illustrative only)

> This is format guidance, not evidence.

**Scenario:** E1-101 101 s normal JPEG  
**Result:** FAIL 2/3  
**First divergence:** watchdog X invoked session reset at monotonic T while USB fingerprint remained unchanged and camera condition still indicated legitimate operation.  
**Later symptoms:** `session already open`, preview failure.  
**A/B:** 99 s 0/3 fail; 101 s 2/3 fail.  
**Next discriminator:** instrument watchdog X expiry and repeat 99/100/101 with preview off.  
**Causal status:** correlated/discriminated only after repeat; not yet proven fix.

Reports should be this concrete. Avoid "camera crashed, reset fixed it" as the engineering conclusion.
