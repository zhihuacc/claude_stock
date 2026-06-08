"""NVIDIA downloader using nvidianews.nvidia.com.

NVDA publishes a press release PDF on its news site for each earnings release.
URL pattern:
  Q1-Q3: /news/nvidia-announces-financial-results-for-{ordinal}-quarter-fiscal-{fy}
  Q4:    /news/nvidia-announces-financial-results-for-fourth-quarter-and-fiscal-{fy}

Fiscal year ends in January; ALL fiscal quarters map to cal_year = FY - 1:
  Q1 FY2027 (Apr 2026) → 2026-Q1
  Q4 FY2027 (Jan 2027) → 2026-Q4
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

from ...base.downloader import BaseDownloader

_BASE = "https://nvidianews.nvidia.com"
_ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth"}

# Earliest calendar quarter to download (= Q2 FY2017)
_MIN_FY, _MIN_FQ = 2017, 2


class NvdaDownloader(BaseDownloader):

    # ── Fiscal ↔ calendar mapping ──────────────────────────────────────────

    @staticmethod
    def _fiscal_to_cal_slug(fiscal_q: int, fiscal_year: int) -> str:
        return f"{fiscal_year - 1}-Q{fiscal_q}"

    def slug(self, label: str) -> str:
        m = re.fullmatch(r"Q([1-4]) FY(\d{4})", label, re.IGNORECASE)
        if m:
            return self._fiscal_to_cal_slug(int(m.group(1)), int(m.group(2)))
        return super().slug(label)

    # ── URL helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _news_url(fiscal_q: int, fiscal_year: int) -> str:
        ordinal = _ORDINALS[fiscal_q]
        if fiscal_q == 4:
            slug = f"nvidia-announces-financial-results-for-fourth-quarter-and-fiscal-{fiscal_year}"
        else:
            slug = f"nvidia-announces-financial-results-for-{ordinal}-quarter-fiscal-{fiscal_year}"
        return f"{_BASE}/news/{slug}"

    def _press_release_pdf_url(self, news_url: str) -> str | None:
        from bs4 import BeautifulSoup
        try:
            r = self.fetch(news_url)
        except Exception:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            if "download_pdf" in a["href"]:
                return f"{_BASE}{a['href']}"
        return None

    # ── BaseDownloader interface ───────────────────────────────────────────

    @staticmethod
    def _latest_reported_fq_fy() -> tuple[int, int]:
        """Estimate the most recently reported fiscal quarter based on today's date.

        NVDA reporting schedule (approximate month of announcement):
          Q1 → May   Q2 → August   Q3 → November   Q4 → February
        """
        today = datetime.date.today()
        m = today.month
        cal_year = today.year
        if m <= 2:
            return 4, cal_year      # Q4 FY(cal_year) announced ~Feb
        elif m <= 5:
            return 1, cal_year + 1  # Q1 FY(cal_year+1) announced ~May
        elif m <= 8:
            return 2, cal_year + 1  # Q2 FY(cal_year+1) announced ~Aug
        elif m <= 11:
            return 3, cal_year + 1  # Q3 FY(cal_year+1) announced ~Nov
        else:
            return 4, cal_year + 1  # Q4 FY(cal_year+1) announced ~Feb next year

    def list_quarters(self) -> list[dict]:
        # Generate fiscal quarters newest-first, starting from the latest
        # plausibly-reported quarter down to the minimum.
        max_fq, max_fy = self._latest_reported_fq_fy()
        quarters: list[dict] = []
        fy = max_fy
        fq = max_fq
        while fy > _MIN_FY or (fy == _MIN_FY and fq >= _MIN_FQ):
            quarters.append({"label": f"Q{fq} FY{fy}", "fiscal_q": fq, "fiscal_year": fy})
            fq -= 1
            if fq == 0:
                fq = 4
                fy -= 1
        return quarters

    def download_quarter(self, quarter: dict, out_dir: Path, force: bool = False) -> None:
        label = quarter["label"]
        fq = quarter["fiscal_q"]
        fy = quarter["fiscal_year"]
        slug_str = self.slug(label)
        q_dir = out_dir / slug_str

        dest = q_dir / "press_release.pdf"
        if not force and dest.exists():
            print(f"  [{label}] press_release.pdf already exists, skipping")
            return

        news_url = self._news_url(fq, fy)
        pdf_url = self._press_release_pdf_url(news_url)
        if not pdf_url:
            print(f"  [{label}] skipped — no press release found at {news_url}")
            return

        try:
            r = self.fetch(pdf_url)
            q_dir.mkdir(parents=True, exist_ok=True)
            self.save_pdf(r.content, dest)
            print(f"  [{label}] → {slug_str}/press_release.pdf ({len(r.content):,} bytes)")
        except Exception as exc:
            # nvidianews CDN no longer serves some old PDFs (e.g. 502/404).
            # Fall back to fetching the news page HTML and converting on the fly.
            print(f"  [{label}] PDF unavailable ({exc}); fetching news page HTML …")
            try:
                r = self.fetch(news_url)
                q_dir.mkdir(parents=True, exist_ok=True)
                self.html_to_pdf(r.text, dest)
                print(f"  [{label}] → {slug_str}/press_release.pdf ({dest.stat().st_size:,} bytes, from HTML)")
            except Exception as exc2:
                print(f"  [{label}] ERROR: {exc2}")

