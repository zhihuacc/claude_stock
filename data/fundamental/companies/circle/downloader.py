"""Circle Internet Financial (CRCL) downloader.

Source: SEC EDGAR — 8-K Item 2.02 filings (earnings press releases).
CIK: 0001876042.  Circle IPO'd June 2025; fiscal year = calendar year.
Press release (EX-99.1) is an HTML exhibit; converted to PDF via weasyprint.
"""

from __future__ import annotations

import re
from pathlib import Path

from ...base.downloader import BaseDownloader

_SUBMISSIONS = "https://data.sec.gov/submissions/CIK0001876042.json"
_EDGAR_DATA = "https://www.sec.gov/Archives/edgar/data/1876042"


class CircleDownloader(BaseDownloader):
    MIN_QUARTER = "2025-Q2"  # First post-IPO earnings quarter

    def __init__(self) -> None:
        super().__init__()
        self.session.headers["User-Agent"] = (
            "FundamentalPipeline/1.0 zhihua.che@shopee.com"
        )

    # ── EDGAR helpers ──────────────────────────────────────────────────────

    def _earnings_8k_filings(self) -> list[tuple[str, str]]:
        """Return [(filing_date, accession_number)] for 8-K Item 2.02 filings."""
        try:
            r = self.fetch(_SUBMISSIONS)
            data = r.json()
        except Exception as exc:
            print(f"  Warning: could not fetch submissions: {exc}")
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

    def _find_ex991_url(self, acc_num: str) -> str | None:
        """Return the URL of the EX-99.1 HTML exhibit in this filing."""
        from bs4 import BeautifulSoup
        acc_clean = acc_num.replace("-", "")
        index_url = f"{_EDGAR_DATA}/{acc_clean}/"
        try:
            r = self.fetch(index_url)
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                # EX-99.1 exhibits are typically named like *press-release*.htm or q*.htm
                if f"/{acc_clean}/" in href and href.endswith(".htm"):
                    # Check nearby text for "EX-99.1" label
                    parent = a.find_parent("tr") or a.find_parent("td") or a
                    parent_text = parent.get_text()
                    if "99.1" in parent_text or "EX-99" in parent_text.upper():
                        return f"https://www.sec.gov{href}" if href.startswith("/") else href
            # Fallback: first .htm file in the filing
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if f"/{acc_clean}/" in href and href.endswith(".htm"):
                    return f"https://www.sec.gov{href}" if href.startswith("/") else href
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_html_from_edgar(content: str) -> str:
        """Strip EDGAR SGML wrapper; return the inner HTML content."""
        m = re.search(r"(<html[\s>].*?</html>)", content, re.DOTALL | re.IGNORECASE)
        return m.group(1) if m else content

    @staticmethod
    def _filing_date_to_cal_slug(date_str: str) -> str:
        """Convert filing date YYYY-MM-DD to calendar quarter slug YYYY-QN.

        Circle reports: Q1→~May, Q2→~Aug, Q3→~Nov, Q4→~Feb.
        We infer the quarter from the filing month.
        """
        year, month, _ = date_str.split("-")
        y, m = int(year), int(month)
        if m <= 2:
            return f"{y - 1}-Q4"   # Q4 of prior year, filed ~Feb
        elif m <= 5:
            return f"{y}-Q1"
        elif m <= 8:
            return f"{y}-Q2"
        elif m <= 11:
            return f"{y}-Q3"
        else:
            return f"{y}-Q4"

    # ── BaseDownloader interface ───────────────────────────────────────────

    def list_quarters(self) -> list[dict]:
        quarters: list[dict] = []
        for date, acc in self._earnings_8k_filings():
            slug = self._filing_date_to_cal_slug(date)
            quarters.append({"label": slug, "date": date, "acc_num": acc})
        return quarters

    def slug(self, label: str) -> str:
        # Labels are already in YYYY-QN format from list_quarters()
        if re.fullmatch(r"\d{4}-Q[1-4]", label):
            return label
        return super().slug(label)

    def download_quarter(self, quarter: dict, out_dir: Path, force: bool = False) -> None:
        label = quarter["label"]
        q_dir = out_dir / label

        dest = q_dir / "press_release.pdf"
        if not force and dest.exists():
            print(f"  [{label}] press_release.pdf already exists, skipping")
            return

        ex991_url = self._find_ex991_url(quarter["acc_num"])
        if not ex991_url:
            print(f"  [{label}] WARNING: EX-99.1 not found in filing {quarter['acc_num']}")
            return

        try:
            r = self.fetch(ex991_url)
            html = self._extract_html_from_edgar(r.text)
            q_dir.mkdir(parents=True, exist_ok=True)
            self.html_to_pdf(html, dest)
            print(f"  [{label}] → {label}/press_release.pdf ({dest.stat().st_size:,} bytes)")
        except Exception as exc:
            print(f"  [{label}] ERROR: {exc}")
