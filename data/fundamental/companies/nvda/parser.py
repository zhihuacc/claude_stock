"""NVIDIA press release and financial tables parsers.

Press release source: nvidianews.nvidia.com press_release.pdf (preferred)
Fallback:            EDGAR press_release.html (legacy)

Returns DataFrames with integer column indices:
  col=0 → current quarter
  col=1 → sequential prior quarter (summaries) or YoY (IS)
  col=2 → year-over-year prior (summaries, if present)
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from ...base.parser import BasePressReleaseParser, BaseFinancialTablesParser

# Cell values to skip when extracting numeric values
_SKIP = frozenset({"$", "%", "—", "–", "—", "–", "*", "**", ""})

_MONTHS = frozenset(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"]
)

class _NvdaPdfHelper(BaseFinancialTablesParser):
    """Word-position PDF parser for NVDA press release sections."""

    PAGE_SECTION_KEYS: dict[str, list[str]] = {
        "income_statement":   ["STATEMENTS OF INCOME", "STATEMENTS OF OPERATIONS"],
        "balance_sheet":      ["BALANCE SHEETS"],
        "cash_flow":          ["STATEMENTS OF CASH FLOWS"],
        "reconciliation":     ["RECONCILIATION OF GAAP TO NON-GAAP"],
        "segment_reportable": ["REVENUE BY REPORTABLE SEGMENT"],
        "segment_market":     ["REVENUE BY MARKET PLATFORM"],
        "free_cash_flow":     ["FREE CASH FLOW"],
    }

    def parse(self, pdf_path: Path) -> dict[str, pd.DataFrame]:
        if not pdf_path.exists():
            return {}
        result = self._parse_pdf(pdf_path)
        # Also search for GAAP/Non-GAAP quarterly summary tables via fuzzy header
        # matching (they use "Q1 FY27" column headers, not date strings).
        try:
            import fitz
        except ImportError:
            import pymupdf as fitz  # type: ignore[no-redef]
        doc = fitz.open(str(pdf_path))
        _finder = _SummaryFinder()
        for key, target in [("gaap", "GAAP Quarterly Financial Results"),
                             ("non_gaap", "Non-GAAP Quarterly Financial Results")]:
            if key in result:
                continue
            best = _finder._find_best_headers(doc, {key: target})
            if key in best:
                _, page_idx, header_bottom = best[key]
                df = _finder._extract_table_below_header(doc, page_idx, header_bottom)
                if df is not None and not df.empty:
                    result[key] = df.rename(columns={c: i for i, c in enumerate(df.columns)})
        return result


class _SummaryFinder(BasePressReleaseParser):
    """Minimal concrete subclass used only for the GAAP/Non-GAAP header search."""

    def parse(self, pdf_path: Path) -> dict[str, pd.DataFrame]:  # pragma: no cover
        return {}


_PDF_HELPER = _NvdaPdfHelper()


def _parse_pdf_nvda(pdf_path: Path) -> dict[str, pd.DataFrame]:
    return _PDF_HELPER.parse(pdf_path)


# ---------------------------------------------------------------------------
# Core HTML table parser (legacy EDGAR support)
# ---------------------------------------------------------------------------

def _expand_colspan(table_elem) -> list[list[str]]:
    """Expand each <tr> into a flat list of strings, repeating colspan cells."""
    rows = []
    for tr in table_elem.find_all("tr"):
        row: list[str] = []
        for td in tr.find_all(["td", "th"]):
            text = td.get_text(strip=True)
            cs = int(td.get("colspan", 1))
            row.extend([text] * cs)
        rows.append(row)
    if not rows:
        return []
    max_len = max(len(r) for r in rows)
    return [r + [""] * (max_len - len(r)) for r in rows]


def _first_val(row: list[str], start: int) -> str:
    """Return first non-skip value at or after position start (within +5 cells)."""
    for j in range(start, min(start + 6, len(row))):
        v = row[j]
        if v and v not in _SKIP:
            return v
    return ""


def _parse_nvda_table(table_elem) -> pd.DataFrame | None:
    """Convert an NVDA HTML <table> to a DataFrame."""
    rows = _expand_colspan(table_elem)
    if not rows:
        return None

    header_idx: int = -1
    col_positions: list[int] = []

    for i, row in enumerate(rows):
        fq_pos: list[int] = []
        seen_fq: set[str] = set()
        for j, v in enumerate(row):
            if re.match(r"Q[1-4]\s+FY\d{2}", v) and v not in seen_fq:
                fq_pos.append(j)
                seen_fq.add(v)
        if len(fq_pos) >= 2:
            header_idx = i
            col_positions = fq_pos[:3]
            break

        month_pos: list[int] = []
        seen_month: set[str] = set()
        for j, v in enumerate(row):
            if any(v.startswith(m) for m in _MONTHS) and v not in seen_month:
                month_pos.append(j)
                seen_month.add(v)
        if len(month_pos) >= 1:
            full_date_pos = [j for j in month_pos if re.search(r"20\d{2}", row[j])]
            if full_date_pos:
                header_idx = i
                col_positions = full_date_pos[:3]
                break
            for yr_offset in (1, 2):
                if i + yr_offset >= len(rows):
                    break
                year_row = rows[i + yr_offset]
                year_pos = [j for j in month_pos if re.match(r"20\d{2}", year_row[j])]
                if year_pos:
                    header_idx = i + yr_offset
                    col_positions = year_pos[:3]
                    break
            if col_positions:
                break

    if header_idx == -1 or not col_positions:
        return None

    label_bound = col_positions[0]
    records: list[tuple[str, list[str]]] = []

    for row in rows[header_idx + 1:]:
        label = ""
        for j in range(label_bound):
            v = row[j]
            if v and v not in _SKIP:
                label = v
                break
        if not label:
            continue

        label = re.sub(r"\s*\([A-Z]\)\s*$", "", label).rstrip("*").strip()
        if not label:
            continue

        vals = [_first_val(row, p) for p in col_positions]
        if any(vals):
            records.append((label, vals))

    if not records:
        return None

    n_cols = len(col_positions)
    index = [r[0] for r in records]
    data = {i: [r[1][i] if i < len(r[1]) else "" for r in records] for i in range(n_cols)}
    return pd.DataFrame(data, index=index)


def _table_title(table_elem) -> str:
    parts: list[str] = []
    for tr in table_elem.find_all("tr"):
        text = " ".join(
            td.get_text(strip=True)
            for td in tr.find_all(["td", "th"])
            if td.get_text(strip=True)
        ).strip()
        if not text:
            continue
        if re.search(r"\d", text) and not re.search(
            r"(STATEMENT|BALANCE|CASH FLOW|RECONCILIATION|REVENUE BY|GAAP|NON-GAAP|FISCAL|QUARTER|UNAUDITED)",
            text, re.IGNORECASE,
        ):
            break
        parts.append(text)
        if len(parts) >= 4:
            break
    return " ".join(parts)


def _classify_and_parse_tables(tables) -> dict[str, pd.DataFrame]:
    """Parse all HTML tables, classifying each by its embedded title."""
    result: dict[str, pd.DataFrame] = {}

    for table_elem in tables:
        df = _parse_nvda_table(table_elem)
        if df is None or df.empty:
            continue

        title = _table_title(table_elem).upper()

        if "RECONCILIATION OF GAAP TO NON-GAAP" in title:
            if "reconciliation" not in result:
                result["reconciliation"] = df
        elif "STATEMENTS OF INCOME" in title or "STATEMENTS OF OPERATIONS" in title:
            result["income_statement"] = df
        elif "BALANCE SHEET" in title:
            result["balance_sheet"] = df
        elif "STATEMENTS OF CASH FLOWS" in title or "CASH FLOWS" in title:
            if "cash_flow" not in result:
                result["cash_flow"] = df
            else:
                result["cash_flow"] = pd.concat([result["cash_flow"], df])
        elif "REVENUE BY REPORTABLE SEGMENT" in title:
            result["segment_reportable"] = df
        elif "REVENUE BY MARKET PLATFORM" in title:
            result["segment_market"] = df
        elif "NON-GAAP" in title or "NON GAAP" in title:
            if "non_gaap" not in result:
                result["non_gaap"] = df
        elif "GAAP" in title:
            if "gaap" not in result:
                result["gaap"] = df
        elif "THREE MONTHS ENDED" in title or "NINE MONTHS ENDED" in title:
            idx_upper = " ".join(str(x) for x in df.index).upper()
            if "OPERATING ACTIVITIES" in idx_upper or "FREE CASH FLOW" in idx_upper:
                if "free_cash_flow" not in result:
                    result["free_cash_flow"] = df
            elif "income_statement" not in result:
                result["income_statement"] = df
        else:
            if "gaap" not in result:
                result["gaap"] = df
            elif "non_gaap" not in result:
                result["non_gaap"] = df

    return result


# ---------------------------------------------------------------------------
# Parser classes
# ---------------------------------------------------------------------------

class NvdaPressReleaseParser(BasePressReleaseParser):
    """Parses NVDA quarterly earnings data.

    Tries press_release.pdf first (nvidianews source), falls back to
    press_release.html (legacy EDGAR source).

    Returns keys: gaap, non_gaap, income_statement, balance_sheet,
                  cash_flow, reconciliation, segment_reportable, segment_market
    """

    def parse(self, pdf_path: Path) -> dict[str, pd.DataFrame]:
        if pdf_path.exists():
            result = _parse_pdf_nvda(pdf_path)
            if result:
                return result
        html_path = pdf_path.with_suffix(".html")
        if html_path.exists():
            return self._parse_html(html_path)
        return {}

    def _parse_html(self, path: Path) -> dict[str, pd.DataFrame]:
        try:
            soup = BeautifulSoup(path.read_bytes(), "html.parser")
        except Exception as exc:
            print(f"  Warning: could not parse {path.name}: {exc}")
            return {}
        return _classify_and_parse_tables(soup.find_all("table"))


class NvdaFinancialTablesParser(BaseFinancialTablesParser):
    """Parses NVDA segment data.

    Tries cfo_commentary.html (legacy EDGAR source).
    Returns keys: gaap, non_gaap, segment_reportable, segment_market,
                  reconciliation (if present)
    """

    PAGE_SECTION_KEYS: dict = {}

    def parse(self, pdf_path: Path) -> dict[str, pd.DataFrame]:
        cfo_path = pdf_path.parent / "cfo_commentary.html"
        if cfo_path.exists():
            return self._parse_html(cfo_path)
        return {}

    def _parse_html(self, path: Path) -> dict[str, pd.DataFrame]:
        try:
            soup = BeautifulSoup(path.read_bytes(), "html.parser")
        except Exception as exc:
            print(f"  Warning: could not parse {path.name}: {exc}")
            return {}
        return _classify_and_parse_tables(soup.find_all("table"))
