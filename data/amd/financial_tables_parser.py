"""Parse financial_tables.pdf into structured DataFrames using word-position analysis.

Strategy: use get_text("words") to get per-word x/y positions, group words into visual
rows with greedy merging (max_gap=4 pts handles within-row baseline variation), cluster
value x-positions into columns, and extract date column names from header rows.
"""

import re
from collections import defaultdict
from pathlib import Path

import fitz
import pandas as pd

MONTH_NAMES = frozenset([
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
])

# Keywords used to classify pages
_PAGE_SECTION_KEYS: dict[str, list[str]] = {
    "income_statement": ["STATEMENTS OF OPERATIONS"],
    "balance_sheet":    ["BALANCE SHEETS"],
    "cash_flow":        ["STATEMENTS OF CASH FLOWS", "SELECTED CASH FLOW INFORMATION"],
    "segment_data":     ["SELECTED CORPORATE DATA"],
    "gaap_to_non_gaap": ["RECONCILIATION OF GAAP TO NON-GAAP"],
}


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _group_into_rows(words: list, max_gap: float = 4.0) -> list[tuple[float, list]]:
    """
    Group word tuples into visual rows via greedy merging.
    Words whose y0 is within max_gap pts of the current row anchor are merged.
    Returns list of (anchor_y, [(x0, text), ...]) sorted by anchor_y.
    """
    data = sorted((y0, x0, text) for x0, y0, x1, y1, text, *_ in words)
    if not data:
        return []

    rows: list[tuple[float, list]] = []
    anchor_y, *_ = data[0]
    current: list[tuple[float, float, str]] = [data[0]]

    for y0, x0, text in data[1:]:
        if y0 - anchor_y <= max_gap:
            current.append((y0, x0, text))
        else:
            rows.append((anchor_y, sorted((x, t) for _, x, t in current)))
            anchor_y = y0
            current = [(y0, x0, text)]

    rows.append((anchor_y, sorted((x, t) for _, x, t in current)))
    return rows


def _is_financial_value(text: str) -> bool:
    """True if text is a financial number, percentage, or dash placeholder."""
    t = text.strip()
    if t in ("$", "—", ""):
        return False
    # Matches: 10,253  (37)  50%  0.84  -  (0.07)  3,158  83%
    return bool(re.match(r"^-$|^\(?[\d,]+\.?\d*\)?%?$", t))


def _cluster_xs(xs: list[float], gap: float = 25.0) -> list[float]:
    """Return sorted list of cluster-centre x positions."""
    if not xs:
        return []
    sorted_xs = sorted(set(round(x, 1) for x in xs))
    clusters: list[list[float]] = [[sorted_xs[0]]]
    for x in sorted_xs[1:]:
        if x - clusters[-1][-1] < gap:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    return [sum(c) / len(c) for c in clusters]


def _is_date_token(text: str) -> bool:
    """True if text is a month name, day number ('26,'), or 4-digit year."""
    return (
        text in MONTH_NAMES
        or bool(re.match(r"^\d{1,2},$", text))   # "26,"  "28,"
        or bool(re.match(r"^\d{4}$", text))       # "2022"  "2026"
    )


# ---------------------------------------------------------------------------
# Column name extraction
# ---------------------------------------------------------------------------

