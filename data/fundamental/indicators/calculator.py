"""FundamentalIndicatorCalculator: compute derived indicators from raw metric DataFrame."""

from __future__ import annotations

import pandas as pd

from ..base.number_parser import parse_number, parse_percent


def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    """Element-wise division; returns NaN where denominator is 0 or NaN."""
    return a.div(b.where(b != 0))


def _to_num(series: pd.Series) -> pd.Series:
    """Convert a Series of raw strings (e.g. '1,786', '(23)', '$3.6') to floats."""
    return series.apply(lambda x: parse_number(str(x)) if pd.notna(x) and str(x) not in ("", "None") else None).astype(float)


def _ttm_sum(series: pd.Series) -> pd.Series:
    """Trailing 12-month sum (4-quarter rolling); NaN if fewer than 4 quarters available."""
    return series.rolling(window=4, min_periods=4).sum()


def _ttm_avg(series: pd.Series) -> pd.Series:
    """Average of beginning and ending values over a 4-quarter TTM window."""
    return (series + series.shift(4)) / 2


class FundamentalIndicatorCalculator:
    """Appends ind_* columns to a raw-metrics DataFrame."""

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return df with all ind_* indicator columns appended."""
        out = df.copy()

        def col(name: str) -> pd.Series:
            if name in out.columns:
                return _to_num(out[name])
            return pd.Series([float("nan")] * len(out), index=out.index)

        rev   = col("gaap_revenue")
        gp    = col("gaap_gross_profit")
        oi    = col("gaap_operating_income")
        ni    = col("gaap_net_income")
        eq    = col("gaap_stockholders_equity")
        ta    = col("gaap_total_assets")
        ca    = col("gaap_total_current_assets")
        cl    = col("gaap_total_current_liabilities")
        inv   = col("gaap_inventories")
        ltd   = col("gaap_long_term_debt")
        ie    = col("gaap_interest_expense")
        ocf   = col("gaap_operating_cash_flow")
        capex = col("gaap_capital_expenditure")
        eps   = col("gaap_diluted_earnings_per_share")

        ng_gp = col("non_gaap_gross_profit")
        ng_oi = col("non_gaap_operating_income")
        ng_ni = col("non_gaap_net_income")

        cash_inv = col("cash_and_short_term_investments")
        fcf_raw  = col("free_cash_flow")

        # Compute FCF from components if not directly available
        fcf = fcf_raw.where(fcf_raw.notna(), ocf + capex.where(capex < 0, -capex.abs()))

        # ── Profitability ──────────────────────────────────────────────────
        out["ind_gross_margin"]            = _safe_div(gp, rev)
        out["ind_non_gaap_gross_margin"]   = _safe_div(ng_gp, rev)
        out["ind_operating_margin"]        = _safe_div(oi, rev)
        out["ind_non_gaap_operating_margin"] = _safe_div(ng_oi, rev)
        out["ind_net_margin"]              = _safe_div(ni, rev)
        out["ind_non_gaap_net_margin"]     = _safe_div(ng_ni, rev)

        # ── Return metrics (TTM) ───────────────────────────────────────────
        ttm_ni  = _ttm_sum(ni)
        avg_eq  = _ttm_avg(eq)
        avg_ta  = _ttm_avg(ta)
        out["ind_roe"] = _safe_div(ttm_ni, avg_eq)
        out["ind_roa"] = _safe_div(ttm_ni, avg_ta)

        # ── Liquidity ──────────────────────────────────────────────────────
        out["ind_current_ratio"] = _safe_div(ca, cl)
        out["ind_quick_ratio"]   = _safe_div(ca - inv, cl)

        # ── Leverage ──────────────────────────────────────────────────────
        out["ind_debt_to_equity"]   = _safe_div(ltd, eq)
        out["ind_net_debt"]         = ltd - cash_inv           # dollar amount
        out["ind_interest_coverage"] = _safe_div(oi, ie.abs())

        # ── Cash Flow Quality ──────────────────────────────────────────────
        out["ind_ocf_margin"]       = _safe_div(ocf, rev)
        out["ind_fcf_margin"]       = _safe_div(fcf, rev)
        out["ind_fcf_conversion"]   = _safe_div(fcf, ni)
        out["ind_capex_intensity"]  = _safe_div(capex.abs(), rev)

        # ── Growth ────────────────────────────────────────────────────────
        out["ind_revenue_qoq"] = rev.pct_change(periods=1)
        out["ind_revenue_yoy"] = rev.pct_change(periods=4)
        out["ind_eps_yoy"]     = eps.pct_change(periods=4)

        # Format all ind_* columns as strings (≤5 decimal places)
        def _fmt(v: object) -> str:
            if v is None or (isinstance(v, float) and v != v):
                return ""
            f = float(v)  # type: ignore[arg-type]
            if f == int(f) and abs(f) < 1e15:
                return str(int(f))
            return f"{f:.5f}".rstrip("0").rstrip(".")

        for c in out.columns:
            if c.startswith("ind_"):
                out[c] = out[c].apply(_fmt)

        return out

    def validate(self, df: pd.DataFrame) -> list[str]:
        """Return list of sanity warning strings for the indicator DataFrame."""
        warnings: list[str] = []

        def _check(col_name: str, lo: float, hi: float, msg: str) -> None:
            if col_name not in df.columns:
                return
            s = pd.to_numeric(df[col_name], errors="coerce")
            bad = s[(s < lo) | (s > hi)].dropna()
            for q, v in bad.items():
                warnings.append(f"[{q}] {msg}: {v:.4g}")

        _check("ind_gross_margin", 0.0, 1.0, "gross_margin out of [0,1]")
        _check("ind_non_gaap_gross_margin", 0.0, 1.0, "non_gaap_gross_margin out of [0,1]")
        _check("ind_operating_margin", -2.0, 1.0, "operating_margin out of [-2,1]")
        _check("ind_net_margin", -5.0, 1.0, "net_margin out of [-5,1]")

        if "ind_revenue_qoq" in df.columns:
            s = pd.to_numeric(df["ind_revenue_qoq"], errors="coerce")
            big = s[s.abs() > 0.80].dropna()
            for q, v in big.items():
                warnings.append(f"[{q}] revenue_qoq={v:.1%} — possible scale error")

        return warnings
