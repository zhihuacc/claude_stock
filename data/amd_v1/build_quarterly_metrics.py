#!/usr/bin/env python3
"""
Build a wide per-quarter DataFrame from AMD financial_tables.pdf files.

    python build_quarterly_metrics.py [--no-check] [--out FILE]

Rows    = fiscal quarters (2020-Q1 … latest), indexed by quarter label
Columns = financial metrics extracted from financial_tables.pdf

Cross-check: for each file the parser returns current-quarter (col 0) and
prior-quarter (col 1) values.  We verify that col-1 from file N matches
col-0 from file N-1 for key metrics — no press_release.pdf dependency.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Module imports
# ---------------------------------------------------------------------------

AMD_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(AMD_DIR))

from financial_tables_parser import extract_financial_tables           # noqa: E402


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _parse_number(s: str | None) -> float | None:
    """Parse a financial string ('10,253', '(37)', '53%', '0.84', '$1.79') → float."""
    if s is None:
        return None
    s = str(s).strip()
    if s in ("", "-", "—", "N/A", "Flat", "nm"):
        return None
    s = s.replace("$", "").replace("%", "").replace(",", "").strip()
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def _resolve_metric(index: pd.Index, metric: str, cutoff: float = 0.82) -> str | None:
    """
    Find the best matching name in `index` for `metric`.

    Strategy:
      1. Exact match
      2. Case-insensitive match  (e.g. "Net Income" → "Net income")
      3. Fuzzy match via difflib (e.g. "Operating income" → "Operating income (loss)")
         — but only within the same '%' group to avoid confusing dollar and percent metrics.

    Returns the resolved index name, or None if no acceptable match found.
    """
    # 1. Exact
    if metric in index:
        return metric

    unique: list[str] = list(dict.fromkeys(index))   # deduplicated, order-preserving

    # 2. Case-insensitive
    metric_lower = metric.lower()
    for name in unique:
        if name.lower() == metric_lower:
            return name

    # 3. Fuzzy — never cross the '%' boundary (dollar vs. percentage metrics)
    search_has_pct = "%" in metric
    candidates = [n for n in unique if ("%" in n) == search_has_pct]
    matches = difflib.get_close_matches(metric, candidates, n=1, cutoff=cutoff)
    return matches[0] if matches else None


def _get(
    df: pd.DataFrame | None,
    metric: str,
    occurrence: int = 0,
    col: int = 0,
) -> str | None:
    """
    Return the value for `metric` from `df`.

    Uses exact → case-insensitive → fuzzy matching via `_resolve_metric`.
    `occurrence` selects among duplicate index entries (0 = first).
    `col`        selects the column (0 = leftmost; used for the two-column EPS table).
    Returns None when metric, df, or column is absent.
    """
    if df is None or df.empty:
        return None
    if col >= len(df.columns):
        return None

    resolved = _resolve_metric(df.index, metric)
    if resolved is None:
        return None

    rows = df.loc[[resolved]]        # list-wrap keeps result as DataFrame
    if len(rows) <= occurrence:
        return None
    val = str(rows.iloc[occurrence, col]).strip()
    return val if val not in ("", "None") else None


# ---------------------------------------------------------------------------
# Metric extraction
# ---------------------------------------------------------------------------

def _extract_metrics(tables: dict, col: int, quarter: str) -> dict:
    """
    Extract all financial metrics from `tables` using column index `col`.

    col=0 → current quarter (leftmost column in each table)
    col=1 → prior quarter  (second column; EPS table uses col*2 / col*2+1)
    """
    rec: dict[str, str | None] = {"quarter": quarter}

    # ── GAAP Income Statement ────────────────────────────────────────────────
    is_ = tables.get("income_statement")
    rec["gaap_revenue"]      = _get(is_, "Net revenue", col=col)
    # "Gross margin" (dollar) in 2020; "Gross profit" everywhere else.
    # Parser now renames "Gross margin" to "Gross margin %" when the value contains "%",
    # so a plain "Gross margin" lookup is always the dollar-amount row.
    rec["gaap_gross_profit"] = _get(is_, "Gross profit", col=col) or _get(is_, "Gross margin", col=col)
    # Fuzzy _get handles both "Gross margin %" (explicit label) and the renamed variant.
    rec["gaap_gross_margin"] = _get(is_, "Gross margin %", col=col)
    rec["gaap_research_development_expense"]    = _get(is_, "Research and development", col=col)
    rec["gaap_marketing_general_admin_expense"] = _get(is_, "Marketing, general and administrative", col=col)
    # Placeholder keeps this key adjacent to the other income-statement metrics in column order.
    # The value is filled below after gng is loaded; "GAAP operating expenses" from the
    # non-GAAP reconciliation table is present in all 25 quarters vs only 5 from the IS.
    rec["gaap_operating_expense"] = None
    # Fuzzy matching resolves "Operating income (loss)" when "Operating income" is absent.
    rec["gaap_operating_income"] = _get(is_, "Operating income", col=col)
    rec["gaap_interest_expense"] = _get(is_, "Interest expense", col=col)
    # Case-insensitive matching handles "Net Income"; explicit fallback for "(loss)" variant
    # because the short string length gives a ratio below the fuzzy cutoff.
    rec["gaap_net_income"] = (
        _get(is_, "Net income", col=col)
        or _get(is_, "Net income (loss)", col=col)
    )

    # EPS / share-count format changed over time:
    #   Newer: explicit "Diluted earnings per share" row, then "Basic"/"Diluted" for shares
    #   Older: "Basic"[0]/"Diluted"[0] = EPS, "Basic"[1]/"Diluted"[1] = shares
    has_eps_label = is_ is not None and "Diluted earnings per share" in is_.index
    if has_eps_label:
        rec["gaap_diluted_earnings_per_share"] = _get(is_, "Diluted earnings per share", col=col)
        rec["gaap_basic_shares"]               = _get(is_, "Basic",   occurrence=0, col=col)
        rec["gaap_diluted_shares"]             = _get(is_, "Diluted", occurrence=0, col=col)
    else:
        rec["gaap_diluted_earnings_per_share"] = _get(is_, "Diluted", occurrence=0, col=col)   # first = EPS
        rec["gaap_basic_shares"]               = _get(is_, "Basic",   occurrence=1, col=col)   # second = shares
        rec["gaap_diluted_shares"]             = _get(is_, "Diluted", occurrence=1, col=col)

    # ── Balance Sheet ────────────────────────────────────────────────────────
    bs = tables.get("balance_sheet")
    rec["gaap_cash"]                       = _get(bs, "Cash and cash equivalents", col=col)
    rec["gaap_short_term_investments"]     = _get(bs, "Short-term investments", col=col)
    rec["gaap_accounts_receivable"]        = _get(bs, "Accounts receivable, net", col=col)
    rec["gaap_inventories"]                = _get(bs, "Inventories", col=col)
    rec["gaap_total_current_assets"]       = _get(bs, "Total current assets", col=col)
    rec["gaap_total_assets"]               = _get(bs, "Total Assets", col=col)
    rec["gaap_total_current_liabilities"]  = _get(bs, "Total current liabilities", col=col)
    rec["gaap_long_term_debt"] = (
        _get(bs, "Long-term debt", col=col)
        or _get(bs, "Long-term debt, net", col=col)
        or _get(bs, "Long-term debt, net of current portion", col=col)
    )
    rec["gaap_stockholders_equity"]        = _get(bs, "Total stockholders' equity", col=col)

    # ── Cash Flow ─────────────────────────────────────────────────────────────
    cash_flow = tables.get("cash_flow")
    op_cash_flow_labels = [
        "Net cash provided by operating activities of continuing operations",
        "Net cash provided by operating activities",
        "Operating activities",    # pre-2022 summary format
    ]
    rec["gaap_operating_cash_flow"] = next(
        (v for label in op_cash_flow_labels if (v := _get(cash_flow, label, col=col)) is not None), None
    )
    rec["gaap_capital_expenditure"] = _get(cash_flow, "Purchases of property and equipment", col=col)

    # ── Segment Data ──────────────────────────────────────────────────────────
    segment = tables.get("segment_data")

    # "Data Center Segment" / "Embedded Segment" appear twice in the index:
    #   occurrence 0 → segment revenue
    #   occurrence 1 → segment operating income
    rec["datacenter_segment_revenue"]              = _get(segment, "Data Center Segment", occurrence=0, col=col)
    rec["client_segment_revenue"]                  = _get(segment, "Client", col=col)
    rec["gaming_segment_revenue"]                  = _get(segment, "Gaming", col=col)
    rec["embedded_segment_revenue"]                = _get(segment, "Embedded Segment", occurrence=0, col=col)
    rec["datacenter_segment_operating_income"]     = _get(segment, "Data Center Segment", occurrence=1, col=col)
    rec["client_gaming_segment_operating_income"]  = _get(segment, "Client and Gaming Segment", col=col)
    rec["embedded_segment_operating_income"]       = _get(segment, "Embedded Segment", occurrence=1, col=col)

    rec["adjusted_ebitda_segment"]            = _get(segment, "Adjusted EBITDA", col=col)
    rec["cash_and_short_term_investments"]    = (
        _get(segment, "Cash, cash equivalents and short-term investments", col=col)
        or _get(segment, "Cash, cash equivalents and marketable securities", col=col)
    )
    rec["free_cash_flow_segment"]  = _get(segment, "Free cash flow", col=col)
    rec["total_assets_segment"]    = _get(segment, "Total assets", col=col)
    rec["total_debt"]              = _get(segment, "Total debt", col=col)
    rec["capital_expenditure_segment"] = _get(segment, "Capital expenditures", col=col)

    # ── Adjusted EBITDA reconciliation ───────────────────────────────────────
    ebitda = tables.get("adjusted_ebitda")
    rec["adjusted_ebitda"] = _get(ebitda, "Adjusted EBITDA", col=col)

    # ── Free Cash Flow reconciliation ─────────────────────────────────────────
    free_cash_flow = tables.get("free_cash_flow")
    rec["free_cash_flow"]  = _get(free_cash_flow, "Free cash flow", col=col)
    # Label varies: "Operating cash flow margin % from continuing operations" (4 quarters)
    # vs "Operating cash flow margin %" (most quarters); fuzzy can't bridge the gap at 0.82,
    # so fall back explicitly.
    rec["operating_cash_flow_margin"] = (
        _get(free_cash_flow, "Operating cash flow margin % from continuing operations", col=col)
        or _get(free_cash_flow, "Operating cash flow margin %", col=col)
    )
    rec["free_cash_flow_margin"] = _get(free_cash_flow, "Free cash flow margin %", col=col)

    # ── GAAP → Non-GAAP (gross profit, opex, operating income) ───────────────
    gng = tables.get("gaap_to_non_gaap")
    # gaap_operating_expense: "GAAP operating expenses" in the non-GAAP reconciliation table
    # is present in all 25 quarters; income statement "Total operating expenses" only in last 5.
    rec["gaap_operating_expense"] = (
        _get(gng, "GAAP operating expenses", col=col)
        or _get(is_, "Total operating expenses", col=col)
    )
    rec["non_gaap_gross_profit"]     = _get(gng, "Non-GAAP gross profit", col=col)
    # Parser now renames percentage-valued "Non-GAAP gross margin" to "Non-GAAP gross margin %",
    # making the lookup key consistent across all quarters.
    rec["non_gaap_gross_margin"]              = _get(gng, "Non-GAAP gross margin %", col=col)
    rec["non_gaap_operating_expense"]         = _get(gng, "Non-GAAP operating expenses", col=col)
    # Fuzzy matching handles "Non-GAAP operating expenses/revenue%" (no space before %).
    rec["non_gaap_operating_expense_margin"]  = _get(gng, "Non-GAAP operating expenses/revenue %", col=col)
    rec["non_gaap_operating_income"]          = _get(gng, "Non-GAAP operating income", col=col)
    # Same fix as gross_margin: look for the "%" suffixed label.
    rec["non_gaap_operating_margin"]          = _get(gng, "Non-GAAP operating margin %", col=col)

    # ── Non-GAAP EPS table (two columns per period: Amt | EPS) ───────────────
    # col=0 → period 0: columns 0 (Amt) and 1 (EPS)
    # col=1 → period 1: columns 2 (Amt) and 3 (EPS)
    eps = tables.get("gaap_to_non_gaap_eps")
    # Fuzzy matching handles the "diluted earnings per share" variant (2 quarters).
    nongaap_row = "Non-GAAP net income / earnings per share"
    eps_amt_col = col * 2
    eps_eps_col = col * 2 + 1
    if eps is not None and not eps.empty and _resolve_metric(eps.index, nongaap_row) is not None:
        rec["non_gaap_net_income"]              = _get(eps, nongaap_row, col=eps_amt_col)
        rec["non_gaap_diluted_earnings_per_share"] = _get(eps, nongaap_row, col=eps_eps_col)
    else:
        rec["non_gaap_net_income"]              = None
        rec["non_gaap_diluted_earnings_per_share"] = None

    return rec


_MONTH_NUM: dict[str, int] = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}


def _col1_is_sequential(tables: dict) -> bool:
    """
    Return True when col 1 is the sequential prior quarter (~3 months before col 0),
    not a year-over-year comparison (~12 months before col 0).
    Uses actual date difference from column headers; returns False when undetermined.
    """
    is_ = tables.get("income_statement")
    if is_ is None or is_.empty or len(is_.columns) < 2:
        return False

    def _parse_col_date(name: str):
        m = re.match(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", name)
        if not m:
            return None
        month = _MONTH_NUM.get(m.group(1))
        if month is None:
            return None
        # Use a simple ordinal: year * 12 + month for approximate month difference
        return int(m.group(3)) * 12 + month

    col0_months = _parse_col_date(is_.columns[0])
    col1_months = _parse_col_date(is_.columns[1])
    if col0_months is None or col1_months is None:
        return False

    diff = col0_months - col1_months   # positive = col1 is in the past
    # Sequential prior quarter: ~3 months apart (allow 1–6 month window)
    # Year-over-year:           ~12 months apart
    return 1 <= diff <= 6


def extract_quarter_metrics(quarter: str) -> tuple[dict, dict, bool]:
    """
    Extract metrics for one quarter's financial_tables.pdf.

    Returns (current_metrics, prior_metrics, prior_is_sequential) where:
      current_metrics     → col 0 of each table (the reported quarter)
      prior_metrics       → col 1 of each table (comparison period)
      prior_is_sequential → True when col 1 is the sequential prior quarter,
                            False when it is a year-over-year comparison period
    """
    pdf = AMD_DIR / "reports" / quarter / "financial_tables.pdf"
    tables = extract_financial_tables(pdf)
    current       = _extract_metrics(tables, col=0, quarter=quarter)
    prior         = _extract_metrics(tables, col=1, quarter=quarter)
    is_sequential = _col1_is_sequential(tables)
    return current, prior, is_sequential


# ---------------------------------------------------------------------------
# Cross-check: prior-quarter col from file N vs current-quarter col from file N-1
# ---------------------------------------------------------------------------

_CROSS_CHECK_KEYS: list[tuple[str, str]] = [
    # (metrics_key,                             label)
    ("gaap_revenue",                            "GAAP Revenue"),
    ("gaap_gross_profit",                       "GAAP Gross Profit"),
    ("gaap_operating_income",                   "GAAP Operating Income"),
    ("gaap_net_income",                         "GAAP Net Income"),
    ("gaap_diluted_earnings_per_share",         "GAAP Diluted EPS"),
    ("non_gaap_gross_profit",                   "Non-GAAP Gross Profit"),
    ("non_gaap_operating_income",               "Non-GAAP Operating Income"),
    ("non_gaap_net_income",                     "Non-GAAP Net Income"),
    ("non_gaap_diluted_earnings_per_share",     "Non-GAAP Diluted EPS"),
]

_TOLERANCE = 0.005   # 0.5 % relative tolerance


def cross_check(quarter: str, prior_in_current: dict, prev_current: dict) -> list[str]:
    """
    Compare prior-quarter values extracted from `quarter`'s file (col 1)
    against current-quarter values extracted from the preceding file (col 0).

    Returns a list of human-readable mismatch strings (empty = all OK).
    """
    mismatches: list[str] = []
    for key, label in _CROSS_CHECK_KEYS:
        val_prior   = _parse_number(prior_in_current.get(key))   # col 1 from file N
        val_current = _parse_number(prev_current.get(key))       # col 0 from file N-1

        if val_prior is None or val_current is None:
            continue

        denom = max(abs(val_current), 1e-9)
        if abs(val_current) < 10:
            ok = abs(val_prior - val_current) < 0.015   # ±$0.015 for EPS
        else:
            ok = abs(val_prior - val_current) / denom < _TOLERANCE

        if not ok:
            mismatches.append(
                f"  [{quarter}] {label}: prior_col={val_prior} "
                f"vs prev_current={val_current} "
                f"(diff {abs(val_prior - val_current):.2f})"
            )

    return mismatches


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_dataframe(run_check: bool = True) -> pd.DataFrame:
    reports_dir = AMD_DIR / "reports"
    quarters = sorted(p.name for p in reports_dir.iterdir() if p.is_dir())

    records: list[dict] = []
    all_mismatches: list[str] = []

    prev_current: dict | None = None   # col-0 metrics from the previous quarter's file

    for q in quarters:
        print(f"  {q} … ", end="", flush=True)
        try:
            current, prior, is_sequential = extract_quarter_metrics(q)
            records.append(current)

            if run_check and prev_current is not None:
                if is_sequential:
                    mm = cross_check(q, prior, prev_current)
                    all_mismatches.extend(mm)
                    print("OK" if not mm else f"{len(mm)} mismatch(es)")
                else:
                    # col 1 is a year-over-year comparison period, not sequential —
                    # skip cross-check to avoid false mismatches (e.g. 2022 Xilinx era)
                    print("OK (YoY col, cross-check skipped)")
            else:
                print("OK")

            prev_current = current

        except Exception as exc:
            print(f"ERROR: {exc}")
            prev_current = None   # gap in the chain; reset

    df = pd.DataFrame(records).set_index("quarter")

    if all_mismatches:
        print(f"\n{'='*60}")
        print(f"Cross-check mismatches ({len(all_mismatches)} total):")
        for m in all_mismatches:
            print(m)
    else:
        print("\nAll cross-checks passed.")

    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-check", action="store_true",
                        help="skip inter-file cross-check")
    parser.add_argument("--out", default="quarterly_metrics.csv",
                        help="output CSV path (default: quarterly_metrics.csv)")
    args = parser.parse_args()

    print("Extracting quarterly metrics …")
    df = build_dataframe(run_check=not args.no_check)

    out = Path(args.out)
    df.to_csv(out)
    print(f"\nSaved {len(df)} quarters × {len(df.columns)} metrics → {out}")
    print(f"\nColumn list:\n{list(df.columns)}")


if __name__ == "__main__":
    main()
