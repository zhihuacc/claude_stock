"""BaseDownloader: shared IR website scraping logic for all company downloaders."""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from pathlib import Path

import requests
from bs4 import BeautifulSoup


class BaseDownloader(ABC):
    REQUEST_DELAY: float = 1.0
    MAX_RETRIES: int = 3
    MIN_QUARTER: str = "2016-Q2"  # 10-year lookback; override for newer companies

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers["User-Agent"] = (
            "Mozilla/5.0 (compatible; FundamentalPipeline/1.0)"
        )

    # ── Abstract interface ─────────────────────────────────────────────────

    @abstractmethod
    def list_quarters(self) -> list[dict]:
        """Scrape the IR index page and return a list of quarter dicts.

        Each dict must contain at minimum:
            label      str        human-readable label, e.g. "Q3 2024"
            press_url  str|None   URL to press release landing page or direct PDF
            tables_url str|None   URL to financial tables PDF (None = not separate)
        """
        ...

    @abstractmethod
    def download_quarter(self, quarter: dict, out_dir: Path, force: bool = False) -> None:
        """Fetch PDFs for one quarter into out_dir / slug(quarter['label']) /."""
        ...

    # ── Shared helpers ─────────────────────────────────────────────────────

    def fetch(self, url: str, **kwargs) -> requests.Response:
        """GET with retry and rate limiting."""
        last_exc: Exception | None = None
        for attempt in range(self.MAX_RETRIES):
            try:
                resp = self.session.get(url, timeout=30, **kwargs)
                resp.raise_for_status()
                time.sleep(self.REQUEST_DELAY)
                return resp
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
        raise last_exc  # type: ignore[misc]

    def get_soup(self, url: str) -> BeautifulSoup:
        resp = self.fetch(url)
        return BeautifulSoup(resp.text, "html.parser")

    @staticmethod
    def save_pdf(content: bytes, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    @staticmethod
    def slug(label: str) -> str:
        """Convert quarter label to sortable folder name: 'Q3 2024' → '2024-Q3'."""
        m = re.search(r"(Q\d)", label)
        y = re.search(r"(20\d\d)", label)
        if m and y:
            return f"{y.group(1)}-{m.group(1)}"
        return re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_")

    def html_to_pdf(self, html: str, dest: Path) -> None:
        """Convert HTML string to PDF using weasyprint."""
        try:
            from weasyprint import HTML  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "weasyprint is required for HTML-to-PDF conversion. "
                "Install it with: pip install weasyprint"
            ) from exc
        dest.parent.mkdir(parents=True, exist_ok=True)
        HTML(string=html).write_pdf(str(dest))

    @staticmethod
    def _quarter_in_range(slug_str: str, min_quarter: str) -> bool:
        """Return True if slug_str >= min_quarter (lexicographic on YYYY-QN format)."""
        return slug_str >= min_quarter

    def run(
        self,
        out_dir: Path,
        force: bool = False,
        latest: bool = False,
        quarter: str | None = None,
    ) -> None:
        """Standard download driver. Filters quarters outside the 10-year window."""
        quarters = self.list_quarters()

        if quarter:
            quarters = [q for q in quarters if q["label"].strip().lower() == quarter.lower()]
            if not quarters:
                print(f"Quarter '{quarter}' not found.")
                return
        elif latest:
            quarters = quarters[:1]
        else:
            quarters = [
                q for q in quarters
                if self._quarter_in_range(self.slug(q["label"]), self.MIN_QUARTER)
            ]

        print(f"Processing {len(quarters)} quarters …")
        for q in quarters:
            self.download_quarter(q, out_dir, force=force)
        print("Done.")
