# Pentax stability trace schema

`tools/pentax_stability_trace.py` currently records JSONL fields:

- `run_id`
- `experiment`
- `event`
- `monotonic_ns`
- `wall_time_ns`
- `pid` (observer PID in the scaffold; source instrumentation should log real pgphoto PID separately)
- `phase`
- `command`
- `camera_state`
- `session_state`
- `usb_fingerprint`
- `candidate_count`
- `details`

Use `details` for structured, bounded extras such as shutter, format, candidate descriptors and recovery reason. Do not put image payloads in the trace.

Once source-level events exist, keep schema compatibility where practical so traces can be analysed by `tools/analyse_pentax_stability_trace.py`.
