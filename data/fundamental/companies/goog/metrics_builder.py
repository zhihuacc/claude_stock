"""Google/Alphabet metrics builder."""

from __future__ import annotations

import pandas as pd

from ...base.metrics_builder import BaseMetricsBuilder
from ...base.parser import BasePressReleaseParser, BaseFinancialTablesParser
from .parser import GoogPressReleaseParser, GoogFinancialTablesParser


class GoogMetricsBuilder(BaseMetricsBuilder):

    def __init__(self) -> None:
        self._pr_parser = GoogPressReleaseParser()
        self._ft_parser = GoogFinancialTablesParser()

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

        rec["gaap_revenue"]          = g(src_is, "Revenues", col=col) or g(gaap, "Revenues", col=col)
        rec["gaap_cost_of_revenue"]  = g(src_is, "Cost of revenues", col=col)
        rec["gaap_gross_profit"]     = g(src_is, "Gross profit", col=col)
        rec["gaap_research_development_expense"] = g(src_is, "Research and development", col=col)
        rec["gaap_selling_general_admin_expense"] = g(src_is, "Sales and marketing", col=col)
        rec["gaap_total_operating_expenses"]      = g(src_is, "Total costs and expenses", col=col)
        rec["gaap_operating_income"] = g(src_is, "Income from operations", col=col) or g(gaap, "Income from operations", col=col)
        rec["gaap_interest_expense"] = g(src_is, "Interest income (expense), net", col=col)
        rec["gaap_net_income"]       = g(src_is, "Net income", col=col) or g(gaap, "Net income", col=col)
        rec["gaap_diluted_earnings_per_share"] = (
            g(src_is, "Diluted earnings per share", col=col)
            or g(gaap, "Diluted net income per share", col=col)
        )
        rec["gaap_diluted_shares"] = g(src_is, "Diluted weighted average shares outstanding", col=col)

        # Non-GAAP (Google's primary adjustment is SBC)
        rec["non_gaap_operating_income"] = g(non_gaap, "Non-GAAP operating income", col=col)
        rec["non_gaap_net_income"]       = g(non_gaap, "Non-GAAP net income", col=col)
        rec["non_gaap_diluted_earnings_per_share"] = g(non_gaap, "Non-GAAP diluted EPS", col=col) or g(non_gaap, "Diluted earnings per share", col=col)

        # Balance sheet
        rec["gaap_cash"]                      = g(bs, "Cash and cash equivalents", col=col)
        rec["gaap_short_term_investments"]    = g(bs, "Short-term investments", col=col)
        rec["gaap_accounts_receivable"]       = g(bs, "Accounts receivable, net", col=col)
        rec["gaap_total_current_assets"]      = g(bs, "Total current assets", col=col)
        rec["gaap_total_assets"]              = g(bs, "Total assets", col=col)
        rec["gaap_total_current_liabilities"] = g(bs, "Total current liabilities", col=col)
        rec["gaap_long_term_debt"]            = g(bs, "Long-term debt", col=col)
        rec["gaap_stockholders_equity"]       = g(bs, "Total stockholders' equity", col=col) or g(bs, "Total equity", col=col)

        # Cash flow
        rec["gaap_operating_cash_flow"] = g(cf, "Net cash provided by operating activities", col=col)
        rec["gaap_capital_expenditure"] = g(cf, "Purchases of property and equipment", col=col)

        # Segments (GOOG revenue breakdown)
        seg_src = segment if segment is not None else gaap
        rec["seg_google_search_revenue"]         = g(seg_src, "Google Search & other", col=col) or g(seg_src, "Google search & other", col=col)
        rec["seg_youtube_ads_revenue"]           = g(seg_src, "YouTube ads", col=col)
        rec["seg_google_network_revenue"]        = g(seg_src, "Google Network", col=col) or g(seg_src, "Google Network Members' properties", col=col)
        rec["seg_google_subscriptions_revenue"]  = g(seg_src, "Google subscriptions, platforms, and devices", col=col) or g(seg_src, "Other Google revenues", col=col)
        rec["seg_google_services_total_revenue"] = g(seg_src, "Google Services", col=col)
        rec["seg_google_services_operating_income"] = g(seg_src, "Google Services operating income", col=col)
        rec["seg_google_cloud_revenue"]          = g(seg_src, "Google Cloud", col=col)
        rec["seg_google_cloud_operating_income"] = g(seg_src, "Google Cloud operating income", col=col)
        rec["seg_other_bets_revenue"]            = g(seg_src, "Other Bets", col=col)

        rec["cash_and_short_term_investments"] = None  # computed from cash + short_term_investments

        return rec
