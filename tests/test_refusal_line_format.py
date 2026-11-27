"""The refusal line's field order is load-bearing for two gate probes.

scripts/probe-config-gate.py and scripts/stress-config-gate.py both match the literal
prefix "admission refused: site=<hex> kind=<n>". Inserting a field between "refused:"
and "site=" makes both regexes match nothing, and a probe that finds zero refusals
reports a clean pass. That is a silent false negative on the very gate that catches the
v115..v117 wedge -- worse than whatever the format change was meant to fix.

On 2026-11-27 a wall-clock stamp was added to this line to make refusals correlatable
with Mlog camera traffic (Clog carries no timestamps, which is what blocks defect A).
Placing it first broke both parsers; it now goes last. This test pins the invariant so
the next person to touch the format finds out here rather than in a green gate.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOADER = ROOT / "container" / "stage2_loader.c"
PROBE = ROOT / "scripts" / "probe-config-gate.py"
STRESS = ROOT / "scripts" / "stress-config-gate.py"


def _refusal_format() -> str:
    """The fprintf format string for the refusal line, concatenated across literals.

    Scans only the run of adjacent string literals that C would concatenate. Stopping
    at the first non-literal matters: collecting every quoted string after the marker
    would pull in unrelated messages from the rest of the file and make these
    assertions pass on nonsense.
    """
    text = LOADER.read_text(encoding="utf-8")
    marker = 'fprintf(stderr, "[stage2] camera admission refused:'
    idx = text.find(marker)
    assert idx != -1, "refusal fprintf not found in stage2_loader.c"

    i = text.index('"', idx)          # opening quote of the first literal
    parts = []
    while i < len(text):
        if text[i] != '"':
            break                     # end of the adjacent-literal run
        j = i + 1
        buf = []
        while j < len(text):
            if text[j] == "\\":       # skip an escaped character
                buf.append(text[j:j + 2])
                j += 2
                continue
            if text[j] == '"':
                break
            buf.append(text[j])
            j += 1
        assert j < len(text), "unterminated string literal"
        parts.append("".join(buf))
        i = j + 1
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
    assert parts, "no format literal after the refusal marker"
    return "".join(parts)


def test_site_and_kind_follow_refused_contiguously():
    fmt = _refusal_format()
    assert "admission refused: site=%x kind=%u " in fmt, (
        "a field was inserted between 'admission refused:' and 'site='; "
        "probe-config-gate.py and stress-config-gate.py match that literal prefix "
        "and would silently report zero refusals"
    )


def test_owner_fields_keep_their_relative_order():
    fmt = _refusal_format()
    order = ["owner_site=%x", "last_owner_kind=%u", "generation=%u"]
    positions = [fmt.find(o) for o in order]
    assert all(p != -1 for p in positions), f"missing fields: {[o for o, p in zip(order, positions) if p == -1]}"
    assert positions == sorted(positions), "owner_site/last_owner_kind/generation reordered; probe regex expects this order"


def _parser_regexes():
    """Pull the real REFUSE_RE patterns out of both tools rather than restating them."""
    out = {}
    for name, path in (("probe", PROBE), ("stress", STRESS)):
        src = path.read_text(encoding="utf-8")
        m = re.search(r"REFUSE_RE\s*=\s*re\.compile\((.*?)\)\n", src, re.S)
        assert m, f"{name}: could not locate REFUSE_RE"
        body = m.group(1).strip()
        # The pattern is one or more adjacent quoted fragments.
        frags = re.findall(r'r?"((?:[^"\\]|\\.)*)"', body)
        assert frags, f"{name}: could not extract pattern text"
        out[name] = re.compile("".join(frags))
    return out


def test_both_gate_probes_match_a_real_refusal_line():
    """Build a line the way the C code would and confirm both parsers still match."""
    fmt = _refusal_format()
    # Substitute plausible values for each conversion in order.
    subs = iter(["100540", "2", "100540", "3", "1", "1", "500", "1192", "649", "1", "4080", "0", "04:47:28"])
    line = "[stage2] " + re.sub(r"%[-#0-9.]*[a-zA-Z]", lambda m: str(next(subs)), fmt).rstrip("\n")

    for name, rx in _parser_regexes().items():
        assert rx.search(line), (
            f"{name} no longer matches a refusal line:\n  {line}\n"
            "a probe that matches nothing reports zero refusals as a pass"
        )


def test_timestamp_field_is_present_and_last():
    fmt = _refusal_format()
    assert "t=%s" in fmt, "wall-clock stamp removed; refusals cannot be aligned with Mlog traffic"
    # Must come after stolen= so the parsers' prefixes stay intact.
    assert fmt.find("t=%s") > fmt.find("stolen=%u"), "t= must trail stolen= to keep parser prefixes contiguous"
