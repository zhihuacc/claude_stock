"""Lumentum Holdings (LITE) downloader.

Source: SEC EDGAR — 8-K Item 2.02 filings.  CIK: 0001633689.
Fiscal year ends ~last Saturday of June.

FQ → calendar slug (filing-date basis):
  FQ1 (Jul-Sep) filed ~Nov  →  YYYY-Q3     (Nov 2025  → 2025-Q3)
  FQ2 (Oct-Dec) filed ~Feb  →  (YYYY-1)-Q4 (Feb 2026  → 2025-Q4)
  FQ3 (Jan-Mar) filed ~May  →  YYYY-Q1     (May 2026  → 2026-Q1)
  FQ4 (Apr-Jun) filed ~Aug  →  YYYY-Q2     (Aug 2025  → 2025-Q2)
"""

from __future__ import annotations

from ...base.edgar_downloader import EdgarDownloader


class LiteDownloader(EdgarDownloader):
    EDGAR_CIK = "0001633689"
    EDGAR_DATA_URL = "https://www.sec.gov/Archives/edgar/data/1633689"
    MIN_QUARTER = "2019-Q3"

    @staticmethod
    def _filing_date_to_cal_slug(date_str: str) -> str:
        year, month, _ = date_str.split("-")
        y, m = int(year), int(month)
        if m <= 2:
            return f"{y - 1}-Q4"
        elif m <= 5:
            return f"{y}-Q1"
        elif m <= 8:
            return f"{y}-Q2"
        else:
            return f"{y}-Q3"

    def list_quarters(self) -> list[dict]:
        quarters: list[dict] = []
        for date, acc in self._earnings_8k_filings():
            slug = self._filing_date_to_cal_slug(date)
            quarters.append({"label": slug, "date": date, "acc_num": acc})
        return quarters