def _extract_col_names(
    rows: list,
    header_row_indices: list[int],
    col_xs: list[float],
) -> list[str]:
    """
    Extract column date labels from header rows and map them to col_xs.

    Month names are range-partitioned: each month anchor owns all date tokens
    between its x and the next month anchor's x. This handles compact layouts
    where inter-column gaps are smaller than intra-date token spreads.

    For EPS reconciliation tables where len(col_xs) == 2 × N_date_headers, columns
    are labelled "<date> Amt" / "<date> EPS" alternately.
    """
    if not col_xs:
        return []

    # Collect (x, y, text) for every date token in header rows
    date_tokens: list[tuple[float, float, str]] = []
    for i in header_row_indices:
        y, ws = rows[i]
        for x, t in ws:
            if _is_date_token(t):
                date_tokens.append((x, y, t))

    if not date_tokens:
        return [f"Col_{i}" for i in range(len(col_xs))]

    # Range-based partitioning: each month anchor owns tokens up to the next anchor
    month_anchors = sorted((x, y, t) for x, y, t in date_tokens if t in MONTH_NAMES)
    if month_anchors:
        date_clusters: list[list[tuple[float, float, str]]] = []
        for idx, (mx, my, mt) in enumerate(month_anchors):
            upper = month_anchors[idx + 1][0] if idx + 1 < len(month_anchors) else float("inf")
            cluster = [(x, y, t) for x, y, t in date_tokens if mx <= x < upper]
            date_clusters.append(cluster)
    else:
        # Fallback: proximity clustering (gap=30 pts)
        date_tokens_sorted = sorted(date_tokens)
        date_clusters = [[date_tokens_sorted[0]]]
        for item in date_tokens_sorted[1:]:
            if item[0] - date_clusters[-1][-1][0] < 30:
                date_clusters[-1].append(item)
            else:
                date_clusters.append([item])

    def _build_date_str(cluster: list[tuple[float, float, str]]) -> str:
        months = [t for _, _, t in cluster if t in MONTH_NAMES]
        days = [t for _, _, t in cluster if re.match(r"^\d{1,2},$", t)]
        years = [t for _, _, t in cluster if re.match(r"^\d{4}$", t)]
        return " ".join(months[:1] + days[:1] + years[:1])

    n_clusters = len(date_clusters)

    # Sort clusters left-to-right for positional pairing with col_xs
    clusters_sorted = sorted(date_clusters, key=lambda c: min(x for x, _, _ in c))

    # Detect EPS pattern: N date clusters but 2N value columns → alternate Amt/EPS
    if n_clusters > 0 and len(col_xs) == 2 * n_clusters:
        col_names: list[str] = []
        for cluster in clusters_sorted:
            date_str = _build_date_str(cluster)
            col_names.append(f"{date_str} Amt")
            col_names.append(f"{date_str} EPS")
        return col_names

    # Standard case: positional pairing (cluster i → col_xs[i])
    col_names = [f"Col_{i}" for i in range(len(col_xs))]
    for i, cluster in enumerate(clusters_sorted):
        if i < len(col_xs):
            col_names[i] = _build_date_str(cluster)
    return col_names


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

def _is_header_row(ws: list[tuple[float, str]]) -> bool:
    """True if a row looks like a date-header or 'Quarter Group' separator."""
    texts = [t for _, t in ws]
    return (
        any(t in MONTH_NAMES for t in texts)
        or any(re.match(r"^\d{4}$", t) for t in texts)
        or ("Quarter" in texts and "Group" in texts)
        or ("Quarter" in texts and "End" in texts)
    )


def _find_section_groups(rows: list) -> list[tuple[int, int]]:
    """
    Find groups of consecutive header rows (date headers / Quarter Group markers).
    Returns list of (first_row_idx, last_row_idx) for each header group.
    """
    header_indices = [i for i, (_, ws) in enumerate(rows) if _is_header_row(ws)]
    if not header_indices:
        return []

    groups: list[tuple[int, int]] = []
    group_start = header_indices[0]
    prev = header_indices[0]

    for idx in header_indices[1:]:
        if idx - prev <= 4:          # consecutive within 4 rows → same group
            prev = idx
        else:
            groups.append((group_start, prev))
            group_start = idx
            prev = idx
    groups.append((group_start, prev))
    return groups


# ---------------------------------------------------------------------------
# Section parser
# ---------------------------------------------------------------------------

