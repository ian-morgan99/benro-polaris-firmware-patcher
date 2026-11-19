---
name: fwpkt-private-upload
description: Publish a verified camera firmware packet into PrivateResearch and retain immutable bytes, source identity and remote evidence.
---

# Publish a camera firmware packet

Use the [release workflow](../polaris-release-orchestrator/SKILL.md) to select the release type. The camera firmware builder calls the packet uploader after its release gate. Astro bundles use `scripts/publish-astro-candidate.sh` and their declared companion files.

For an already-built camera packet, inspect the build directory, exact identity manifest, artifact hashes and release gate. The uploader is repo-local and works from the checkout:

~~~bash
bash .github/skills/fwpkt-private-upload/scripts/upload-fwpkt-to-pr.sh \
  --build out/ID --id ID --dry-run
~~~

The dry run validates and stages a temporary copy. Dropping `--dry-run` publishes to PrivateResearch. The default run creates a separate temporary clone. If you pass `PR_CHECKOUT`, use a dedicated, clean clone on main with matching origin and no unpublished commits. Use Git's credential helper or authenticated GitHub CLI credentials.

The packet path is `firmware-packets/<display-version>--<id>/FwPkt.zip`. Publish exact bytes once. A rerun may reuse the same archive and identity already present. A conflicting path requires reconciliation before retrying. Record the remote commit and full digests in [the provenance register](../../../docs/FWPKT-PROVENANCE-CONTRACT.md) and verify the downloaded files using [the artifact audit](../polaris-release-artifact-auditor/SKILL.md).

Packet upload is one milestone. Complete [release documentation](../polaris-release-documentation/SKILL.md) and any required companion set before handing the candidate to a user for install.
