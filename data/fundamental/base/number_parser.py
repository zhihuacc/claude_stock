"""Financial number string parsing utilities shared by all company parsers."""


def parse_number(s: str | None) -> float | None:
    """Parse a financial string to float.

    '10,253' → 10253.0
    '(37)'   → -37.0
    '53%'    → 53.0   (raw; callers decide whether to /100)
    '$1.79'  → 1.79
    '—'/''   → None
    """
    if s is None:
        return None
    s = str(s).strip()
    if s in ("", "-", "—", "–", "N/A", "Flat", "nm", "NM", "n/a"):
        return None
    s = s.replace("$", "").replace("%", "").replace(",", "").strip()
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def parse_percent(s: str | None) -> float | None:
    """Parse a percentage string to a 0-1 float.

    '44%'  → 0.44
    '44'   → 0.44   (bare number assumed to be percentage points)
    '0.44' → 0.44   (already a ratio; returned unchanged)
    '—'    → None
    """
    raw = parse_number(s)
    if raw is None:
        return None
    # If the original string contained "%" or the value is > 1, treat as percentage points.
    # Values like 0.44 (already a ratio) are returned as-is.
    if s is not None and "%" in str(s):
        return raw / 100.0
    # Bare numbers: if they look like percentage points (abs > 1), divide by 100.
    if abs(raw) > 1:
        return raw / 100.0
    return raw
