# USB transport vs camera-session health

The existing USB supervisor handles stable camera USB identity changes because pgphoto can otherwise retain stale abilities/explicit ports.

That does not cover every session failure. A Pentax body can remain physically enumerated with the same USB fingerprint while capture/PTP/application state is contaminated. In that case an identity-change supervisor correctly sees nothing to do.

Therefore every experiment records USB identity independently from camera/PTP/process state. Do not use unrelated `ttyUSB` failure as proof that the Pentax camera endpoint disappeared.
