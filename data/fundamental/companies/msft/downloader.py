"""Microsoft IR website downloader.

Source: https://www.microsoft.com/en-us/Investor/earnings/FY-{YYYY}-Q{N}/press-release-webcast
Converts the press release HTML page to PDF via weasyprint.

MSFT fiscal year ends June 30. Fiscal→calendar mapping:
  FY-YYYY-Q1 ends Sep → calendar (YYYY-1)-Q3
  FY-YYYY-Q2 ends Dec → calendar (YYYY-1)-Q4
  FY-YYYY-Q3 ends Mar → calendar YYYY-Q1
  FY-YYYY-Q4 ends Jun → calendar YYYY-Q2
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

from ...base.downloader import BaseDownloader

_BASE = "https://www.microsoft.com"

# MSFT FQ → (calendar_quarter_str, fiscal_year_offset)
_FQ_TO_CAL: dict[int, tuple[str, int]] = {
    1: ("Q3", -1),
    2: ("Q4", -1),
    3: ("Q1",  0),
    4: ("Q2",  0),
}

# FQ1 starts in July; approximate announcement months:
#   Q1 (Sep end) → October   Q2 (Dec end) → January
#   Q3 (Mar end) → April     Q4 (Jun end) → July
_FQ_ANNOUNCE_MONTH = {1: 10, 2: 1, 3: 4, 4: 7}

_MIN_FY, _MIN_FQ = 2016, 4   # FY-2016-Q4 = 2016-Q2


class MsftDownloader(BaseDownloader):

    @staticmethod
    def _fiscal_to_calendar_slug(fy: int, fq: int) -> str:
        cal_q, yr_offset = _FQ_TO_CAL[fq]
        return f"{fy + yr_offset}-{cal_q}"

    def slug(self, label: str) -> str:
        m = re.search(r"FY-?(\d{4})-?Q(\d)", label, re.IGNORECASE)
        if m:
            return self._fiscal_to_calendar_slug(int(m.group(1)), int(m.group(2)))
        return super().slug(label)

    @staticmethod
    def _latest_reported_fy_fq() -> tuple[int, int]:
        """Estimate most recently reported MSFT fiscal quarter.

        Announcement schedule (approximate):
          FQ1 ends Sep → announced ~Oct    FQ2 ends Dec → ~Jan
          FQ3 ends Mar → ~Apr              FQ4 ends Jun → ~Jul
        """
        today = datetime.date.today()
        m, y = today.month, today.year
        if m <= 1:
            return y, 2       # FQ2 of FY(y) announced ~Jan
        elif m <= 4:
            return y, 3       # FQ3 of FY(y) announced ~Apr; safe through April
        elif m <= 7:
            return y, 3       # FQ4 ends June, announced ~Jul — conservative; use FQ3
        elif m <= 10:
            return y + 1, 1   # FQ1 of FY(y+1) ends Sep, announced ~Oct
        else:
            return y + 1, 1   # FQ1 announced ~Oct; safe through December

    def list_quarters(self) -> list[dict]:
        max_fy, max_fq = self._latest_reported_fy_fq()
        quarters: list[dict] = []
        fy, fq = max_fy, max_fq
        while fy > _MIN_FY or (fy == _MIN_FY and fq >= _MIN_FQ):
            url = f"{_BASE}/en-us/Investor/earnings/FY-{fy}-Q{fq}/press-release-webcast"
            quarters.append({"label": f"FY-{fy}-Q{fq}", "fy": fy, "fq": fq, "press_url": url})
            fq -= 1
            if fq == 0:
                fq = 4
                fy -= 1
        return quarters

    def download_quarter(self, quarter: dict, out_dir: Path, force: bool = False) -> None:
        label = quarter["label"]
        slug_str = self.slug(label)
        q_dir = out_dir / slug_str

        dest = q_dir / "press_release.pdf"
        if not force and dest.exists():
            print(f"  [{label}] press_release.pdf already exists, skipping")
            return

        url = quarter["press_url"]
        try:
            resp = self.fetch(url)
            q_dir.mkdir(parents=True, exist_ok=True)
            self.html_to_pdf(resp.text, dest)
            print(f"  [{label}] → {slug_str}/press_release.pdf")
        except Exception as exc:
            print(f"  [{label}] skipped — {exc}")
