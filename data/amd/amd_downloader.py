#!/usr/bin/env python3
"""Download AMD quarterly financial reports.

Source: https://ir.amd.com/financial-information/financial-results
Outputs:
  - <output_dir>/<quarter>/press_release.pdf    (original PDF from press release page)
  - <output_dir>/<quarter>/financial_tables.pdf (original PDF from IR results page)
"""

import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://ir.amd.com"
RESULTS_URL = f"{BASE_URL}/financial-information/financial-results"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AMD-IR-Downloader/1.0)"}
REQUEST_DELAY = 1.0  # seconds between requests


def fetch(url: str, session: requests.Session) -> requests.Response:
    resp = session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp


def parse_quarters(html: str) -> list[dict]:
    """Extract all quarters from the financial results page."""
    soup = BeautifulSoup(html, "html.parser")
    quarters = []

    for box in soup.find_all("div", class_="box quarterly-results"):
        year_tag = box.find("h2")
        year = year_tag.get_text(strip=True) if year_tag else "unknown"

        for row in box.find_all("div", class_="col-md-4 results-info"):
            quarter_tag = row.find("h3")
            if not quarter_tag:
                continue
            quarter_label = quarter_tag.get_text(strip=True)  # e.g. "Q1 2026"
            date_tag = row.find("div", class_="date")
            date_str = date_tag.get_text(strip=True) if date_tag else ""

            # Collect links from the sibling col-md-8
            links_col = row.find_next_sibling("div", class_="col-md-8")
            if not links_col:
                continue

            press_url = None
            tables_pdf_url = None

            for a in links_col.find_all("a", href=True):
                href = a["href"]
                if not href.startswith("http"):
                    href = urljoin(BASE_URL, href)
                span = a.find("span")
                icon = span["class"][0] if span and span.get("class") else ""
                text = a.get_text(strip=True).lower()

                if "/press-releases/detail/" in href:
                    press_url = href
                elif "financial_tables_pdf" in href:
                    tables_pdf_url = href

            quarters.append(
                {
                    "label": quarter_label,
                    "year": year,
                    "date": date_str,
                    "press_url": press_url,
                    "tables_pdf_url": tables_pdf_url,
                }
            )

    return quarters


def get_press_release_pdf_url(press_page_url: str, session: requests.Session) -> str | None:
    """Fetch the press release page and return the 'Download as PDF' link."""
    resp = fetch(press_page_url, session)
    soup = BeautifulSoup(resp.text, "html.parser")
    for a in soup.find_all("a", href=True):
        if "download" in a.get_text(strip=True).lower() and a["href"].endswith(".pdf"):
            return a["href"]
    return None


def download_pdf(url: str, dest: Path, session: requests.Session) -> None:
    resp = fetch(url, session)
    dest.write_bytes(resp.content)


def slug(label: str) -> str:
    """Convert quarter label to folder name: 'Q1 2026' → '2026-Q1', 'Q4 & FY 2025' → '2025-Q4'."""
    m = re.search(r"(Q\d)", label)
    y = re.search(r"(20\d\d)", label)
    if m and y:
        return f"{y.group(1)}-{m.group(1)}"
    return re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_")


def download_quarter(q: dict, out_dir: Path, session: requests.Session, force: bool = False) -> None:
    label = q["label"]
    dir_name = slug(label)
    q_dir = out_dir / dir_name
    q_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{label}] {q['date']}")

    # Press release PDF
    pr_path = q_dir / "press_release.pdf"
    if q["press_url"] and (force or not pr_path.exists()):
        print(f"  -> Press release page: {q['press_url']}")
        try:
            pdf_url = get_press_release_pdf_url(q["press_url"], session)
            if pdf_url:
                print(f"     PDF: {pdf_url}")
                download_pdf(pdf_url, pr_path, session)
                print(f"     Saved: {pr_path}")
            else:
                print(f"     WARNING: no PDF download link found", file=sys.stderr)
        except Exception as e:
            print(f"     ERROR: {e}", file=sys.stderr)
        time.sleep(REQUEST_DELAY)
    elif pr_path.exists():
        print(f"  -> Press release PDF already exists, skipping.")

    # Financial tables PDF
    ft_path = q_dir / "financial_tables.pdf"
    if q["tables_pdf_url"] and (force or not ft_path.exists()):
        print(f"  -> Financial tables: {q['tables_pdf_url']}")
        try:
            download_pdf(q["tables_pdf_url"], ft_path, session)
            print(f"     Saved: {ft_path}")
        except Exception as e:
            print(f"     ERROR: {e}", file=sys.stderr)
        time.sleep(REQUEST_DELAY)
    elif ft_path.exists():
        print(f"  -> Financial tables already exist, skipping.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download AMD quarterly financial reports.")
    parser.add_argument("--out", default="data/amd/reports", help="Output directory (default: data/amd/reports)")
    parser.add_argument("--force", action="store_true", help="Re-download even if files already exist")
    parser.add_argument("--latest", action="store_true", help="Download only the most recent quarter")
    parser.add_argument("--quarter", metavar="LABEL", help="Download a specific quarter, e.g. 'Q1 2026'")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()

    print(f"Fetching quarter list from {RESULTS_URL} ...")
    resp = fetch(RESULTS_URL, session)
    quarters = parse_quarters(resp.text)
    print(f"Found {len(quarters)} quarters.\n")

    if not quarters:
        print("No quarters found. The page structure may have changed.", file=sys.stderr)
        sys.exit(1)

    if args.quarter:
        target = args.quarter.strip()
        quarters = [q for q in quarters if q["label"].lower() == target.lower()]
        if not quarters:
            print(f"Quarter '{target}' not found.", file=sys.stderr)
            sys.exit(1)
    elif args.latest:
        quarters = quarters[:1]

    for q in quarters:
        download_quarter(q, out_dir, session, force=args.force)

    print("\nDone.")


if __name__ == "__main__":
    main()
