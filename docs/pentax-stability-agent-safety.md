# Physical-camera agent safety constraints

Agents controlling the connected Polaris/camera must:

- start with non-destructive scenarios;
- stop repeated runs if camera requires repeated hard power cycles or shows abnormal hardware behaviour;
- avoid deleting RAW/DNG unless the disposable test procedure explicitly authorises it;
- avoid uncontrolled restart loops;
- avoid very long exposures until instrumentation is confirmed working;
- preserve logs before recovery actions overwrite useful state;
- never leave Bulb/exposure active unattended without a bounded test plan;
- record any manual intervention because it changes session history.

The purpose of fault injection is controlled evidence, not maximum stress.
