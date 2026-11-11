"""Parse-check shell scripts with the interpreter they actually declare.

Why this exists: three tests used `sh -n <path>` to syntax-check scripts whose
shebang was `#!/bin/bash`. On the development host /bin/sh is a symlink to bash,
so bash-only syntax (arrays, [[ ]], local -n) parsed fine and the tests passed.
On a GitHub runner /bin/sh is dash, which rejects that same syntax, so the tests
went RED on perfectly valid scripts.

That is a wrong-interpreter bug in the *test*, not a defect in the scripts: a
script declaring #!/bin/bash is never executed by dash, so dash's opinion of it
is irrelevant. Conversely a script declaring #!/bin/sh must parse under dash --
that check is genuinely useful and is preserved here.

Rule applied: honour the shebang. `#!/usr/bin/env bash` and `#!/bin/bash` are
checked with bash; anything else with sh. A script that declares #!/bin/sh but
contains bash-only syntax still fails, which is the case worth catching.
"""

from __future__ import annotations

import os
import shutil
import subprocess


def interpreter_for(path: str) -> list[str]:
    """Return the argv prefix that matches the script's declared interpreter."""
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        first = handle.readline()
    if not first.startswith("#!"):
        return ["sh"]
    line = first[2:].strip()
    parts = line.split()
    if not parts:
        return ["sh"]
    program = os.path.basename(parts[0])
    if program == "env" and len(parts) > 1:
        program = os.path.basename(parts[1])
    if program in ("bash", "zsh", "ksh", "dash"):
        # Fall back to sh only if the declared interpreter is genuinely absent;
        # silently substituting a different shell would hide a portability problem.
        return [program] if shutil.which(program) else ["sh"]
    return ["sh"]


def parse_check(path: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Syntax-check `path` with the interpreter its shebang declares."""
    argv = [*interpreter_for(path), "-n", path]
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
