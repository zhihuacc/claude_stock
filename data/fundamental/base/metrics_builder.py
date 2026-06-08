"""BaseMetricsBuilder: orchestrates parse → extract → validate → write CSV."""

from __future__ import annotations

import difflib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from .number_parser import parse_number, parse_percent

if TYPE_CHECKING:
    from ..normalizer.name_normalizer import NameNormalizer
    from .parser import BasePressReleaseParser, BaseFinancialTablesParser


_MONTH_NUM: dict[str, int] = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}

_CROSS_CHECK_TOLERANCE = 0.005   # 0.5% relative
_EPS_ABS_TOLERANCE = 0.015       # ±$0.015 for EPS-sized values


# ---------------------------------------------------------------------------
# Validation data structures
# ---------------------------------------------------------------------------

@dataclass
class ValidationIssue:
    quarter: str
    layer: int              # 1=cross-report, 2=internal consistency, 3=sanity bounds
    check: str
    expected: float | None = None
    actual: float | None = None
    pct_diff: float | None = None

    def __str__(self) -> str:
        parts = [f"[L{self.layer}][{self.quarter}] {self.check}"]
        if self.expected is not None and self.actual is not None:
            parts.append(f"expected={self.expected:.4g}, actual={self.actual:.4g}")
            if self.pct_diff is not None:
                parts.append(f"diff={self.pct_diff:.2%}")
        return "  " + " | ".join(parts)


@dataclass
class ValidationReport:
    company: str
    issues: list[ValidationIssue] = field(default_factory=list)

    def add(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)

    def summary(self) -> str:
        if not self.issues:
            return f"[{self.company}] All validation checks passed."
        lines = [f"[{self.company}] {len(self.issues)} validation issue(s):"]
        lines += [str(i) for i in self.issues]
        return "\n".join(lines)

    def has_strict_errors(self) -> bool:
        return any(i.layer == 2 and i.pct_diff is None for i in self.issues)


# ---------------------------------------------------------------------------
# BaseMetricsBuilder
# ---------------------------------------------------------------------------

