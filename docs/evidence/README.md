# Evidence layout — what is tracked here, and where the raw bytes live

This directory holds **public** evidence: `SUMMARY.md`, `README.md`, provenance rows,
and transcripts saved as `.txt`. That is deliberate. `.gitignore` excludes
`docs/evidence/**/*.{log,bin,stock,tmp,pid}` because rotating device logs and
firmware-derived snapshots are large, churn constantly, and belong in the private
archive rather than a public repository.

## Where raw logs actually are

Rotating `Clog_*` / `Mlog_*`, SD filesystem dumps, crash captures and similar raw
artifacts live in **PrivateResearch**, not here:

    PrivateResearch/polaris-evidence/<session>-<date>/          per-session captures
    PrivateResearch/polaris-evidence/patcher-repo-raw-evidence/  moved out of this repo

The second path mirrors the relative paths that were previously tracked here, so a
reference like `docs/evidence/bulb-session-20260930-0201/raw/Clog_000180.log` resolves
by prefixing it with `patcher-repo-raw-evidence/`.

## Why they were removed from tracking

Thirty-three files totalling 33 MB were tracked here despite the ignore rules above —
31 of them committed *after* the rule that forbids them, which means they got in via
`git add -f`. Nothing noticed for six weeks because a force-added file never appears in
`git status` again: it is tracked, so it is not untracked, and it matches an ignore
rule, so it is silently invisible to every check that looks at the working tree.

They are now untracked with `git rm --cached`, so they remain on disk for anyone who
already has a checkout, and byte-identical copies are preserved in PrivateResearch.
Nothing here lost data.

## For a developer agent reading this

If you need a raw log that is not present in your checkout:

1. Look in `PrivateResearch/polaris-evidence/` first — it is the authoritative archive.
2. If you are on a machine without PrivateResearch, the file may still exist locally at
   the path quoted in the summary; check before assuming it is gone.
3. Do **not** `git add -f` a raw log back into this repository. The ignore rule is the
   policy, not an oversight, and `build-doctor.sh` now fails a release build if anything
   tracked matches `.gitignore`.

Transcripts that are worth publishing should be written as `.txt` or `.md` summaries
with the relevant lines quoted, which is what the rest of this directory does.
