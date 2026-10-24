#!/usr/bin/env python3
"""Triage open issues: does the code already contain a fix referencing them?"""
import json, re, subprocess, sys

REPO = "ian-morgan99/benro-polaris-firmware-patcher"
SEARCH_PATHS = ["scripts", "container", "tests", "docs"]

out = subprocess.run(
    ["gh", "issue", "list", "--repo", REPO, "--state", "open", "--limit", "100",
     "--json", "number,title,body"],
    capture_output=True, text=True, check=True).stdout
issues = json.loads(out)

rows = []
for it in issues:
    n = it["number"]
    body = it.get("body") or ""
    # explicit status banner the project uses
    banner = re.search(r"STATUS[^\n]*", body, re.I)
    banner_txt = (banner.group(0)[:90] if banner else "")
    # code references to this issue number
    refs = subprocess.run(
        ["grep", "-rn", f"#{n}", "--include=*.py", "--include=*.c",
         "--include=*.h", "--include=*.sh", *SEARCH_PATHS],
        capture_output=True, text=True).stdout.strip().splitlines()
    # keep only references that look like fix annotations, not doc prose
    code_refs = [r for r in refs if re.match(r"^(scripts|container|tests)/", r)]
    rows.append((n, len(code_refs), it["title"][:60], banner_txt))

fixed = [r for r in rows if r[1] > 0]
true_total = subprocess.run(
    ["gh", "issue", "list", "--repo", REPO, "--state", "open", "--limit", "1000",
     "--json", "number", "--jq", "length"],
    capture_output=True, text=True).stdout.strip()
print(f"OPEN TOTAL (fetched {len(rows)}): true={true_total}")
print(f"WITH CODE REFERENCE TO THEIR OWN NUMBER (likely fixed): {len(fixed)}\n")
for n, c, t, b in sorted(fixed, key=lambda x: -x[1]):
    print(f"#{n:<4} refs={c:<3} {t}")
    if b:
        print(f"      banner: {b}")
