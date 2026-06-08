"""Circle Internet Financial press release parser."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ...base.parser import BasePressReleaseParser, BaseFinancialTablesParser


class CirclePressReleaseParser(BasePressReleaseParser):
    # Circle's press release structure is bank-like (net interest income model)
    GAAP_HEADER = "Condensed Consolidated Statements of Operations"
    NON_GAAP_HEADER = "Adjusted EBITDA"

    _GAAP_ALTERNATES = [
        "Condensed Consolidated Statements of Operations",
        "Statements of Operations",
        "Income Statement",
        "Financial Results",
        "Selected Financial Data",
    ]
    _NON_GAAP_ALTERNATES = [
        "Adjusted EBITDA",
        "Non-GAAP",
        "Adjusted Financial Measures",
    ]
    _SEGMENT_HEADERS = [
        "Revenue Breakdown",
        "Revenue by Product",
        "Supplemental Data",
        "Key Financial and Operating Metrics",
        "Selected Operating Metrics",
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


class CircleFinancialTablesParser(BaseFinancialTablesParser):
    PAGE_SECTION_KEYS = {
        "income_statement": [
            "CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS",
            "STATEMENTS OF OPERATIONS",
        ],
        "balance_sheet": [
            "CONDENSED CONSOLIDATED BALANCE SHEETS",
            "BALANCE SHEETS",
        ],
        "cash_flow": [
            "CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS",
            "STATEMENTS OF CASH FLOWS",
        ],
        "segment_data": [
            "KEY FINANCIAL AND OPERATING METRICS",
            "SUPPLEMENTAL DATA",
            "REVENUE BREAKDOWN",
        ],
    }

    def parse(self, pdf_path: Path) -> dict[str, pd.DataFrame]:
        if not pdf_path.exists():
            return {}
        return self._parse_pdf(pdf_path)
