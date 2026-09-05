#!/usr/bin/env python3
"""Create the full-review issues in ian-morgan99/benro-polaris-firmware-patcher.

Usage:
    GITHUB_TOKEN=<token> python3 scripts/create-review-issues.py

Idempotent-ish: skips an issue if one with the same title already exists.
"""
import json
import os
import sys
import urllib.request

REPO = "ian-morgan99/benro-polaris-firmware-patcher"
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

ISSUES = [
    {
        "title": (
            "HIGH: docs/TESTED.md + stage2_patch.py still cite the upstream "
            "loader/trampoline md5s, but our loader now links stage2_policy.c"
        ),
        "body": """## Finding

Our `container/stage2_loader.c` diverges from upstream: it links in
`stage2_policy.c` (the R5-II-only shim gate via `gp_camera_get_abilities`),
which upstream's loader does not have. Upstream's hardware-validated binaries
were built *without* that object.

Yet our repo still asserts the upstream hashes as "hardware-validated":

- `docs/TESTED.md:45-46` — loader `74f681de…`, trampolined pgphoto `a83ac7bb…`
- `docs/HOW-IT-WORKS.md:179-180` — same two hashes in the Determinism section
- `container/stage2_patch.py:92` — `KNOWN_STAGE2_OUT_MD5 = a83ac7bb…`

The trampoline output (`pgphoto.stage2ondisk`) is produced by patching the
stock binary, so `a83ac7bb` may still be correct for *that* file — but the
**loader** md5 `74f681de` cannot match a loader compiled with an extra object
file. Nothing in our build asserts the loader md5, so the table is silently
stale rather than loudly wrong.

## Why it matters

The TESTED.md table is the reproducibility contract: "the patcher reproduces
the exact hardware-validated components byte-for-byte". If a future run
reproduces `74f681de` for the loader, that would mean our R5-gate code is not
in the shipped binary at all.

## Suggested checks

1. Build in the container and md5 the produced `libpolaris_stage2.so`; record
   the new value (or drop the loader row until re-validated).
2. Decide whether the R5-II gate changes the *hardware-validated* claim: the
   flashed build was upstream's loader; ours adds a fail-closed abilities
   check. Either re-flash-validate, or annotate the table with "loader now
   includes stage2_policy.c (R5-II gate) — md5 X, not yet flash-validated".
3. Consider asserting the loader md5 in `patch.sh` (fail-closed), mirroring
   what `stage2_patch.py` does for the trampoline output.

## Upstream reference

Upstream `blaineam/benro-polaris-firmware-patcher` @ `b62c407` — loader has no
`stage2_policy` include; its TESTED.md table matches its own build.""",
    },
    {
        "title": (
            "MED: Windows CRLF protection missing — no .gitattributes, no Dockerfile "
            "CR-strip, launchers don't check docker build exit code"
        ),
        "body": """## Finding

Upstream fixed a real Windows failure mode (their issue #1): a CRLF checkout
makes every container script die with `/bin/bash^M: bad interpreter`, and it
also changes the bytes of `pgphoto.wrapper` / `stage2_loader.c` that the build
is supposed to reproduce byte-for-byte. Their fix has three parts, none of
which we have:

1. **`.gitattributes`** pinning LF for everything the container consumes
   (`*.sh`, `*.py`, `*.c`, `*.in`, `Dockerfile`, `pgphoto.wrapper`; CRLF only
   for `*.ps1`). We have no `.gitattributes` at all.
2. **Dockerfile belt-and-braces**: after `COPY container/ /opt/patcher/`,
   strip stray CRs (`sed -i 's/\\r$//'`) and assert `patch.sh`'s shebang, so
   pre-fix clones and zip exports still work. Ours only does `chmod +x`.
3. **Launcher exit-code checks**: upstream's `patch-polaris.ps1` no longer
   runs `docker build -q … | Out-Null` unchecked — a silent build failure used
   to let the script print `[OK]` over a broken image. Ours still does:
   - `patch-polaris.ps1:62` — `docker build -q … | Out-Null`, no `$LASTEXITCODE` check
   - `patch-polaris.sh:85` — `docker build -q … >/dev/null`, and the script has
     `set -eu` (line 27) so a failed build *does* abort, but with no diagnostic
     output at all.

Also upstream normalises Docker Desktop bind-mount paths (`ProviderPath`,
drive letter + forward slashes, UNC rejection); our ps1 uses `.Path`, which
can hand back `FileSystem::C:\\…` provider paths.

## Suggested checks

- Reproduce: on a Windows machine (or with `git config core.autocrlf true`),
  clone our repo and run the ps1; confirm the CRLF failure mode is live for us.
- Port upstream's `.gitattributes` + Dockerfile CR-strip (they are small and
  independent of our Pentax/source-input work).
- Add a `$LASTEXITCODE` check after `docker build` in the ps1, and drop `-q`
  or at least surface the failure reason in the sh launcher.

## Upstream reference

`blaineam/benro-polaris-firmware-patcher` commit `004c057` ("Add optional
--ssh-key debug access; fix Windows CRLF container build (#1)").""",
    },
    {
        "title": (
            "MED: patch-polaris.ps1 prints [OK] over a failed docker build — "
            "silent success on broken image"
        ),
        "body": """## Finding

`patch-polaris.ps1:62`:

```powershell
docker build -q -t $Image -f (Join-Path $Here "docker\\Dockerfile") $Here | Out-Null
```

No `$LASTEXITCODE` check follows. If the image build fails (e.g. CRLF
checkout, network blip pulling debian:9), the script sails on to `docker run`,
which then fails with a confusing "no such file or directory" against the
*previous* (possibly stale) image — or succeeds against a stale image and
prints `[OK]` for output that was never actually produced.

Upstream fixed exactly this in commit `004c057`: build is no longer quiet,
and both build and run exit codes are checked with explicit error messages.

## Suggested fix

```powershell
docker build -t $Image -f (Join-Path $Here "docker\\Dockerfile") $Here
if ($LASTEXITCODE -ne 0) { throw "docker build failed (exit $LASTEXITCODE). The build output above says why; nothing was patched." }
```

(And consider the same for `patch-polaris.sh`, which currently swallows all
build output with `>/dev/null`.)""",
    },
    {
        "title": (
            "LOW: untracked working files (STATE.md, builds/, scripts/, docs/evidence/) "
            "— decide what belongs in the repo"
        ),
        "body": """## Finding

`git status` shows a growing pile of untracked content that is neither
committed nor ignored:

- `STATE.md`, `LMStudioLogEnhancements.md` — investigation state notes
- `builds/2026-08-23`, `builds/2026-08-27-combined-720p60`,
  `builds/2026-08-29-libgphoto2-only`, `builds/2026-08-30-padded-appfs`
- `docs/CROSS-PROJECT.md`, `docs/evidence/polaris-ssh-2026-08-31`
- `scripts/reboot-via-812.sh`, `scripts/watch-fwpkt-update.sh`

Issues #3/#7 reference `builds/…/build-source-provenance.txt`, so the builds
directory is load-bearing for provenance claims even though it isn't tracked.
Note `.gitignore` has no `builds/` entry, and `*.bin` / `*.ubifs` patterns
would hide firmware blobs *inside* those dirs if they were ever added.

## Suggested checks

- Decide per-item: commit (provenance, scripts), ignore (evidence dumps), or
  move to the analysis repo (STATE.md is about the FwPkt install
  investigation, which #17 split out).
- If `builds/` stays untracked, document that provenance files are local-only.
- Add `builds/` and `docs/evidence/` to `.gitignore` if they're meant to be
  scratch space.""",
    },
    {
        "title": (
            "LOW: upstream added --ssh-key debug access — decide whether to adopt or "
            "document the divergence"
        ),
        "body": """## Finding

Upstream's latest commit (`004c057`) adds an opt-in `--ssh-key` / `-SshKey`
flag: it adds one new appfs file (the stock `/app/bootapp` already runs
`/app/network_telnetd.sh` if present) that appends a validated public key to
`/root/.ssh/authorized_keys` at boot. Key validation lives in
`container/gen_ssh_hook.py`; `out/ssh-debug/` ships the hook standalone with
install-without-flashing and removal instructions. Upstream's TESTED.md marks
it "verified in the build, NOT yet flash-verified".

We don't have it. That's fine if deliberate — but our README/CHANGELOG don't
mention the divergence, and our own `docs/evidence/polaris-ssh-2026-08-31`
suggests we've been doing ad-hoc SSH access on the device.

## Suggested checks

- Adopt upstream's `gen_ssh_hook.py` + patch.sh section (it is self-contained
  and fail-closed: aborts rather than editing bootapp if no free hook exists).
- Or document in README why we don't ship it, so a user of our fork isn't
  surprised the flag is missing.
- If adopting: note the hook is not flash-verified upstream; add to our
  TESTED.md accordingly.""",
    },
]


def api(path, data=None, method="GET"):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}{path}",
        data=json.dumps(data).encode() if data is not None else None,
        headers={
            "Authorization": f"token {TOKEN}",
            "User-Agent": "VSCode-LMStudio-Bridge",
            "Accept": "application/vnd.github+json",
        },
        method=method,
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def main():
    if not TOKEN:
        sys.exit("set GITHUB_TOKEN (or GH_TOKEN) first")
    existing = {i["title"] for i in api("/issues?state=all&per_page=100")}
    for issue in ISSUES:
        if issue["title"] in existing:
            print(f"skip (exists): {issue['title'][:60]}…")
            continue
        created = api("/issues", {"title": issue["title"], "body": issue["body"]}, method="POST")
        print(f"created #{created['number']}: {created['html_url']}")


if __name__ == "__main__":
    main()
