---
name: polaris-release-reconciliation
description: Reconcile Polaris candidate records against immutable PrivateResearch files and record exceptions by release type and exact build.
---

# Reconcile Polaris releases

Start from the [provenance register](../../../docs/FWPKT-PROVENANCE-CONTRACT.md), [version state](../../../docs/RELEASE-VERSION-STATE.md) and the actual PrivateResearch tree. Use the [artifact auditor](../polaris-release-artifact-auditor/SKILL.md) for presence and content. For each row record the candidate ID, app-reported firmware version, kit identity, exact source pair and downloaded content hashes, followed by completed and missing milestones.

Compare the declared release type and archive requirements before classifying completeness. Check firmware and kit identity separately. The historical v110 firmware row is `6.0.0.54.110`; the v111 WebUI-open kit has its own ID and compatibility requirement. Historical version/label disagreements belong in the exception ledger with their actual artifact identity. For new Astro firmware candidates, follow the current version binding in the register.

If a push failed, inspect the remote ref and target path before retrying. Keep previously published binary bytes immutable. Use an explicit superseding candidate for changed bytes and preserve the older row and evidence. Link reconciliation exceptions to #350/#356 when applicable.
