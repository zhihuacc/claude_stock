"""EdgarDownloader: base class for EDGAR 8-K earnings press release downloaders.

Subclasses must define:
  EDGAR_CIK       - 10-digit zero-padded CIK string, e.g. "0000723125"
  EDGAR_DATA_URL  - https://www.sec.gov/Archives/edgar/data/{cik_int}
  _filing_date_to_cal_slug(date_str) - company-specific fiscal→calendar mapping
  list_quarters() - builds quarter list from _earnings_8k_filings()
"""

from __future__ import annotations

import re
from abc import abstractmethod
from pathlib import Path

from .downloader import BaseDownloader


class EdgarDownloader(BaseDownloader):
    EDGAR_CIK: str = ""
    EDGAR_DATA_URL: str = ""

    def __init__(self) -> None:
        super().__init__()
        self.session.headers["User-Agent"] = (
            "FundamentalPipeline/1.0 zhihua.che@shopee.com"
        )

    # ── EDGAR helpers ──────────────────────────────────────────────────────

    def _earnings_8k_filings(self) -> list[tuple[str, str]]:
        """Return [(filing_date, accession_number)] for 8-K Item 2.02 filings."""
        url = f"https://data.sec.gov/submissions/CIK{self.EDGAR_CIK}.json"
        try:
            r = self.fetch(url)
            data = r.json()
        except Exception as exc:
            print(f"  Warning: could not fetch EDGAR submissions: {exc}")
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
        return sorted(results, reverse=True)

    def _find_ex991_url(self, acc_num: str) -> tuple[str | None, bool]:
        """Return (url, is_pdf) for the EX-99.1 exhibit in this filing.

        Uses the structured filing index page (which labels each document by
        type) instead of the raw directory listing (which has no labels).
        Returns is_pdf=True for direct PDF exhibits.
        """
        from bs4 import BeautifulSoup
        acc_clean = acc_num.replace("-", "")
        # Structured index page has proper document-type labels (e.g. "EX-99.1")
        index_url = f"{self.EDGAR_DATA_URL}/{acc_clean}/{acc_num}-index.html"
        _VALID = (".htm", ".html", ".pdf")
        try:
            r = self.fetch(index_url)
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                # Strip iXBRL viewer prefix (/ix?doc=...) to get the bare path
                if "/ix?doc=" in href:
                    href = re.sub(r"^.*?/ix\?doc=", "", href)
                if f"/{acc_clean}/" not in href:
                    continue
                if not any(href.lower().endswith(ext) for ext in _VALID):
                    continue
                parent = a.find_parent("tr") or a.find_parent("td") or a
                text = parent.get_text()
                if "99.1" in text or "EX-99" in text.upper():
                    full_url = f"https://www.sec.gov{href}" if href.startswith("/") else href
                    return full_url, href.lower().endswith(".pdf")
            # Fallback: first direct (non-iXBRL) HTML file listed in the filing
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/ix?doc=" in href:
                    continue
                if f"/{acc_clean}/" in href and href.lower().endswith((".htm", ".html")):
                    full_url = f"https://www.sec.gov{href}" if href.startswith("/") else href
                    return full_url, False
        except Exception:
            pass
        return None, False

    @staticmethod
    def _extract_html_from_edgar(content: str) -> str:
        """Strip EDGAR SGML wrapper; return inner HTML content."""
        m = re.search(r"(<html[\s>].*?</html>)", content, re.DOTALL | re.IGNORECASE)
        return m.group(1) if m else content

    # ── BaseDownloader interface ───────────────────────────────────────────

    def slug(self, label: str) -> str:
        if re.fullmatch(r"\d{4}-Q[1-4]", label):
            return label
        return super().slug(label)

    @abstractmethod
    def list_quarters(self) -> list[dict]:
        ...

    def download_quarter(self, quarter: dict, out_dir: Path, force: bool = False) -> None:
        label = quarter["label"]
        q_dir = out_dir / label
        dest = q_dir / "press_release.pdf"

        if not force and dest.exists():
            print(f"  [{label}] press_release.pdf already exists, skipping")
            return

        url, is_pdf = self._find_ex991_url(quarter["acc_num"])
        if not url:
            print(f"  [{label}] WARNING: EX-99.1 not found in filing {quarter['acc_num']}")
            return

        try:
            r = self.fetch(url)
            q_dir.mkdir(parents=True, exist_ok=True)
            if is_pdf:
                self.save_pdf(r.content, dest)
            else:
                html = self._extract_html_from_edgar(r.text)
                self.html_to_pdf(html, dest)
            print(f"  [{label}] → {label}/press_release.pdf ({dest.stat().st_size:,} bytes)")
        except Exception as exc:
            print(f"  [{label}] ERROR: {exc}")
