"""Google/Alphabet press release and financial tables parsers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ...base.parser import BasePressReleaseParser, BaseFinancialTablesParser


class GoogPressReleaseParser(BasePressReleaseParser):
    GAAP_HEADER = "CONSOLIDATED STATEMENTS OF INCOME"
    NON_GAAP_HEADER = "Non-GAAP Results"

    _GAAP_ALTERNATES = [
        "CONSOLIDATED STATEMENTS OF INCOME",
        "Consolidated Statements of Income",
        "CONDENSED CONSOLIDATED STATEMENTS OF INCOME",
        "Financial Results",
    ]
    _NON_GAAP_ALTERNATES = [
        "Non-GAAP Results",
        "Non-GAAP Financial Measures",
        "Reconciliation of GAAP Results",
    ]
    _SEGMENT_HEADERS = [
        "Revenues by Segment",
        "REVENUES BY SEGMENT",
        "Segment Information",
        "SEGMENT INFORMATION",
        "Revenues",
    ]

    def parse(self, pdf_path: Path) -> dict[str, pd.DataFrame]:
        if not pdf_path.exists():
            return {}
        try:
            import fitz
        except ImportError:
            import pymupdf as fitz  # type: ignore
        doc = fitz.open(str(pdf_path))

        all_targets: dict[str, str] = {}
        for i, h in enumerate(self._GAAP_ALTERNATES):
            all_targets[f"gaap_{i}"] = h
        for i, h in enumerate(self._NON_GAAP_ALTERNATES):
            all_targets[f"non_gaap_{i}"] = h
        for i, h in enumerate(self._SEGMENT_HEADERS):
            all_targets[f"segment_{i}"] = h

        best = self._find_best_headers(doc, all_targets)
        result: dict[str, pd.DataFrame] = {}

        for prefix in ("gaap", "non_gaap", "segment"):
            group_hits = {k: v for k, v in best.items() if k.startswith(f"{prefix}_")}
            if group_hits:
                best_key = max(group_hits, key=lambda k: group_hits[k][0])
                _, page_idx, header_bottom = group_hits[best_key]
                df = self._extract_table_below_header(doc, page_idx, header_bottom)
                if df is not None:
                    result[prefix] = df

        return result


class GoogFinancialTablesParser(BaseFinancialTablesParser):
    PAGE_SECTION_KEYS = {
        "income_statement": [
            "CONSOLIDATED STATEMENTS OF INCOME",
            "Consolidated Statements of Income",
        ],
        "balance_sheet": [
            "CONSOLIDATED BALANCE SHEETS",
            "Consolidated Balance Sheets",
        ],
        "cash_flow": [
            "CONSOLIDATED STATEMENTS OF CASH FLOWS",
            "Consolidated Statements of Cash Flows",
        ],
        "segment_data": [
            "Revenues by Segment",
            "REVENUES BY SEGMENT",
            "Segment Information",
        ],
    }

    def parse(self, pdf_path: Path) -> dict[str, pd.DataFrame]:
        if not pdf_path.exists():
            return {}
        return self._parse_pdf(pdf_path)
