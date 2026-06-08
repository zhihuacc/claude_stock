"""Coherent Corp (COHR) downloader.

Source: www.coherent.com/company/investor-relations/financial-releases
Fiscal year ends June 30.

FQ → calendar slug:
  FQ1 (Jul-Sep) FYYYY announced ~Nov(FY-1) → {FY-1}-Q3
  FQ2 (Oct-Dec) FYYYY announced ~Feb(FY)   → {FY-1}-Q4
  FQ3 (Jan-Mar) FYYYY announced ~May(FY)   → {FY}-Q1
  FQ4 (Apr-Jun) FYYYY announced ~Aug(FY)   → {FY}-Q2
"""

from __future__ import annotations

import re
from pathlib import Path

from ...base.downloader import BaseDownloader

_BASE = "https://www.coherent.com"
_FINANCIAL_RELEASES_URL = f"{_BASE}/company/investor-relations/financial-releases"
_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4}
_PDF_LINK_TEXTS = {"Click here for full release", "Shareholder Letter"}


class CohrDownloader(BaseDownloader):
    MIN_QUARTER = "2019-Q2"

    @staticmethod
    def _fq_fy_to_cal_slug(fq: int, fy: int) -> str:
        if fq == 1:
            return f"{fy - 1}-Q3"
        elif fq == 2:
            return f"{fy - 1}-Q4"
        elif fq == 3:
            return f"{fy}-Q1"
        else:
            return f"{fy}-Q2"

    @staticmethod
    def _parse_fq_fy_from_slug(slug: str) -> tuple[int, int] | None:
        """Extract (fq, fy) from a press-release URL slug or PDF filename."""
        slug = re.sub(r"\.[a-z]{2,4}$", "", slug, flags=re.I)
        # Compact form: fy22-q4, fy22q4, fy19q4 (filenames like earnings-release-fy22-q4)
        m = re.search(r"fy(\d\d)-?q(\d)", slug, re.I)
        if m:
            return int(m.group(2)), 2000 + int(m.group(1))
        # Full year + ordinal word: "third-quarter-fiscal-year-2026-results"
        fy_m = re.search(r"\b20(\d\d)\b", slug)
        if not fy_m:
            return None
        fy = 2000 + int(fy_m.group(1))
        fq_word_m = re.search(r"(first|second|third|fourth)", slug, re.I)
        if fq_word_m:
            return _ORDINALS[fq_word_m.group(1).lower()], fy
        # Q-notation: "Q4 and Full-Year Fiscal 2022"
        fq_num_m = re.search(r"\bq(\d)\b", slug, re.I)
        if fq_num_m:
            return int(fq_num_m.group(1)), fy
        return None

    def list_quarters(self) -> list[dict]:
        from bs4 import BeautifulSoup
        soup = self.get_soup(_FINANCIAL_RELEASES_URL)
        seen: set[str] = set()
        quarters: list[dict] = []

        # Recent quarters: "Press Release" links → landing pages
        for a in soup.find_all("a", href=True):
            if a.get_text(strip=True) != "Press Release":
                continue
            href = a["href"]
            if "news/press-releases/" not in href:
                continue
            slug = href.split("/news/press-releases/")[-1]
            if not re.search(r"result", slug, re.I):
                continue
            parsed = self._parse_fq_fy_from_slug(slug)
            if not parsed:
                continue
            fq, fy = parsed
            label = self._fq_fy_to_cal_slug(fq, fy)
            if label in seen:
                continue
            seen.add(label)
            press_url = f"{_BASE}{href}" if href.startswith("/") else href
            quarters.append({"label": label, "press_url": press_url, "direct_pdf": None})

        # Older quarters: direct "View ... Results" PDF links on the page
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ".pdf" not in href.lower():
                continue
            if "earnings-release" not in href.lower() and "earnings" not in href.lower():
                continue
            # Parse FQ/FY from filename or link text
            filename = href.split("/")[-1]
            parsed = self._parse_fq_fy_from_slug(filename)
            if not parsed:
                # Try link text as fallback
                parsed = self._parse_fq_fy_from_slug(a.get_text(strip=True))
            if not parsed:
                continue
            fq, fy = parsed
            label = self._fq_fy_to_cal_slug(fq, fy)
            if label in seen:
                continue
            seen.add(label)
            pdf_url = f"{_BASE}{href}" if href.startswith("/") else href
            quarters.append({"label": label, "press_url": None, "direct_pdf": pdf_url})

        return sorted(quarters, key=lambda q: q["label"], reverse=True)

    def _get_pdf_from_landing(self, press_url: str) -> str | None:
        from bs4 import BeautifulSoup
        try:
            soup = self.get_soup(press_url)
            for a in soup.find_all("a", href=True):
                href = a["href"]
                t = a.get_text(strip=True)
                if ".pdf" not in href.lower():
                    continue
                if t in _PDF_LINK_TEXTS or "earnings-release" in href.lower():
                    return f"{_BASE}{href}" if href.startswith("/") else href
        except Exception:
            pass
        return None

    def download_quarter(self, quarter: dict, out_dir: Path, force: bool = False) -> None:
        label = quarter["label"]
        q_dir = out_dir / label
        dest = q_dir / "press_release.pdf"

        if not force and dest.exists():
            print(f"  [{label}] press_release.pdf already exists, skipping")
            return

        pdf_url = quarter.get("direct_pdf")
        if not pdf_url and quarter.get("press_url"):
            pdf_url = self._get_pdf_from_landing(quarter["press_url"])

        if not pdf_url:
            print(f"  [{label}] WARNING: no PDF found")
            return

        try:
            r = self.fetch(pdf_url)
            q_dir.mkdir(parents=True, exist_ok=True)
            self.save_pdf(r.content, dest)
            print(f"  [{label}] → {label}/press_release.pdf ({len(r.content):,} bytes)")
        except Exception as exc:
            print(f"  [{label}] ERROR: {exc}")