def _parse_section(
    rows: list,
    col_xs: list[float],
    label_x_max: float,
    start_idx: int,
    end_idx: int,
    skip_indices: set[int],
    col_names: list[str],
) -> pd.DataFrame:
    """
    Parse rows[start_idx:end_idx+1] into a DataFrame.

    Label  = words with x < label_x_max that are not financial values or '$'.
    Values = words with x ≥ label_x_max that pass _is_financial_value(), assigned
             to the nearest column centre in col_xs.
    """
    records: list[list] = []

    for i in range(start_idx, min(end_idx + 1, len(rows))):
        if i in skip_indices:
            continue
        _, ws = rows[i]

        label_words = [
            (x, t) for x, t in ws
            if x < label_x_max and t != "$" and not _is_financial_value(t)
        ]
        value_words = [
            (x, t) for x, t in ws
            if x >= label_x_max and _is_financial_value(t)
        ]

        if not value_words:
            continue

        label = " ".join(t for _, t in sorted(label_words))
        if not label.strip():
            continue

        # Normalise labels that already end with "%" but have no space: "foo%" → "foo %"
        if label.endswith("%") and not label.endswith(" %"):
            label = label[:-1].rstrip() + " %"

        # If extracted values are percentages, reflect that in the label so that
        # "Gross margin" (value "47%") is stored as "Gross margin %" — distinct from
        # "Gross margin" whose value is a dollar amount (e.g. "818").
        # Skip labels that already contain "%" anywhere (e.g. "margin % from operations").
        if any("%" in t for _, t in value_words) and "%" not in label:
            label = label.rstrip() + " %"

        # Assign each value to the nearest column
        row_vals: dict[int, list[str]] = defaultdict(list)
        for x, t in value_words:
            col_idx = min(range(len(col_xs)), key=lambda i: abs(col_xs[i] - x))
            row_vals[col_idx].append(t)

        row = [label] + [" ".join(row_vals.get(i, [])) for i in range(len(col_xs))]
        records.append(row)

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records, columns=["Metric"] + col_names)
    return df.set_index("Metric")


# ---------------------------------------------------------------------------
# Page parser: detects sections, extracts col_xs, calls _parse_section
# ---------------------------------------------------------------------------

