# Pentax stability objective metrics

Track objective metrics rather than subjective "seems stable" assessments.

- failure rate per scenario (`failures / runs`);
- consecutive successful capture count;
- time from shutter request to camera READY;
- time from first candidate to reconciliation terminal;
- pending candidate count at next shutter (target 0 unexplained);
- automatic recovery/restart count per 100 captures (target 0 in clean baseline);
- Polaris reboot requirement per test campaign (target 0 for recoverable software failures);
- pgphoto RSS/fd/thread trend vs capture count;
- preview failure/NoUpdateImage rate by lifecycle phase;
- command reject/queue counts by phase;
- USB identity changes vs camera-session failures;
- failure probability around timeout boundaries.

Use these measurements to decide where engineering changes add value. Do not change deterministic runtime behaviour because an agent subjectively predicts it might help.
