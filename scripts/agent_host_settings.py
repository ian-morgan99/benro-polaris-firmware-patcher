#!/usr/bin/env python3
"""Shared helpers for the agent host-config checkers (issues #184, #185).

Both ``check-agent-sandbox.py`` and ``check-agent-host-config.py`` read the
same VS Code-family settings files; the loader lives here so the two checks
cannot drift apart on comment handling or file discovery order.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Product user-settings locations, VS Code family. All found files are merged
# in the same order the editor merges them (user first, workspace last so it
# overrides).
USER_SETTINGS_RELPATHS = [
    Path(".config/Code/User/settings.json"),
    Path(".config/Code - Insiders/User/settings.json"),
    Path(".config/Code - OSS/User/settings.json"),
    Path(".config/Code - OSS - Dev/User/settings.json"),
    Path(".config/VSCodium/User/settings.json"),
]


def strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments and trailing commas from JSONC."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)

    def _sub(match: re.Match) -> str:
        token = match.group(0)
        return token if token.startswith('"') else ""

    text = re.sub(r'"(?:[^"\\]|\\.)*"|//[^\n]*', _sub, text)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text


def load_settings(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    return json.loads(strip_jsonc(raw))


def discover_user_settings(home: Path) -> list[Path]:
    return [
        home / rel for rel in USER_SETTINGS_RELPATHS if (home / rel).is_file()
    ]
