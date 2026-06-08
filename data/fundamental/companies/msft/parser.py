"""Microsoft press release parser.

MSFT embeds all financials (income statement, segments, non-GAAP) in a single
press release HTML/PDF. There is no separate financial_tables.pdf.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ...base.parser import BasePressReleaseParser, BaseFinancialTablesParser


class MsftPressReleaseParser(BasePressReleaseParser):
    GAAP_HEADER = "Financial Statements"
    NON_GAAP_HEADER = "Non-GAAP Financial Measures"

    # Alternative headers across different quarters
    _GAAP_ALTERNATES = [
        "Financial Statements",
        "INCOME STATEMENTS",
        "Consolidated Statements of Income",
        "Results of Operations",
    ]
    _NON_GAAP_ALTERNATES = [
        "Non-GAAP Financial Measures",
        "Non-GAAP Measures",
        "Adjusted Financial Measures",
    ]
    _SEGMENT_HEADERS = [
        "Segment Revenue and Operating Income",
        "SEGMENT REVENUE AND OPERATING INCOME",
        "Revenue and operating income",
    ]

    def parse(self, pdf_path: Path) -> dict[str, pd.DataFrame]:
        if not pdf_path.exists():
            return {}
        try:
            import fitz
        except ImportError:
            import pymupdf as fitz  # type: ignore
        doc = fitz.open(str(pdf_path))

        # Try all alternate headers for GAAP and Non-GAAP
        all_targets: dict[str, str] = {}
        for i, h in enumerate(self._GAAP_ALTERNATES):
            all_targets[f"gaap_{i}"] = h
        for i, h in enumerate(self._NON_GAAP_ALTERNATES):
            all_targets[f"non_gaap_{i}"] = h
        for i, h in enumerate(self._SEGMENT_HEADERS):
            all_targets[f"segment_{i}"] = h

        best = self._find_best_headers(doc, all_targets)
        result: dict[str, pd.DataFrame] = {}

        # Pick the best match across each group
        for prefix in ("gaap", "non_gaap", "segment"):
            group_hits = {k: v for k, v in best.items() if k.startswith(f"{prefix}_")}
            if group_hits:
                best_key = max(group_hits, key=lambda k: group_hits[k][0])
                _, page_idx, header_bottom = group_hits[best_key]
                df = self._extract_table_below_header(doc, page_idx, header_bottom)
                if df is not None:
                    result[prefix] = df

        return result


class MsftFinancialTablesParser(BaseFinancialTablesParser):
    """No separate financial_tables.pdf for MSFT — parse() always returns empty."""

    PAGE_SECTION_KEYS: dict[str, list[str]] = {}

    def parse(self, pdf_path: Path) -> dict[str, pd.DataFrame]:
        return {}
