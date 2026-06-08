"""AMD IR website downloader.

Source: https://ir.amd.com/financial-information/financial-results
Downloads: press_release.pdf + financial_tables.pdf per quarter.
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urljoin

from ...base.downloader import BaseDownloader

BASE_URL = "https://ir.amd.com"
RESULTS_URL = f"{BASE_URL}/financial-information/financial-results"


class AmdDownloader(BaseDownloader):

    def list_quarters(self) -> list[dict]:
        resp = self.fetch(RESULTS_URL)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        quarters: list[dict] = []

        for box in soup.find_all("div", class_="box quarterly-results"):
            for row in box.find_all("div", class_="col-md-4 results-info"):
                quarter_tag = row.find("h3")
                if not quarter_tag:
                    continue
                label = quarter_tag.get_text(strip=True)
                date_tag = row.find("div", class_="date")
                date_str = date_tag.get_text(strip=True) if date_tag else ""

                links_col = row.find_next_sibling("div", class_="col-md-8")
                if not links_col:
                    continue

                press_url = None
                tables_pdf_url = None
                for a in links_col.find_all("a", href=True):
                    href = a["href"]
                    if not href.startswith("http"):
                        href = urljoin(BASE_URL, href)
                    if "/press-releases/detail/" in href:
                        press_url = href
                    elif "financial_tables_pdf" in href:
                        tables_pdf_url = href

                quarters.append({
                    "label": label,
                    "date": date_str,
                    "press_url": press_url,
                    "tables_url": tables_pdf_url,
                })

        return quarters

    def download_quarter(self, quarter: dict, out_dir: Path, force: bool = False) -> None:
        label = quarter["label"]
        q_dir = out_dir / self.slug(label)
        q_dir.mkdir(parents=True, exist_ok=True)
        print(f"[{label}]")

        pr_path = q_dir / "press_release.pdf"
        if quarter.get("press_url") and (force or not pr_path.exists()):
            try:
                pdf_url = self._get_press_release_pdf_url(quarter["press_url"])
                if pdf_url:
                    resp = self.fetch(pdf_url)
                    self.save_pdf(resp.content, pr_path)
                    print(f"  press_release.pdf saved")
                else:
                    print(f"  WARNING: no PDF link found on press release page", file=sys.stderr)
            except Exception as e:
                print(f"  ERROR (press release): {e}", file=sys.stderr)
        elif pr_path.exists():
            print(f"  press_release.pdf already exists, skipping")

        # TODO: re-enable when financial_tables parsing is ready
        # ft_path = q_dir / "financial_tables.pdf"
        # if quarter.get("tables_url") and (force or not ft_path.exists()):
        #     try:
        #         resp = self.fetch(quarter["tables_url"])
        #         self.save_pdf(resp.content, ft_path)
        #         print(f"  financial_tables.pdf saved")
        #     except Exception as e:
        #         print(f"  ERROR (financial tables): {e}", file=sys.stderr)
        # elif ft_path.exists():
        #     print(f"  financial_tables.pdf already exists, skipping")

    def _get_press_release_pdf_url(self, press_page_url: str) -> str | None:
        from bs4 import BeautifulSoup
        resp = self.fetch(press_page_url)
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            if "download" in a.get_text(strip=True).lower() and a["href"].endswith(".pdf"):
                return a["href"]
        return None
