"""Microsoft metrics builder."""

from __future__ import annotations

import pandas as pd

from ...base.metrics_builder import BaseMetricsBuilder
from ...base.parser import BasePressReleaseParser, BaseFinancialTablesParser
from .parser import MsftPressReleaseParser, MsftFinancialTablesParser


class MsftMetricsBuilder(BaseMetricsBuilder):

    def __init__(self) -> None:
        self._pr_parser = MsftPressReleaseParser()
        self._ft_parser = MsftFinancialTablesParser()

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

        gaap    = tables.get("gaap")
        non_gaap = tables.get("non_gaap")
        segment = tables.get("segment")

        rec["gaap_revenue"]          = g(gaap, "Revenue", col=col)
        rec["gaap_cost_of_revenue"]  = g(gaap, "Cost of revenue", col=col)
        rec["gaap_gross_profit"]     = g(gaap, "Gross margin", col=col) or g(gaap, "Gross profit", col=col)
        rec["gaap_gross_margin_pct"] = g(gaap, "Gross margin %", col=col)
        rec["gaap_research_development_expense"] = g(gaap, "Research and development", col=col)
        rec["gaap_selling_general_admin_expense"] = g(gaap, "Sales and marketing", col=col)
        rec["gaap_total_operating_expenses"]      = g(gaap, "Total operating expenses", col=col)
        rec["gaap_operating_income"] = g(gaap, "Operating income", col=col)
        rec["gaap_operating_margin_pct"] = g(gaap, "Operating margin %", col=col)
        rec["gaap_interest_expense"] = g(gaap, "Interest expense", col=col)
        rec["gaap_net_income"]       = g(gaap, "Net income", col=col)
        rec["gaap_diluted_earnings_per_share"] = g(gaap, "Diluted earnings per share", col=col)
        rec["gaap_diluted_shares"]   = g(gaap, "Diluted weighted average shares outstanding", col=col)

        # Non-GAAP
        rec["non_gaap_gross_profit"]     = g(non_gaap, "Gross margin", col=col)
        rec["non_gaap_gross_margin_pct"] = g(non_gaap, "Gross margin %", col=col)
        rec["non_gaap_operating_income"] = g(non_gaap, "Operating income", col=col)
        rec["non_gaap_operating_margin_pct"] = g(non_gaap, "Operating margin %", col=col)
        rec["non_gaap_net_income"]       = g(non_gaap, "Net income", col=col)
        rec["non_gaap_diluted_earnings_per_share"] = g(non_gaap, "Diluted earnings per share", col=col)

        # Segments
        rec["seg_intelligent_cloud_revenue"]          = g(segment, "Intelligent Cloud", col=col)
        rec["seg_intelligent_cloud_operating_income"] = g(segment, "Intelligent Cloud operating income", col=col)
        rec["seg_productivity_biz_revenue"]           = g(segment, "Productivity and Business Processes", col=col)
        rec["seg_productivity_biz_operating_income"]  = g(segment, "Productivity and Business Processes operating income", col=col)
        rec["seg_more_personal_computing_revenue"]    = g(segment, "More Personal Computing", col=col)
        rec["seg_more_personal_computing_operating_income"] = g(segment, "More Personal Computing operating income", col=col)
        rec["seg_azure_growth_pct"] = g(segment, "Azure and other cloud services", col=col)
        rec["seg_m365_commercial_revenue"] = g(gaap, "Microsoft 365 Commercial products and cloud services", col=col)

        # Balance sheet and cash flow not available from press release alone
        for key in [
            "gaap_cash", "gaap_short_term_investments", "gaap_accounts_receivable",
            "gaap_inventories", "gaap_total_current_assets", "gaap_total_assets",
            "gaap_total_current_liabilities", "gaap_long_term_debt",
            "gaap_stockholders_equity", "gaap_operating_cash_flow",
            "gaap_capital_expenditure",
        ]:
            rec[key] = None

        return rec