def _parse_page(page: fitz.Page) -> list[dict]:
    """
    Parse all columnar sections found on a page.
    Returns list of dicts: {"section_idx", "df", "col_xs", "col_names"}.
    """
    words = page.get_text("words")
    rows = _group_into_rows(words)
    header_groups = _find_section_groups(rows)

    if not header_groups:
        return []

    results: list[dict] = []

    for section_num, (hg_start, hg_end) in enumerate(header_groups):
        data_start_idx = hg_end + 1

        # Data ends just before the next header group, or at end of rows
        if section_num + 1 < len(header_groups):
            data_end_idx = header_groups[section_num + 1][0] - 1
        else:
            data_end_idx = len(rows) - 1

        if data_start_idx > data_end_idx:
            continue

        # Cluster value x-positions from data rows to find column centres
        value_xs: list[float] = []
        for i in range(data_start_idx, data_end_idx + 1):
            _, ws = rows[i]
            for x, t in ws:
                if _is_financial_value(t):
                    value_xs.append(x)

        col_xs = _cluster_xs(value_xs, gap=25)
        if not col_xs:
            continue

        # Filter out spurious clusters (footnote markers) using month anchor positions
        month_xs: list[float] = []
        for i in range(hg_start, hg_end + 1):
            _, ws = rows[i]
            for x, t in ws:
                if t in MONTH_NAMES:
                    month_xs.append(x)
        # Filter out spurious col_xs (footnote markers) that lie well to the
        # left of the real value columns.  Real value columns are always to the
        # right of their corresponding month-name anchor; spurious ones cluster
        # in the label area, left of the leftmost month anchor.
        if month_xs:
            left_bound = min(month_xs) - 30
            filtered = [cx for cx in col_xs if cx >= left_bound]
            if filtered:
                col_xs = filtered

        # Label boundary: 50 pts left of leftmost value column (clears the $ sign)
        label_x_max = min(col_xs) - 50

        # Extract column date names from the header group
        header_indices = list(range(hg_start, hg_end + 1))
        col_names = _extract_col_names(rows, header_indices, col_xs)

        # Parse data rows
        skip_indices = set(range(hg_start, hg_end + 1))
        df = _parse_section(
            rows, col_xs, label_x_max, data_start_idx, data_end_idx,
            skip_indices, col_names,
        )

        if not df.empty:
            results.append({
                "section_idx": section_num,
                "df": df,
                "col_xs": col_xs,
                "col_names": col_names,
            })

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_financial_tables(pdf_path: str | Path) -> dict[str, pd.DataFrame]:
    """
    Parse financial_tables.pdf and return a dict of DataFrames.

    Keys (present when the corresponding section is found):
        "income_statement"   – Condensed Consolidated Statements of Operations
        "balance_sheet"      – Condensed Consolidated Balance Sheets
        "cash_flow"          – Cash Flow Statement (or Selected Cash Flow Info)
        "segment_data"       – Selected Corporate Data (segment revenue / income)
        "gaap_to_non_gaap"   – GAAP-to-Non-GAAP upper section (gross profit / opex / opIncome)
        "gaap_to_non_gaap_eps" – Net income / EPS reconciliation (6-column EPS table)
        "adjusted_ebitda"    – Adjusted EBITDA reconciliation
        "free_cash_flow"     – Free Cash Flow reconciliation
    """
    doc = fitz.open(str(pdf_path))
    result: dict[str, pd.DataFrame] = {}

    for page in doc:
        text = page.get_text()
        sections = _parse_page(page)

        # ── Standard single-section pages ──────────────────────────────────
        if "STATEMENTS OF OPERATIONS" in text and "income_statement" not in result:
            if sections:
                result["income_statement"] = sections[0]["df"]

        elif "BALANCE SHEETS" in text and "balance_sheet" not in result:
            if sections:
                result["balance_sheet"] = sections[0]["df"]

        elif (
            ("STATEMENTS OF CASH FLOWS" in text or "SELECTED CASH FLOW INFORMATION" in text)
            and "cash_flow" not in result
        ):
            if sections:
                result["cash_flow"] = sections[0]["df"]

        elif "SELECTED CORPORATE DATA" in text and "segment_data" not in result:
            if sections:
                result["segment_data"] = sections[0]["df"]

        # ── Non-GAAP reconciliation page (1 or 2 sections) ─────────────────
        elif "RECONCILIATION OF GAAP TO NON-GAAP" in text:
            if len(sections) >= 1 and "gaap_to_non_gaap" not in result:
                result["gaap_to_non_gaap"] = sections[0]["df"]
            if len(sections) >= 2 and "gaap_to_non_gaap_eps" not in result:
                result["gaap_to_non_gaap_eps"] = sections[1]["df"]

        # ── EBITDA and FCF reconciliations (dedicated pages only) ─────────
        # Skip pages that are already claimed as segment_data to avoid duplicating
        # rows that appear as summary metrics within the SELECTED CORPORATE DATA table.
        if (
            "Adjusted EBITDA" in text
            and "adjusted_ebitda" not in result
            and "SELECTED CORPORATE DATA" not in text
        ):
            for s in sections:
                idx = s["df"].index
                if any("Adjusted EBITDA" in str(m) for m in idx):
                    result["adjusted_ebitda"] = s["df"]
                    break

        if (
            "Free cash flow" in text
            and "free_cash_flow" not in result
            and "SELECTED CORPORATE DATA" not in text
        ):
            for s in sections:
                idx = s["df"].index
                if any("Free cash flow" in str(m) for m in idx):
                    result["free_cash_flow"] = s["df"]
                    break

    # Keep the two most-recent periods (current + prior quarter).
    # EPS tables have two columns per period (Amt + EPS); all others have one.
    for key in list(result.keys()):
        df = result[key]
        if df.empty or not len(df.columns):
            continue
        first_col = df.columns[0]
        is_eps = (
            first_col.endswith(" Amt")
            and len(df.columns) > 1
            and df.columns[1].endswith(" EPS")
        )
        result[key] = df.iloc[:, :4] if is_eps else df.iloc[:, :2]

    return result


if __name__ == "__main__":
    import sys

    path = sys.argv[1]
    tables = extract_financial_tables(path)
    for name, df in tables.items():
        print(f"\n{'='*70}")
        print(f"  {name.upper()}")
        print("="*70)
        print(df.to_string())
