"""Google/Alphabet IR downloader.

Primary:  Alphabet investor CDN (s206.q4cdn.com) — direct PDF, 2022-Q1 onwards.
Fallback: SEC EDGAR 8-K Item 2.02 EX-99.1 exhibit → HTML→PDF via weasyprint.

Alphabet uses calendar year quarters:
  Q1 2025 → 2025-Q1, Q2 2025 → 2025-Q2, etc.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

from ...base.downloader import BaseDownloader

_CDN = "https://s206.q4cdn.com/479360582/files/doc_financials"
_MIN_YEAR, _MIN_Q = 2022, 1

_EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions/CIK0001652044.json"
_EDGAR_ARCHIVES = "https://www.sec.gov/Archives/edgar/data/1652044"


class GoogDownloader(BaseDownloader):
    MIN_QUARTER = "2022-Q1"

    def __init__(self) -> None:
        super().__init__()
        self.session.headers["User-Agent"] = (
            "FundamentalPipeline/1.0 zhihua.che@shopee.com"
        )
        self._edgar_8ks: list[tuple[str, str]] | None = None  # lazy cache

    # ── CDN helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _cdn_url(year: int, q: int) -> str:
        return f"{_CDN}/{year}/q{q}/{year}q{q}-alphabet-earnings-release.pdf"

    # ── EDGAR helpers ──────────────────────────────────────────────────────

    def _earnings_8k_filings(self) -> list[tuple[str, str]]:
        """Return [(filing_date, accession_number)] for Alphabet 8-K Item 2.02 filings."""
        if self._edgar_8ks is not None:
            return self._edgar_8ks
        try:
            r = self.fetch(_EDGAR_SUBMISSIONS)
            data = r.json()
        except Exception as exc:
            print(f"  Warning: could not fetch Alphabet EDGAR submissions: {exc}")
            self._edgar_8ks = []
            return []
        filings = data.get("filings", {}).get("recent", {})
        results: list[tuple[str, str]] = []
        for form, date, acc, items in zip(
            filings.get("form", []),
            filings.get("filingDate", []),
            filings.get("accessionNumber", []),
            filings.get("items", []),
        ):
            if form == "8-K" and "2.02" in str(items):
                results.append((date, acc))
        self._edgar_8ks = sorted(results, reverse=True)
        return self._edgar_8ks

    @staticmethod
    def _quarter_filing_date_range(year: int, q: int) -> tuple[str, str]:
        """Approximate date window when Alphabet files the quarterly earnings 8-K."""
        if q == 1:
            return f"{year}-03-01", f"{year}-05-31"
        elif q == 2:
            return f"{year}-06-01", f"{year}-08-31"
        elif q == 3:
            return f"{year}-09-01", f"{year}-11-30"
        else:
            return f"{year}-11-01", f"{year + 1}-03-31"

    def _edgar_acc_for_quarter(self, year: int, q: int) -> str | None:
        lo, hi = self._quarter_filing_date_range(year, q)
        for date, acc in self._earnings_8k_filings():
            if lo <= date <= hi:
                return acc
        return None

    def _find_ex991_url(self, acc_num: str) -> str | None:
        """Return URL of the EX-99.1 HTML exhibit in this filing."""
        from bs4 import BeautifulSoup
        acc_clean = acc_num.replace("-", "")
        index_url = f"{_EDGAR_ARCHIVES}/{acc_clean}/"
        try:
            r = self.fetch(index_url)
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if f"/{acc_clean}/" in href and href.endswith(".htm"):
                    parent = a.find_parent("tr") or a.find_parent("td") or a
                    if "99.1" in parent.get_text() or "EX-99" in parent.get_text().upper():
                        return f"https://www.sec.gov{href}" if href.startswith("/") else href
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if f"/{acc_clean}/" in href and href.endswith(".htm"):
                    return f"https://www.sec.gov{href}" if href.startswith("/") else href
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_html_from_edgar(content: str) -> str:
        m = re.search(r"(<html[\s>].*?</html>)", content, re.DOTALL | re.IGNORECASE)
        return m.group(1) if m else content

    # ── BaseDownloader interface ───────────────────────────────────────────

    @staticmethod
    def _latest_reported_cal_quarter() -> tuple[int, int]:
        """Estimate the most recently reported calendar quarter.

        Alphabet announcement schedule (approximate):
          Q1 (Jan-Mar) → late April     Q2 (Apr-Jun) → late July
          Q3 (Jul-Sep) → late October   Q4 (Oct-Dec) → late January/Feb
        """
        today = datetime.date.today()
        m, y = today.month, today.year
        if m <= 2:
            return 4, y - 1
        elif m <= 6:
            return 1, y
        elif m <= 9:
            return 2, y
        else:
            return 3, y

    def list_quarters(self) -> list[dict]:
        max_q, max_year = self._latest_reported_cal_quarter()
        quarters: list[dict] = []
        year, q = max_year, max_q
        while year > _MIN_YEAR or (year == _MIN_YEAR and q >= _MIN_Q):
            quarters.append({"label": f"Q{q} {year}", "year": year, "q": q})
            q -= 1
            if q == 0:
                q = 4
                year -= 1
        return quarters

    def slug(self, label: str) -> str:
        m = re.fullmatch(r"Q([1-4])\s+(\d{4})", label, re.IGNORECASE)
        if m:
            return f"{m.group(2)}-Q{m.group(1)}"
        return super().slug(label)

    def download_quarter(self, quarter: dict, out_dir: Path, force: bool = False) -> None:
        label = quarter["label"]
        slug_str = self.slug(label)
        q_dir = out_dir / slug_str
        dest = q_dir / "press_release.pdf"

        if not force and dest.exists():
            print(f"  [{label}] press_release.pdf already exists, skipping")
            return

        # Primary: CDN direct PDF
        cdn_url = self._cdn_url(quarter["year"], quarter["q"])
        try:
            r = self.fetch(cdn_url)
            q_dir.mkdir(parents=True, exist_ok=True)
            self.save_pdf(r.content, dest)
            print(f"  [{label}] → {slug_str}/press_release.pdf ({len(r.content):,} bytes)")
            return
        except Exception as exc:
            print(f"  [{label}] CDN unavailable ({exc}); trying EDGAR …")

        # Fallback: EDGAR EX-99.1 HTML → PDF
        acc = self._edgar_acc_for_quarter(quarter["year"], quarter["q"])
        if not acc:
            print(f"  [{label}] ERROR: no EDGAR 8-K filing found for this quarter")
            return
        ex991_url = self._find_ex991_url(acc)
        if not ex991_url:
            print(f"  [{label}] ERROR: EX-99.1 not found in EDGAR filing {acc}")
            return
        try:
            r = self.fetch(ex991_url)
            html = self._extract_html_from_edgar(r.text)
            q_dir.mkdir(parents=True, exist_ok=True)
            self.html_to_pdf(html, dest)
            print(f"  [{label}] → {slug_str}/press_release.pdf ({dest.stat().st_size:,} bytes, from EDGAR)")
        except Exception as exc:
            print(f"  [{label}] ERROR: {exc}")
