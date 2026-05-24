"""Extract GAAP and Non-GAAP quarterly financial tables from earnings press release PDFs."""

import difflib
import re
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd

# Canonical header strings used for fuzzy matching (asterisks/parens stripped at match time)
_GAAP_HEADER = "GAAP Quarterly Financial Results"
_NON_GAAP_HEADER = "Non-GAAP Quarterly Financial Results"

# Minimum similarity ratio (0–1) to accept a text block as a header match
_MATCH_THRESHOLD = 0.7


def _normalize(text: str) -> str:
    """Lowercase, strip asterisks/parens, collapse whitespace."""
    text = re.sub(r"[*()\[\]]", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _to_df(table: fitz.table.Table) -> pd.DataFrame:
    df = table.to_pandas()
    df = df.rename(columns={df.columns[0]: "Metric"})
    df = df.set_index("Metric")
    return df.map(lambda x: x.strip() if isinstance(x, str) else x)


def extract_quarterly_financial_tables(pdf_path: str | Path) -> dict[str, pd.DataFrame]:
    """
    Parse GAAP and Non-GAAP quarterly financial results tables from a press release PDF.

    Returns a dict with keys:
        "gaap"     -> DataFrame with GAAP Quarterly Financial Results
        "non_gaap" -> DataFrame with Non-GAAP Quarterly Financial Results

    Each DataFrame has the metric name as the index and columns like Q1'26, Q1'25, Y/Y, Q4'25, Q/Q.

    The two tables may appear on the same page or on different pages. Each header is matched by
    fuzzy similarity (difflib); each block is assigned exclusively to its best-matching target so
    that "GAAP …" and "Non-GAAP …" don't steal each other's match.
    """
    doc = fitz.open(str(pdf_path))
    targets = {"gaap": _GAAP_HEADER, "non_gaap": _NON_GAAP_HEADER}

    # Pass 1: scan every page to find the best-matching text block for each header.
    # best_headers[key] = (score, page_idx, block_bottom_y)
    best_headers: dict[str, tuple[float, int, float]] = {}

    for page_idx, page in enumerate(doc):
        for block in page.get_text("blocks"):
            x0, y0, x1, y1, text, *_ = block
            text = text.strip()
            if not text:
                continue
            scores = {key: _similarity(text, target) for key, target in targets.items()}
            top_key = max(scores, key=scores.__getitem__)
            top_score = scores[top_key]
            if top_score >= _MATCH_THRESHOLD:
                prev_score = best_headers.get(top_key, (-1, 0, 0.0))[0]
                if top_score > prev_score:
                    best_headers[top_key] = (top_score, page_idx, y1)

    missing = [k for k in targets if k not in best_headers]
    if missing:
        raise ValueError(f"Could not find headers {missing} in {pdf_path}")

    # Pass 2: for each header, find the table on the same page whose top edge is
    # closest below the header's bottom edge.
    result: dict[str, pd.DataFrame] = {}
    for key, (_, page_idx, header_bottom) in best_headers.items():
        page = doc[page_idx]
        tabs = page.find_tables()
        candidates = [(t.bbox[1], t) for t in tabs.tables if t.bbox[1] > header_bottom]
        if not candidates:
            raise ValueError(
                f"No table found below '{key}' header on page {page_idx + 1} of {pdf_path}"
            )
        _, table = min(candidates, key=lambda kv: kv[0])
        result[key] = _to_df(table)

    return result


if __name__ == "__main__":
    import sys

    path = sys.argv[1]
    tables = extract_quarterly_financial_tables(path)

    print("=== GAAP Quarterly Financial Results ===")
    print(tables["gaap"].to_string())
    print()
    print("=== Non-GAAP Quarterly Financial Results ===")
    print(tables["non_gaap"].to_string())
