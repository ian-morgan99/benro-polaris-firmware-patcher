# Pentax capture timing/watchdog inventory

Agent: populate this from source before E1.

| Layer | Source path/function | Constant/config | Duration | Starts when | On expiry | Can overlap EXPOSING? | Can overlap PROCESSING? | Evidence |
|---|---|---|---:|---|---|---|---|---|
| libgphoto2 | ptp2 capture path | `USB_TIMEOUT_CAPTURE` | 100000 ms currently observed | TO_VERIFY | TO_VERIFY | TO_VERIFY | TO_VERIFY | source audit required |
| pgphoto | TO_FIND | TO_FIND | | | | | | |
| watchdog | TO_FIND | TO_FIND | | | | | | |
| preview | TO_FIND | retry/bounds | | | | | | |
| supervisor | camera USB identity polling | TO_VERIFY | | | restart pgphoto on stable identity change | n/a | n/a | existing source |

The objective is not to increase every timeout. Determine which timers are transport I/O bounds, which are operation expectations, which cause active recovery, and whether any can fire first during a legitimate long Pentax operation.
