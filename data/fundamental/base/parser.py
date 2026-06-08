"""Base parser classes for press releases and financial tables PDFs.

BasePressReleaseParser  – fuzzy header matching → GAAP/Non-GAAP DataFrames
BaseFinancialTablesParser – PyMuPDF word-position grid reconstruction shared by
                            all companies; subclasses only override PAGE_SECTION_KEYS
                            or _detect_sections() for company-specific headers.
"""

from __future__ import annotations

import difflib
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from pathlib import Path

try:
    import fitz  # PyMuPDF < 1.24
except ImportError:
    import pymupdf as fitz  # type: ignore[no-redef]
import pandas as pd

# ---------------------------------------------------------------------------
# Press release parser
# ---------------------------------------------------------------------------

MONTH_NAMES = frozenset([
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
])


class BasePressReleaseParser(ABC):
    """Parse a press release PDF and return GAAP/Non-GAAP financial tables."""

    GAAP_HEADER: str = "GAAP Quarterly Financial Results"
    NON_GAAP_HEADER: str = "Non-GAAP Quarterly Financial Results"
    MATCH_THRESHOLD: float = 0.7

    @abstractmethod
    def parse(self, pdf_path: Path) -> dict[str, pd.DataFrame]:
        """Return dict with at minimum 'gaap' and 'non_gaap' DataFrame keys.

        Each DataFrame is indexed by metric name. Col 0 = current quarter,
        Col 1 = prior quarter (or YoY comparison).
        Returns an empty dict if the PDF does not exist.
        """
        ...

    # ── Shared helpers ─────────────────────────────────────────────────────

    @staticmethod
    def normalize_header(text: str) -> str:
        text = re.sub(r"[*()\[\]]", "", text)
        return re.sub(r"\s+", " ", text).strip().lower()

    @classmethod
    def similarity(cls, a: str, b: str) -> float:
        return difflib.SequenceMatcher(
            None, cls.normalize_header(a), cls.normalize_header(b)
        ).ratio()

    @staticmethod
    def table_to_df(table: fitz.table.Table) -> pd.DataFrame:
        df = table.to_pandas()
        df = df.rename(columns={df.columns[0]: "Metric"})
        df = df.set_index("Metric")
        return df.map(lambda x: x.strip() if isinstance(x, str) else x)

    def _find_best_headers(
        self, doc: fitz.Document, targets: dict[str, str]
    ) -> dict[str, tuple[float, int, float]]:
        """Scan all pages for each target header; return best (score, page_idx, bottom_y)."""
        best: dict[str, tuple[float, int, float]] = {}
        for page_idx, page in enumerate(doc):
            for block in page.get_text("blocks"):
                x0, y0, x1, y1, text, *_ = block
                text = text.strip()
                if not text:
                    continue
                scores = {k: self.similarity(text, t) for k, t in targets.items()}
                top_key = max(scores, key=scores.__getitem__)
                top_score = scores[top_key]
                if top_score >= self.MATCH_THRESHOLD:
                    prev = best.get(top_key, (-1, 0, 0.0))[0]
                    if top_score > prev:
                        best[top_key] = (top_score, page_idx, y1)
        return best

    def _extract_table_below_header(
        self, doc: fitz.Document, page_idx: int, header_bottom: float
    ) -> pd.DataFrame | None:
        page = doc[page_idx]
        tabs = page.find_tables()
        candidates = [(t.bbox[1], t) for t in tabs.tables if t.bbox[1] > header_bottom]
        if not candidates:
            return None
        _, table = min(candidates, key=lambda kv: kv[0])
        return self.table_to_df(table)


# ---------------------------------------------------------------------------
# Financial tables parser (word-position grid reconstruction)
# ---------------------------------------------------------------------------


