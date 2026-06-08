"""Circle Internet Financial metrics builder."""

from __future__ import annotations

import pandas as pd

from ...base.metrics_builder import BaseMetricsBuilder
from ...base.parser import BasePressReleaseParser, BaseFinancialTablesParser
from .parser import CirclePressReleaseParser, CircleFinancialTablesParser


class CircleMetricsBuilder(BaseMetricsBuilder):

    def __init__(self) -> None:
        self._pr_parser = CirclePressReleaseParser()
        self._ft_parser = CircleFinancialTablesParser()

    @property
    def press_release_parser(self) -> BasePressReleaseParser:
        return self._pr_parser

    @property
    def financial_tables_parser(self) -> BaseFinancialTablesParser:
        return self._ft_parser

    def extract_raw_metrics(
        self,
        tables: dict[str, pd.DataFrame],
        col: int,
        quarter: str,
    ) -> dict[str, str | None]:
        rec: dict[str, str | None] = {"quarter": quarter}
        g = self.get

        gaap     = tables.get("gaap")
        non_gaap = tables.get("non_gaap")
        segment  = tables.get("segment")
        is_      = tables.get("income_statement")
        bs       = tables.get("balance_sheet")
        cf       = tables.get("cash_flow")

        src_is = is_ if is_ is not None else gaap

        # Circle income statement is bank-like: primary revenue is net interest income
        rec["gaap_revenue"] = (
            g(src_is, "Total revenue", col=col)
            or g(src_is, "Revenue", col=col)
            or g(gaap, "Total revenue", col=col)
        )
        rec["gaap_gross_profit"] = g(src_is, "Gross profit", col=col)
        rec["gaap_operating_income"] = g(src_is, "Income from operations", col=col) or g(gaap, "Operating income", col=col)
        rec["gaap_interest_expense"] = g(src_is, "Interest expense", col=col)
        rec["gaap_net_income"]       = g(src_is, "Net income (loss)", col=col) or g(src_is, "Net income", col=col)
        rec["gaap_diluted_earnings_per_share"] = g(src_is, "Diluted earnings (loss) per share", col=col) or g(src_is, "Diluted", col=col)
        rec["gaap_diluted_shares"] = g(src_is, "Diluted weighted average shares outstanding", col=col)

        # Non-GAAP (Circle: Adjusted EBITDA is the key non-GAAP metric)
        rec["non_gaap_adjusted_ebitda"] = g(non_gaap, "Adjusted EBITDA", col=col)
        rec["non_gaap_net_income"] = g(non_gaap, "Non-GAAP net income", col=col)

        # Balance sheet
        rec["gaap_cash"]                      = g(bs, "Cash and cash equivalents", col=col)
        rec["gaap_total_current_assets"]      = g(bs, "Total current assets", col=col)
        rec["gaap_total_assets"]              = g(bs, "Total assets", col=col)
        rec["gaap_total_current_liabilities"] = g(bs, "Total current liabilities", col=col)
        rec["gaap_long_term_debt"]            = g(bs, "Long-term debt", col=col)
        rec["gaap_stockholders_equity"]       = g(bs, "Total stockholders' equity", col=col) or g(bs, "Total equity", col=col)

        # Cash flow
        rec["gaap_operating_cash_flow"] = g(cf, "Net cash provided by operating activities", col=col)
        rec["gaap_capital_expenditure"] = g(cf, "Purchases of property and equipment", col=col)

        # Circle-specific segment / KPI metrics
        seg_src = segment if segment is not None else gaap
        rec["seg_usdc_reserve_income"]         = (
            g(seg_src, "Net interest income", col=col)
            or g(seg_src, "USDC net reserve income", col=col)
        )
        rec["seg_subscription_services_revenue"] = (
            g(seg_src, "Subscription and services revenue", col=col)
            or g(seg_src, "SaaS revenue", col=col)
        )
        # USDC circulation: a balance KPI (billions), not a revenue line
        rec["seg_usdc_circulation"] = (
            g(seg_src, "USDC in circulation", col=col)
            or g(seg_src, "Total USDC in circulation", col=col)
        )
        rec["seg_reserve_yield_pct"] = (
            g(seg_src, "Effective reserve yield", col=col)
            or g(seg_src, "Reserve yield", col=col)
        )

        return rec
