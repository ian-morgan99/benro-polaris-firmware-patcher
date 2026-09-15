# Observed vs assumed

Every mode/timing/candidate report should distinguish:

- **requested/configured** — what host/camera settings say was requested;
- **observed** — what trace/PTP/camera evidence actually showed;
- **inferred** — a hypothesis used to design the next test.

Never write an inference such as "Pixel Shift produced five candidates" into a regression contract until the camera actually exposes that behaviour.
