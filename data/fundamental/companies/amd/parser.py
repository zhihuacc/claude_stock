"""AMD press release and financial tables parsers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ...base.parser import BasePressReleaseParser, BaseFinancialTablesParser


class AmdPressReleaseParser(BasePressReleaseParser):
    GAAP_HEADER = "GAAP Quarterly Financial Results"
    NON_GAAP_HEADER = "Non-GAAP Quarterly Financial Results"

    def parse(self, pdf_path: Path) -> dict[str, pd.DataFrame]:
        if not pdf_path.exists():
            return {}
        try:
            import fitz
        except ImportError:
            import pymupdf as fitz  # type: ignore
        doc = fitz.open(str(pdf_path))
        targets = {"gaap": self.GAAP_HEADER, "non_gaap": self.NON_GAAP_HEADER}
        best_headers = self._find_best_headers(doc, targets)
        missing = [k for k in targets if k not in best_headers]
        if missing:
            print(f"  WARNING: could not find headers {missing} in {pdf_path.name}")
        result: dict[str, pd.DataFrame] = {}
        for key, (_, page_idx, header_bottom) in best_headers.items():
            df = self._extract_table_below_header(doc, page_idx, header_bottom)
            if df is not None:
                result[key] = df
        return result


class AmdFinancialTablesParser(BaseFinancialTablesParser):
    # AMD uses the default PAGE_SECTION_KEYS defined in BaseFinancialTablesParser

    def parse(self, pdf_path: Path) -> dict[str, pd.DataFrame]:
        if not pdf_path.exists():
            return {}
        return self._parse_pdf(pdf_path)
