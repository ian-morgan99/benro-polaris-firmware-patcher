# Pentax stability artifact layout

Recommended local/test artifact structure:

```text
tests/pentax_stability_artifacts/
  <run-id>/
    manifest.json
    trace.jsonl
    Mlog.log
    Clog.log
    result.md
```

Large/raw runtime artifacts need not be committed to git. The GitHub issue/result must preserve enough provenance to retrieve the evidence and reproduce the run.

Never commit image payloads merely for stability tracing unless a specific image-content defect requires them.