class BaseMetricsBuilder(ABC):
    """Orchestrates: load PDFs → parse → extract raw metrics → validate → return DataFrame."""

    # Only GAAP keys: press-release non-GAAP tables often use YoY comparison columns
    # (not sequential prior), making non_gaap cross-checks unreliable across companies.
    CROSS_CHECK_KEYS: list[str] = [
        "gaap_revenue",
        "gaap_gross_profit",
        "gaap_operating_income",
        "gaap_net_income",
        "gaap_diluted_earnings_per_share",
    ]

    # ── Abstract interface ─────────────────────────────────────────────────

    @property
    @abstractmethod
    def press_release_parser(self) -> BasePressReleaseParser:
        ...

    @property
    @abstractmethod
    def financial_tables_parser(self) -> BaseFinancialTablesParser:
        ...

    @abstractmethod
    def extract_raw_metrics(
        self,
        tables: dict[str, pd.DataFrame],
        col: int,
        quarter: str,
    ) -> dict[str, str | None]:
        """Extract raw string values from parsed tables for one quarter/column.

        col=0 → current quarter, col=1 → prior quarter.
        Returns dict with canonical snake_case keys → raw strings ("1,234", "46%").
        """
        ...

    # ── Shared helpers ─────────────────────────────────────────────────────

    @staticmethod
    def resolve_metric(
        index: pd.Index,
        metric: str,
        cutoff: float = 0.82,
        normalizer: NameNormalizer | None = None,
    ) -> str | None:
        """4-stage match: exact → case-insensitive → fuzzy → synonym expansion."""
        if metric in index:
            return metric
        unique: list[str] = list(dict.fromkeys(index))
        metric_lower = metric.lower()
        for name in unique:
            if name.lower() == metric_lower:
                return name
        search_has_pct = "%" in metric
        candidates = [n for n in unique if ("%" in n) == search_has_pct]
        matches = difflib.get_close_matches(metric, candidates, n=1, cutoff=cutoff)
        if matches:
            return matches[0]
        if normalizer:
            for synonym in normalizer.get_synonyms(metric):
                result = BaseMetricsBuilder.resolve_metric(index, synonym, cutoff=cutoff)
                if result:
                    return result
        return None

    @staticmethod
    def get(
        df: pd.DataFrame | None,
        metric: str,
        occurrence: int = 0,
        col: int = 0,
        normalizer: NameNormalizer | None = None,
    ) -> str | None:
        """Return cell value using fuzzy metric matching. Returns None on any miss."""
        if df is None or df.empty or col >= len(df.columns):
            return None
        resolved = BaseMetricsBuilder.resolve_metric(df.index, metric, normalizer=normalizer)
        if resolved is None:
            return None
        rows = df.loc[[resolved]]
        if len(rows) <= occurrence:
            return None
        val = str(rows.iloc[occurrence, col]).strip()
        return val if val not in ("", "None") else None

    @staticmethod
    def col1_is_sequential(tables: dict[str, pd.DataFrame]) -> bool:
        """True when col 1 is the sequential prior quarter (~3 months before col 0)."""
        is_ = tables.get("income_statement")
        if is_ is None or is_.empty or len(is_.columns) < 2:
            return False

        def _parse_col_date(name: str) -> int | None:
            m = re.match(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", name)
            if not m:
                return None
            month = _MONTH_NUM.get(m.group(1))
            if month is None:
                return None
            return int(m.group(3)) * 12 + month

        col0 = _parse_col_date(is_.columns[0])
        col1 = _parse_col_date(is_.columns[1])
        if col0 is None or col1 is None:
            return False
        diff = col0 - col1
        return 1 <= diff <= 6

    # ── Validation ─────────────────────────────────────────────────────────

    def cross_check(
        self,
        quarter: str,
        prior_in_current: dict[str, str | None],
        prev_current: dict[str, str | None],
        report: ValidationReport,
        keys: list[str] | None = None,
    ) -> None:
        """Layer 1: compare col-1 values from quarter Q against col-0 from Q-1."""
        check_keys = keys if keys is not None else self.CROSS_CHECK_KEYS
        for key in check_keys:
            val_prior = parse_number(prior_in_current.get(key))
            val_prev = parse_number(prev_current.get(key))
            if val_prior is None or val_prev is None:
                continue
            denom = max(abs(val_prev), 1e-9)
            if abs(val_prev) < 10:
                ok = abs(val_prior - val_prev) < _EPS_ABS_TOLERANCE
                pct = abs(val_prior - val_prev)
            else:
                pct = abs(val_prior - val_prev) / denom
                ok = pct < _CROSS_CHECK_TOLERANCE
            if not ok:
                report.add(ValidationIssue(
                    quarter=quarter,
                    layer=1,
                    check=f"cross_check:{key}",
                    expected=val_prev,
                    actual=val_prior,
                    pct_diff=pct,
                ))

    def consistency_check(
        self,
        quarter: str,
        metrics: dict[str, float | None],
        report: ValidationReport,
    ) -> None:
        """Layer 2: arithmetic consistency checks within a single quarter."""

        def _check_approx(check_name: str, expected: float | None, actual: float | None, tol: float = 0.005, strict: bool = False) -> None:
            if expected is None or actual is None:
                return
            denom = max(abs(expected), 1e-9)
            diff = abs(expected - actual) / denom
            if diff > tol:
                report.add(ValidationIssue(
                    quarter=quarter, layer=2, check=check_name,
                    expected=expected, actual=actual,
                    pct_diff=None if strict else diff,
                ))

        rev = metrics.get("gaap_revenue")
        gp = metrics.get("gaap_gross_profit")
        oi = metrics.get("gaap_operating_income")
        ni = metrics.get("gaap_net_income")
        eps = metrics.get("gaap_diluted_earnings_per_share")
        non_gaap_gp = metrics.get("non_gaap_gross_profit")
        gm_pct = metrics.get("gaap_gross_margin_pct")

        # Gross margin consistency: reported % vs computed (absolute ±0.5pp tolerance for rounding)
        if rev and gp and gm_pct is not None:
            computed_gm = gp / rev
            if abs(computed_gm - gm_pct) > 0.005:
                pct = abs(computed_gm - gm_pct) / max(abs(computed_gm), 1e-9)
                report.add(ValidationIssue(
                    quarter=quarter, layer=2, check="margin_consistency:gross_margin",
                    expected=computed_gm, actual=gm_pct, pct_diff=pct,
                ))

        # Non-GAAP gross profit >= GAAP gross profit (adjustments are additive)
        if gp is not None and non_gaap_gp is not None and non_gaap_gp < gp - 1:
            report.add(ValidationIssue(
                quarter=quarter, layer=2,
                check="strict:non_gaap_gp_lt_gaap_gp",
                expected=gp, actual=non_gaap_gp,
            ))

        # Revenue must be positive
        if rev is not None and rev <= 0:
            report.add(ValidationIssue(
                quarter=quarter, layer=2,
                check="strict:revenue_nonpositive",
                actual=rev,
            ))

        # EPS sign must match net income sign
        if ni is not None and eps is not None:
            if (ni > 0) != (eps > 0):
                report.add(ValidationIssue(
                    quarter=quarter, layer=2,
                    check="strict:eps_sign_mismatch",
                    expected=ni, actual=eps,
                ))

    def sanity_check_df(self, df: pd.DataFrame, report: ValidationReport) -> None:
        """Layer 3: outlier detection across the full time series."""
        if "gaap_revenue" in df.columns:
            rev = df["gaap_revenue"].apply(lambda x: parse_number(str(x)) if pd.notna(x) else None).astype(float)
            pct_change = rev.pct_change().abs()
            for quarter, val in pct_change.items():
                if pd.notna(val) and val > 0.80:
                    report.add(ValidationIssue(
                        quarter=str(quarter), layer=3,
                        check="sanity:revenue_qoq_gt_80pct",
                        pct_diff=val,
                    ))

        for col in ["gaap_gross_margin_pct", "non_gaap_gross_margin_pct"]:
            if col in df.columns:
                gm = df[col].apply(lambda x: parse_percent(str(x)) if pd.notna(x) else None).astype(float)
                for quarter, val in gm.items():
                    if pd.notna(val) and not (0.0 <= val <= 1.0):
                        report.add(ValidationIssue(
                            quarter=str(quarter), layer=3,
                            check=f"sanity:margin_out_of_range:{col}",
                            actual=val,
                        ))

    # ── Main orchestrator ──────────────────────────────────────────────────

    def build_dataframe(
        self,
        reports_dir: Path,
        normalizer: NameNormalizer | None = None,
        run_check: bool = True,
        company: str = "",
    ) -> tuple[pd.DataFrame, ValidationReport]:
        """Iterate quarter directories, extract metrics, validate, return DataFrame."""
        report = ValidationReport(company=company)
        quarters = sorted(p.name for p in reports_dir.iterdir() if p.is_dir())
        records: list[dict] = []
        prev_current: dict[str, str | None] | None = None

        for q in quarters:
            print(f"  {q} … ", end="", flush=True)
            try:
                q_dir = reports_dir / q
                pr_pdf = q_dir / "press_release.pdf"
                ft_pdf = q_dir / "financial_tables.pdf"

                # Always call parsers; each checks internally for file existence
                # (supports PDF, HTML siblings, or alternative filenames per company)
                pr_tables = self.press_release_parser.parse(pr_pdf)
                ft_tables = self.financial_tables_parser.parse(ft_pdf)
                all_tables = {**ft_tables, **pr_tables}

                current_raw = self.extract_raw_metrics(all_tables, col=0, quarter=q)
                prior_raw = self.extract_raw_metrics(all_tables, col=1, quarter=q)
                is_seq = self.col1_is_sequential(ft_tables if ft_tables else pr_tables)

                # Normalize raw strings → floats → formatted strings (≤5 decimal places)
                current_floats = self._convert_to_floats(current_raw, normalizer)
                records.append(self._normalize_to_strings(current_raw, normalizer))

                unresolved = [k for k, v in current_raw.items() if v is None and k != "quarter"]
                if unresolved:
                    print(f"unresolved({len(unresolved)}): {unresolved[:5]}{'…' if len(unresolved) > 5 else ''}")

                if run_check:
                    if prev_current is not None and is_seq:
                        self.cross_check(q, prior_raw, prev_current, report)
                    self.consistency_check(q, current_floats, report)

                cross_issues = sum(1 for i in report.issues if i.quarter == q and i.layer == 1)
                consist_issues = sum(1 for i in report.issues if i.quarter == q and i.layer == 2)
                if cross_issues or consist_issues:
                    print(f"WARN: {cross_issues} cross-check, {consist_issues} consistency issue(s)")
                elif not unresolved:
                    print("OK")

                prev_current = current_raw

            except Exception as exc:
                print(f"ERROR: {exc}")
                prev_current = None

        df = pd.DataFrame(records)
        if "quarter" in df.columns:
            df = df.set_index("quarter")

        if run_check:
            self.sanity_check_df(df, report)

        return df, report

    @staticmethod
    def _fmt(v: float | None) -> str:
        """Format a float as a clean string with at most 5 decimal places."""
        if v is None or (isinstance(v, float) and (v != v)):  # NaN check
            return ""
        if v == int(v) and abs(v) < 1e15:
            return str(int(v))
        return f"{v:.5f}".rstrip("0").rstrip(".")

    def _convert_to_floats(
        self,
        raw: dict[str, str | None],
        normalizer: NameNormalizer | None,
    ) -> dict[str, float | None]:
        """Convert raw string values to floats using normalizer is_percentage metadata."""
        result: dict[str, float | None] = {}
        for key, val in raw.items():
            if key == "quarter":
                result[key] = val  # type: ignore[assignment]
                continue
            if normalizer and normalizer.is_percentage(key):
                result[key] = parse_percent(val)
            else:
                result[key] = parse_number(val)
        return result

    def _normalize_to_strings(
        self,
        raw: dict[str, str | None],
        normalizer: NameNormalizer | None,
    ) -> dict[str, str]:
        """Parse raw strings → floats → formatted strings (≤5 decimal places)."""
        floats = self._convert_to_floats(raw, normalizer)
        result: dict[str, str] = {}
        for key, val in floats.items():
            if key == "quarter":
                result[key] = str(val) if val is not None else ""
            else:
                result[key] = self._fmt(val)
        return result
