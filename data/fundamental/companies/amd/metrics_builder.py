"""AMD metrics builder: extracts canonical financial metrics from parsed tables."""

from __future__ import annotations

import pandas as pd

from ...base.metrics_builder import BaseMetricsBuilder
from ...base.parser import BasePressReleaseParser, BaseFinancialTablesParser
from .parser import AmdPressReleaseParser, AmdFinancialTablesParser

class AmdMetricsBuilder(BaseMetricsBuilder):

    def __init__(self) -> None:
        self._pr_parser = AmdPressReleaseParser()
        self._ft_parser = AmdFinancialTablesParser()

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
        g = self.get  # shorthand

        # Primary GAAP income statement source: financial_tables.pdf (clean labels, sequential prior)
        # Fallback: press_release["gaap"] for any metrics not found in financial_tables
        is_  = tables.get("income_statement")
        gaap = tables.get("gaap")

        # Use financial_tables income_statement as primary; press_release gaap as fallback
        src_is = is_ if is_ is not None else gaap

        rec["gaap_revenue"]          = (
            g(src_is, "Net revenue", col=col)
            or g(gaap, "Revenue", col=col)
            or g(gaap, "Net revenue", col=col)
        )
        rec["gaap_gross_profit"]     = (
            g(src_is, "Gross profit", col=col)
            or g(src_is, "Gross margin", col=col)   # pre-2022 label in financial_tables
            or g(gaap, "Gross profit", col=col)
            or g(gaap, "Gross margin", col=col)
        )
        rec["gaap_gross_margin_pct"] = (
            g(src_is, "Gross margin %", col=col)
            or g(gaap, "Gross margin %", col=col)
        )
        rec["gaap_research_development_expense"] = (
            g(src_is, "Research and development", col=col)
            or g(gaap, "Research and development", col=col)
        )
        rec["gaap_selling_general_admin_expense"] = (
            g(src_is, "Marketing, general and administrative", col=col)
            or g(gaap, "Marketing, general and administrative", col=col)
        )
        rec["gaap_operating_income"] = (
            g(src_is, "Operating income", col=col)
            or g(src_is, "Operating income (loss)", col=col)
            or g(gaap, "Operating income", col=col)
        )
        rec["gaap_operating_margin_pct"] = (
            g(src_is, "Operating income %", col=col)
            or g(gaap, "Operating income %", col=col)
        )
        rec["gaap_interest_expense"] = (
            g(src_is, "Interest expense", col=col)
            or g(gaap, "Interest expense", col=col)
        )
        rec["gaap_net_income"] = (
            g(src_is, "Net income", col=col)
            or g(src_is, "Net income (loss)", col=col)
            or g(gaap, "Net income", col=col)
            or g(gaap, "Net income (loss)", col=col)
        )

        # EPS / shares format detection:
        #   Old format (pre-2025): "Diluted" row appears twice — occ=0 is EPS, occ=1 is shares
        #   New format (2025+): "Diluted earnings per share" = EPS, standalone "Diluted" = shares
        _is_new_eps_format = is_ is not None and (
            "Diluted earnings per share" in is_.index
            or "Basic earnings per share" in is_.index
        )
        if _is_new_eps_format:
            rec["gaap_diluted_earnings_per_share"] = (
                g(is_, "Diluted earnings per share", col=col)
                or g(gaap, "Diluted earnings per share", col=col)
            )
            rec["gaap_basic_shares"]   = g(is_, "Basic",   occurrence=0, col=col)
            rec["gaap_diluted_shares"] = g(is_, "Diluted", occurrence=0, col=col)
        else:
            # Old format: "Diluted" occ=0 is EPS, occ=1 is shares
            rec["gaap_diluted_earnings_per_share"] = (
                g(is_, "Diluted", occurrence=0, col=col)
                or g(gaap, "Diluted earnings per share", col=col)
                or g(gaap, "Diluted", occurrence=0, col=col)
            )
            rec["gaap_basic_shares"] = (
                g(is_, "Basic",   occurrence=1, col=col)
                or g(gaap, "Basic",   occurrence=1, col=col)
            )
            rec["gaap_diluted_shares"] = (
                g(is_, "Diluted", occurrence=1, col=col)
                or g(gaap, "Diluted", occurrence=1, col=col)
            )

        # ── Non-GAAP (from press_release["non_gaap"] and financial_tables["gaap_to_non_gaap"]) ─
        non_gaap = tables.get("non_gaap")
        gng = tables.get("gaap_to_non_gaap")

        # Prefer non_gaap table from press release; fall back to reconciliation table
        rec["non_gaap_gross_profit"]   = (
            g(non_gaap, "Gross profit", col=col)
            or g(gng, "Non-GAAP gross profit", col=col)
        )
        rec["non_gaap_gross_margin_pct"] = (
            g(non_gaap, "Gross margin %", col=col)
            or g(gng, "Non-GAAP gross margin %", col=col)
        )
        rec["non_gaap_operating_expenses"] = g(gng, "Non-GAAP operating expenses", col=col)
        rec["non_gaap_operating_expense_margin_pct"] = g(gng, "Non-GAAP operating expenses/revenue %", col=col)
        rec["non_gaap_operating_income"] = (
            g(non_gaap, "Operating income", col=col)
            or g(gng, "Non-GAAP operating income", col=col)
        )
        rec["non_gaap_operating_margin_pct"] = (
            g(non_gaap, "Operating income %", col=col)
            or g(gng, "Non-GAAP operating margin %", col=col)
        )
        rec["non_gaap_net_income"] = g(non_gaap, "Net income", col=col)
        rec["non_gaap_diluted_earnings_per_share"] = g(non_gaap, "Diluted earnings per share", col=col)

        # AMD EPS reconciliation table (Amt | EPS alternating columns)
        eps = tables.get("gaap_to_non_gaap_eps")
        nongaap_row = "Non-GAAP net income / earnings per share"
        eps_amt_col = col * 2
        eps_eps_col = col * 2 + 1
        if eps is not None and not eps.empty and self.resolve_metric(eps.index, nongaap_row) is not None:
            if rec["non_gaap_net_income"] is None:
                rec["non_gaap_net_income"] = g(eps, nongaap_row, col=eps_amt_col)
            if rec["non_gaap_diluted_earnings_per_share"] is None:
                rec["non_gaap_diluted_earnings_per_share"] = g(eps, nongaap_row, col=eps_eps_col)

        # ── GAAP opex: financial_tables income_statement primary, reconciliation fallback ──
        rec["gaap_total_operating_expenses"] = (
            g(is_, "Total operating expenses", col=col)
            or g(gng, "GAAP operating expenses", col=col)
        )

        # ── Adjusted EBITDA ──────────────────────────────────────────────────
        ebitda = tables.get("adjusted_ebitda")
        segment = tables.get("segment_data")
        rec["non_gaap_adjusted_ebitda"] = (
            g(ebitda, "Adjusted EBITDA", col=col)
            or g(segment, "Adjusted EBITDA", col=col)
        )

        # ── Balance Sheet ────────────────────────────────────────────────────
        bs = tables.get("balance_sheet")
        rec["gaap_cash"]                      = g(bs, "Cash and cash equivalents", col=col)
        rec["gaap_short_term_investments"]    = g(bs, "Short-term investments", col=col)
        rec["gaap_accounts_receivable"]       = g(bs, "Accounts receivable, net", col=col)
        rec["gaap_inventories"]               = g(bs, "Inventories", col=col)
        rec["gaap_total_current_assets"]      = g(bs, "Total current assets", col=col)
        rec["gaap_total_assets"]              = g(bs, "Total Assets", col=col)
        rec["gaap_total_current_liabilities"] = g(bs, "Total current liabilities", col=col)
        rec["gaap_long_term_debt"]            = (
            g(bs, "Long-term debt", col=col)
            or g(bs, "Long-term debt, net", col=col)
            or g(bs, "Long-term debt, net of current portion", col=col)
        )
        rec["gaap_stockholders_equity"] = g(bs, "Total stockholders' equity", col=col)

        # ── Cash Flow ─────────────────────────────────────────────────────────
        cf = tables.get("cash_flow")
        rec["gaap_operating_cash_flow"] = (
            g(cf, "Net cash provided by operating activities of continuing operations", col=col)
            or g(cf, "Net cash provided by operating activities", col=col)
            or g(cf, "Operating activities", col=col)
        )
        rec["gaap_capital_expenditure"] = g(cf, "Purchases of property and equipment", col=col)

        # ── Segment Data ─────────────────────────────────────────────────────
        # "Data Center Segment" appears twice: occurrence 0 = revenue, 1 = op income
        rec["seg_datacenter_revenue"]          = g(segment, "Data Center Segment", occurrence=0, col=col)
        rec["seg_client_revenue"]              = g(segment, "Client", col=col)
        rec["seg_gaming_revenue"]              = g(segment, "Gaming", col=col)
        rec["seg_embedded_revenue"]            = g(segment, "Embedded Segment", occurrence=0, col=col)
        rec["seg_datacenter_operating_income"] = g(segment, "Data Center Segment", occurrence=1, col=col)
        rec["seg_client_operating_income"]     = g(segment, "Client and Gaming Segment", col=col)
        rec["seg_embedded_operating_income"]   = g(segment, "Embedded Segment", occurrence=1, col=col)

        rec["cash_and_short_term_investments"] = (
            g(segment, "Cash, cash equivalents and short-term investments", col=col)
            or g(segment, "Cash, cash equivalents and marketable securities", col=col)
        )
        rec["free_cash_flow"] = (
            g(tables.get("free_cash_flow"), "Free cash flow", col=col)
            or g(segment, "Free cash flow", col=col)
        )
        rec["total_debt"]  = g(segment, "Total debt", col=col)
        rec["gaap_capital_expenditure"] = (
            rec["gaap_capital_expenditure"]
            or g(segment, "Capital expenditures", col=col)
        )

        rec["operating_cash_flow_margin_pct"] = (
            g(tables.get("free_cash_flow"), "Operating cash flow margin % from continuing operations", col=col)
            or g(tables.get("free_cash_flow"), "Operating cash flow margin %", col=col)
        )
        rec["free_cash_flow_margin_pct"] = g(tables.get("free_cash_flow"), "Free cash flow margin %", col=col)

        return rec
