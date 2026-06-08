"""Micron Technology (MU) downloader.

Source: investors.micron.com/quarterly-results
Each press release page has a direct PDF download link (/node/{id}/pdf).

Fiscal year ends ~last Thursday of August.

FQ → calendar slug:
  FQ1 FYYYY (announced Dec) → {Y-1}-Q4
  FQ2 FYYYY (announced Mar) → Y-Q1
  FQ3 FYYYY (announced Jun) → Y-Q2
  FQ4 FYYYY (announced Sep) → Y-Q3
"""

from __future__ import annotations

import re
from pathlib import Path

from ...base.downloader import BaseDownloader

_IR_BASE = "https://investors.micron.com"
_QUARTERLY_RESULTS_URL = f"{_IR_BASE}/quarterly-results"


class MuDownloader(BaseDownloader):

    @staticmethod
    def _fq_fy_to_cal_slug(fq: int, fy: int) -> str:
        if fq == 1:
            return f"{fy - 1}-Q4"
        elif fq == 2:
            return f"{fy}-Q1"
        elif fq == 3:
            return f"{fy}-Q2"
        else:
            return f"{fy}-Q3"

    def list_quarters(self) -> list[dict]:
        from bs4 import BeautifulSoup
        soup = self.get_soup(_QUARTERLY_RESULTS_URL)
        quarters: list[dict] = []
        for acc_div in soup.find_all("div", class_="idm-acc"):
            acc_text = acc_div.get_text(separator=" ", strip=True)
            year_match = re.search(r"20\d\d", acc_text[:50])
            if not year_match:
                continue
            fy = int(year_match.group())
            for a in acc_div.find_all("a", href=re.compile(r"news-release-details")):
                href = a["href"]
                card = a.find_parent(class_=re.compile("card"))
                if not card:
                    continue
                card_title = card.find(class_="card-title")
                if not card_title:
                    continue
                fq_match = re.search(r"Q([1-4])", card_title.get_text(strip=True), re.I)
                if not fq_match:
                    continue
                fq = int(fq_match.group(1))
                label = self._fq_fy_to_cal_slug(fq, fy)
                press_url = f"{_IR_BASE}{href}" if href.startswith("/") else href
                quarters.append({"label": label, "press_url": press_url})
        return quarters

    def _get_pdf_url(self, press_url: str) -> str | None:
        from bs4 import BeautifulSoup
        try:
            soup = self.get_soup(press_url)
            for a in soup.find_all("a", href=True):
                if re.match(r"/node/\d+/pdf$", a["href"]):
                    return f"{_IR_BASE}{a['href']}"
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

        pdf_url = self._get_pdf_url(quarter["press_url"])
        if not pdf_url:
            print(f"  [{label}] WARNING: PDF not found at {quarter['press_url']}")
            return

        try:
            r = self.fetch(pdf_url)
            q_dir.mkdir(parents=True, exist_ok=True)
            self.save_pdf(r.content, dest)
            print(f"  [{label}] → {label}/press_release.pdf ({len(r.content):,} bytes)")
        except Exception as exc:
            print(f"  [{label}] ERROR: {exc}")
