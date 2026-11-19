---
name: polaris-release
description: Route Polaris firmware, Astro kit, publication and device-install requests to the maintained release workflow.
---

# Polaris release routing

Open the [release workflow](../polaris-release-orchestrator/SKILL.md) for the command, inputs and effects of the requested operation. Read the same procedures directly from the checkout if your agent client has no skill support.

First identify whether the task calls for local build, private upload, remote verification, SD staging, live install or physical qualification. The camera firmware builder uploads as part of its run. The convenience wrapper's `--install` option wakes Polaris, flashes it and reboots it. Choose the entry point for the requested stage.

Use the [release version register](../../../docs/RELEASE-VERSION-STATE.md) and [provenance contract](../../../docs/FWPKT-PROVENANCE-CONTRACT.md) for exact identities. For existing downloads, use the [artifact auditor](../polaris-release-artifact-auditor/SKILL.md). For device recovery, use the [install procedure](../fwpkt-update-flow/SKILL.md).
