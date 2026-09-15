# Lab reproduction vs field qualification

The lab/agent camera rig is for precise causal discrimination. Field testers are for real-world diversity and confirmation.

A lab fix should first pass its deterministic reproducer and adjacent baselines. Then compare its fingerprint against existing field logs and ship through the normal FwPkt/release gate for external confirmation.

Do not ask field testers to execute complex timing races that the connected agent rig can automate.