class BaseFinancialTablesParser(ABC):
    """Parse a financial_tables.pdf using PyMuPDF word-position analysis.

    The grid reconstruction algorithm (grouping words into rows, clustering
    x-positions into columns) is fully implemented here and shared by all
    companies. Subclasses customise section detection by overriding
    PAGE_SECTION_KEYS or _detect_sections().
    """

    PAGE_SECTION_KEYS: dict[str, list[str]] = {
        "income_statement": ["STATEMENTS OF OPERATIONS"],
        "balance_sheet":    ["BALANCE SHEETS"],
        "cash_flow":        ["STATEMENTS OF CASH FLOWS", "SELECTED CASH FLOW INFORMATION"],
        "segment_data":     ["SELECTED CORPORATE DATA"],
        "gaap_to_non_gaap": ["RECONCILIATION OF GAAP TO NON-GAAP"],
    }

    @abstractmethod
    def parse(self, pdf_path: Path) -> dict[str, pd.DataFrame]:
        """Parse the PDF and return a dict of named section DataFrames.

        Expected keys (present when the section exists):
            income_statement, balance_sheet, cash_flow, segment_data,
            gaap_to_non_gaap, gaap_to_non_gaap_eps, adjusted_ebitda, free_cash_flow
        Returns an empty dict if the PDF does not exist.
        """
        ...

    # ── Section detection (overridable) ───────────────────────────────────

    def _detect_section(self, page_text: str, found: set[str]) -> str | None:
        """Return the section key for this page, or None.

        Default: substring match against PAGE_SECTION_KEYS. Subclasses may
        also add fuzzy matching or additional keys.
        """
        for key, keywords in self.PAGE_SECTION_KEYS.items():
            if key not in found and any(kw in page_text for kw in keywords):
                return key
        return None

    # ── Low-level helpers (used by _parse_page_sections) ──────────────────

    @staticmethod
    def _group_into_rows(words: list, max_gap: float = 4.0) -> list[tuple[float, list]]:
        data = sorted((y0, x0, text) for x0, y0, x1, y1, text, *_ in words)
        if not data:
            return []
        rows: list[tuple[float, list]] = []
        anchor_y, *_ = data[0]
        current: list = [data[0]]
        for y0, x0, text in data[1:]:
            if y0 - anchor_y <= max_gap:
                current.append((y0, x0, text))
            else:
                rows.append((anchor_y, sorted((x, t) for _, x, t in current)))
                anchor_y = y0
                current = [(y0, x0, text)]
        rows.append((anchor_y, sorted((x, t) for _, x, t in current)))
        return rows

    @staticmethod
    def _is_financial_value(text: str) -> bool:
        t = text.strip()
        if t in ("$", "—", ""):
            return False
        return bool(re.match(r"^-$|^\(?[\d,]+\.?\d*\)?%?$", t))

    @staticmethod
    def _cluster_xs(xs: list[float], gap: float = 25.0) -> list[float]:
        if not xs:
            return []
        sorted_xs = sorted(set(round(x, 1) for x in xs))
        clusters: list[list[float]] = [[sorted_xs[0]]]
        for x in sorted_xs[1:]:
            if x - clusters[-1][-1] < gap:
                clusters[-1].append(x)
            else:
                clusters.append([x])
        return [sum(c) / len(c) for c in clusters]

    @staticmethod
    def _is_date_token(text: str) -> bool:
        return (
            text in MONTH_NAMES
            or bool(re.match(r"^\d{1,2},$", text))
            or bool(re.match(r"^\d{4}$", text))
        )

    @classmethod
    def _extract_col_names(
        cls,
        rows: list,
        header_row_indices: list[int],
        col_xs: list[float],
    ) -> list[str]:
        if not col_xs:
            return []
        date_tokens: list[tuple[float, float, str]] = []
        for i in header_row_indices:
            y, ws = rows[i]
            for x, t in ws:
                if cls._is_date_token(t):
                    date_tokens.append((x, y, t))
        if not date_tokens:
            return [f"Col_{i}" for i in range(len(col_xs))]

        month_anchors = sorted((x, y, t) for x, y, t in date_tokens if t in MONTH_NAMES)
        if month_anchors:
            date_clusters: list[list] = []
            for idx, (mx, my, mt) in enumerate(month_anchors):
                upper = month_anchors[idx + 1][0] if idx + 1 < len(month_anchors) else float("inf")
                cluster = [(x, y, t) for x, y, t in date_tokens if mx <= x < upper]
                date_clusters.append(cluster)
        else:
            date_tokens_sorted = sorted(date_tokens)
            date_clusters = [[date_tokens_sorted[0]]]
            for item in date_tokens_sorted[1:]:
                if item[0] - date_clusters[-1][-1][0] < 30:
                    date_clusters[-1].append(item)
                else:
                    date_clusters.append([item])

        def _build_date_str(cluster: list) -> str:
            months = [t for _, _, t in cluster if t in MONTH_NAMES]
            days = [t for _, _, t in cluster if re.match(r"^\d{1,2},$", t)]
            years = [t for _, _, t in cluster if re.match(r"^\d{4}$", t)]
            return " ".join(months[:1] + days[:1] + years[:1])

        clusters_sorted = sorted(date_clusters, key=lambda c: min(x for x, _, _ in c))
        n_clusters = len(clusters_sorted)

        if n_clusters > 0 and len(col_xs) == 2 * n_clusters:
            col_names: list[str] = []
            for cluster in clusters_sorted:
                date_str = _build_date_str(cluster)
                col_names.append(f"{date_str} Amt")
                col_names.append(f"{date_str} EPS")
            return col_names

        col_names = [f"Col_{i}" for i in range(len(col_xs))]
        for i, cluster in enumerate(clusters_sorted):
            if i < len(col_xs):
                col_names[i] = _build_date_str(cluster)
        return col_names

    @classmethod
    def _is_header_row(cls, ws: list[tuple[float, str]]) -> bool:
        texts = [t for _, t in ws]
        return (
            any(t in MONTH_NAMES for t in texts)
            or any(re.match(r"^\d{4}$", t) for t in texts)
            or ("Quarter" in texts and "Group" in texts)
            or ("Quarter" in texts and "End" in texts)
        )

    @classmethod
    def _find_section_groups(cls, rows: list) -> list[tuple[int, int]]:
        header_indices = [i for i, (_, ws) in enumerate(rows) if cls._is_header_row(ws)]
        if not header_indices:
            return []
        groups: list[tuple[int, int]] = []
        group_start = header_indices[0]
        prev = header_indices[0]
        for idx in header_indices[1:]:
            if idx - prev <= 4:
                prev = idx
            else:
                groups.append((group_start, prev))
                group_start = idx
                prev = idx
        groups.append((group_start, prev))
        return groups

    @classmethod
    def _parse_section_df(
        cls,
        rows: list,
        col_xs: list[float],
        label_x_max: float,
        start_idx: int,
        end_idx: int,
        skip_indices: set[int],
        col_names: list[str],
    ) -> pd.DataFrame:
        records: list[list] = []
        for i in range(start_idx, min(end_idx + 1, len(rows))):
            if i in skip_indices:
                continue
            _, ws = rows[i]
            label_words = [
                (x, t) for x, t in ws
                if x < label_x_max and t != "$" and not cls._is_financial_value(t)
            ]
            value_words = [
                (x, t) for x, t in ws
                if x >= label_x_max and cls._is_financial_value(t)
            ]
            if not value_words:
                continue
            label = " ".join(t for _, t in sorted(label_words))
            if not label.strip():
                continue
            if label.endswith("%") and not label.endswith(" %"):
                label = label[:-1].rstrip() + " %"
            if any("%" in t for _, t in value_words) and "%" not in label:
                label = label.rstrip() + " %"
            row_vals: dict[int, list[str]] = defaultdict(list)
            for x, t in value_words:
                col_idx = min(range(len(col_xs)), key=lambda i: abs(col_xs[i] - x))
                row_vals[col_idx].append(t)
            row = [label] + [" ".join(row_vals.get(i, [])) for i in range(len(col_xs))]
            records.append(row)
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records, columns=["Metric"] + col_names)
        return df.set_index("Metric")

    def _parse_page_sections(self, page: fitz.Page) -> list[dict]:
        """Return list of {section_idx, df, col_xs, col_names} for one page."""
        words = page.get_text("words")
        rows = self._group_into_rows(words)
        header_groups = self._find_section_groups(rows)
        if not header_groups:
            return []
        results: list[dict] = []
        for section_num, (hg_start, hg_end) in enumerate(header_groups):
            data_start_idx = hg_end + 1
            if section_num + 1 < len(header_groups):
                data_end_idx = header_groups[section_num + 1][0] - 1
            else:
                data_end_idx = len(rows) - 1
            if data_start_idx > data_end_idx:
                continue
            value_xs: list[float] = []
            for i in range(data_start_idx, data_end_idx + 1):
                _, ws = rows[i]
                for x, t in ws:
                    if self._is_financial_value(t):
                        value_xs.append(x)
            col_xs = self._cluster_xs(value_xs, gap=25)
            if not col_xs:
                continue
            month_xs: list[float] = []
            for i in range(hg_start, hg_end + 1):
                _, ws = rows[i]
                for x, t in ws:
                    if t in MONTH_NAMES:
                        month_xs.append(x)
            if month_xs:
                left_bound = min(month_xs) - 30
                filtered = [cx for cx in col_xs if cx >= left_bound]
                if filtered:
                    col_xs = filtered
            label_x_max = min(col_xs) - 50
            header_indices = list(range(hg_start, hg_end + 1))
            col_names = self._extract_col_names(rows, header_indices, col_xs)
            skip_indices = set(range(hg_start, hg_end + 1))
            df = self._parse_section_df(
                rows, col_xs, label_x_max, data_start_idx, data_end_idx,
                skip_indices, col_names,
            )
            if not df.empty:
                results.append({
                    "section_idx": section_num,
                    "df": df,
                    "col_xs": col_xs,
                    "col_names": col_names,
                })
        return results

    def _parse_pdf(self, pdf_path: Path) -> dict[str, pd.DataFrame]:
        """Core parsing logic used by the default parse() implementation."""
        doc = fitz.open(str(pdf_path))
        result: dict[str, pd.DataFrame] = {}
        found: set[str] = set()

        for page in doc:
            text = page.get_text()
            sections = self._parse_page_sections(page)

            key = self._detect_section(text, found)
            if key and key not in found and sections:
                result[key] = sections[0]["df"]
                found.add(key)

            # Non-GAAP reconciliation page can contain two sections
            if "RECONCILIATION OF GAAP TO NON-GAAP" in text:
                if "gaap_to_non_gaap" not in found and sections:
                    result["gaap_to_non_gaap"] = sections[0]["df"]
                    found.add("gaap_to_non_gaap")
                if len(sections) >= 2 and "gaap_to_non_gaap_eps" not in found:
                    result["gaap_to_non_gaap_eps"] = sections[1]["df"]
                    found.add("gaap_to_non_gaap_eps")

            if (
                "Adjusted EBITDA" in text
                and "adjusted_ebitda" not in found
                and "SELECTED CORPORATE DATA" not in text
            ):
                for s in sections:
                    if any("Adjusted EBITDA" in str(m) for m in s["df"].index):
                        result["adjusted_ebitda"] = s["df"]
                        found.add("adjusted_ebitda")
                        break

            if (
                "Free cash flow" in text
                and "free_cash_flow" not in found
                and "SELECTED CORPORATE DATA" not in text
            ):
                for s in sections:
                    if any("Free cash flow" in str(m) for m in s["df"].index):
                        result["free_cash_flow"] = s["df"]
                        found.add("free_cash_flow")
                        break

        # Trim to 2 most-recent periods (4 columns for EPS tables)
        for key in list(result.keys()):
            df = result[key]
            if df.empty or not len(df.columns):
                continue
            first_col = df.columns[0]
            is_eps = (
                first_col.endswith(" Amt")
                and len(df.columns) > 1
                and df.columns[1].endswith(" EPS")
            )
            result[key] = df.iloc[:, :4] if is_eps else df.iloc[:, :2]

        return result
