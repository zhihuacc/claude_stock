"""NVIDIA metrics builder.

Data sources per table key (from press_release.html + cfo_commentary.html):

  gaap            — GAAP quarterly summary: Revenue, Gross margin %, Op. income,
                    Net income, Diluted EPS  (col=0 current, col=1 SEQ prior Q)
  non_gaap        — Non-GAAP quarterly summary (same structure)
  income_statement — Full IS: R&D, SGA, interest expense, shares
                     col=1 = YoY prior — NOT used for cross-check
  balance_sheet   — BS items (col=0 current, col=1 fiscal year-end prior)
  cash_flow       — CF items (col=0 current, col=1 YoY prior)
  reconciliation  — GAAP/Non-GAAP reconciliation (col=0, col=1 seq prior, col=2 yoy)
  segment_reportable — Compute & Networking / Graphics (new) or GPU Business / Tegra (old)
  segment_market  — Data Center / Edge Computing (new) or Gaming / ProViz / DC / Auto / OEM (old)

Cross-check uses only GAAP summary metrics (col=1 = sequential prior).
"""

from __future__ import annotations

import pandas as pd

from ...base.metrics_builder import BaseMetricsBuilder
from ...base.parser import BasePressReleaseParser, BaseFinancialTablesParser
from .parser import NvdaPressReleaseParser, NvdaFinancialTablesParser


class NvdaMetricsBuilder(BaseMetricsBuilder):

    def __init__(self) -> None:
        self._pr_parser = NvdaPressReleaseParser()
        self._ft_parser = NvdaFinancialTablesParser()

    @property
    def press_release_parser(self) -> BasePressReleaseParser:
        return self._pr_parser

    @property
    def financial_tables_parser(self) -> BaseFinancialTablesParser:
        return self._ft_parser

    def col1_is_sequential(self, tables: dict) -> bool:
        # NVDA GAAP/Non-GAAP summary tables always show [current, seq_prior, yoy_prior].
        # Column headers are integers (not date strings), so the base-class date check
        # would error. Return True unconditionally — col=1 is always sequential prior.
        return True

    def extract_raw_metrics(
        self,
        tables: dict[str, pd.DataFrame],
        col: int,
        quarter: str,
    ) -> dict[str, str | None]:
        rec: dict[str, str | None] = {"quarter": quarter}
        g = self.get

        gaap     = tables.get("gaap")        # summary: seq prior at col=1
        non_gaap = tables.get("non_gaap")    # summary: seq prior at col=1
        recon    = tables.get("reconciliation")  # seq prior at col=1
        is_      = tables.get("income_statement")   # col=1 = YoY — only use col=0
        bs       = tables.get("balance_sheet")
        cf       = tables.get("cash_flow")
        seg_mkt  = tables.get("segment_market")      # market platforms (CFO commentary)
        seg_rep  = tables.get("segment_reportable")  # reportable segments (CFO commentary)

        # ── GAAP income statement ──────────────────────────────────────────
        # Revenue: gaap summary has seq prior at col=1 (critical for cross-check)
        rec["gaap_revenue"] = g(gaap, "Revenue", col=col)

        # Gross profit: reconciliation has seq prior at col=1
        rec["gaap_gross_profit"] = (
            g(recon, "GAAP gross profit", col=col)
            or (g(is_, "Gross profit", col=0) if col == 0 else None)
        )
        rec["gaap_gross_margin_pct"] = (
            g(gaap, "Gross margin", col=col)
            or g(recon, "GAAP gross margin", col=col)
        )

        # Operating income: gaap summary has seq prior at col=1
        rec["gaap_operating_income"] = (
            g(gaap, "Operating income", col=col)
            or g(recon, "GAAP operating income", col=col)
        )

        # Net income: gaap summary has seq prior at col=1
        rec["gaap_net_income"] = (
            g(gaap, "Net income", col=col)
            or g(recon, "GAAP net income", col=col)
        )

        # Diluted EPS: gaap summary has seq prior at col=1
        rec["gaap_diluted_earnings_per_share"] = g(gaap, "Diluted earnings per share", col=col)

        # Detailed IS items — only use col=0 (IS col=1 is YoY prior, not sequential)
        if col == 0:
            rec["gaap_cost_of_revenue"]              = g(is_, "Cost of revenue", col=0)
            rec["gaap_research_development_expense"] = g(is_, "Research and development", col=0)
            rec["gaap_selling_general_admin_expense"] = (
                g(is_, "Sales, general and administrative", col=0)
            )
            rec["gaap_operating_margin_pct"]         = g(gaap, "Operating income %", col=0)
            rec["gaap_interest_expense"]             = g(is_, "Interest expense", col=0)
            # EPS precise value from IS (summary shows rounded values)
            if not rec["gaap_diluted_earnings_per_share"]:
                rec["gaap_diluted_earnings_per_share"] = g(is_, "Diluted", occurrence=0, col=0)
            # Weighted-average shares: "Basic"/"Diluted" appear twice in IS:
            #   occurrence=0 → EPS per share; occurrence=1 → weighted avg shares
            rec["gaap_basic_shares"]   = g(is_, "Basic",   occurrence=1, col=0)
            rec["gaap_diluted_shares"] = g(is_, "Diluted", occurrence=1, col=0)
        else:
            for k in ["gaap_cost_of_revenue", "gaap_research_development_expense",
                      "gaap_selling_general_admin_expense", "gaap_operating_margin_pct",
                      "gaap_interest_expense", "gaap_basic_shares", "gaap_diluted_shares"]:
                rec[k] = None

        # ── Non-GAAP ──────────────────────────────────────────────────────
        rec["non_gaap_gross_profit"] = (
            g(recon, "Non-GAAP gross profit", col=col)
            or g(non_gaap, "Gross profit", col=col)
        )
        rec["non_gaap_gross_margin_pct"] = (
            g(non_gaap, "Gross margin", col=col)
            or g(recon, "Non-GAAP gross margin", col=col)
        )
        rec["non_gaap_operating_income"] = (
            g(non_gaap, "Operating income", col=col)
            or g(recon, "Non-GAAP operating income", col=col)
        )
        rec["non_gaap_operating_margin_pct"] = g(non_gaap, "Operating income %", col=col)
        rec["non_gaap_net_income"] = (
            g(non_gaap, "Net income", col=col)
            or g(recon, "Non-GAAP net income", col=col)
        )
        rec["non_gaap_diluted_earnings_per_share"] = (
            g(non_gaap, "Diluted earnings per share", col=col)
        )

        # ── Balance sheet (col=0 only) ────────────────────────────────────
        if col == 0:
            # NVDA balance sheet changed format in FY2027:
            # Old: single "Cash, cash equivalents and marketable securities" line
            # New: separate Cash, Marketable debt securities, Marketable equity securities
            _combined_cash = g(bs, "Cash, cash equivalents and marketable securities", col=0)
            rec["gaap_cash"]                      = (
                g(bs, "Cash and cash equivalents", col=0)
                or _combined_cash
            )
            rec["gaap_short_term_investments"]    = (
                g(bs, "Marketable debt securities", col=0)
                or g(bs, "Short-term investments", col=0)
            )
            rec["gaap_accounts_receivable"]       = g(bs, "Accounts receivable, net", col=0)
            rec["gaap_inventories"]               = g(bs, "Inventories", col=0)
            rec["gaap_total_current_assets"]      = g(bs, "Total current assets", col=0)
            rec["gaap_total_assets"]              = g(bs, "Total assets", col=0)
            rec["gaap_total_current_liabilities"] = g(bs, "Total current liabilities", col=0)
            rec["gaap_long_term_debt"]            = (
                g(bs, "Long-term debt", col=0)
                or g(bs, "Long-term notes payable", col=0)
            )
            rec["gaap_stockholders_equity"]       = (
                g(bs, "Total stockholders' equity", col=0)
                or g(bs, "Total equity", col=0)
                or g(bs, "Shareholders' equity", col=0)
                or g(bs, "Total shareholders' equity", col=0)
            )
            rec["cash_and_short_term_investments"] = (
                _combined_cash
                or g(bs, "Cash and cash equivalents", col=0)
            )
        else:
            for k in ["gaap_cash", "gaap_short_term_investments", "gaap_accounts_receivable",
                      "gaap_inventories", "gaap_total_current_assets", "gaap_total_assets",
                      "gaap_total_current_liabilities", "gaap_long_term_debt",
                      "gaap_stockholders_equity", "cash_and_short_term_investments"]:
                rec[k] = None

        # ── Cash flow (col=0 and col=1 from free_cash_flow table) ───────────
        # New format: full CF statement in press_release → `cash_flow` table
        # Old format: small summary with OCF/CapEx/FCF → `free_cash_flow` table
        fcf_tbl = tables.get("free_cash_flow")
        if col == 0:
            rec["gaap_operating_cash_flow"] = (
                g(cf, "Net cash provided by operating activities", col=0)
                or g(cf, "Net cash provided by operating activities of continuing operations", col=0)
                or g(fcf_tbl, "GAAP net cash provided by operating activities", col=0)
            )
            rec["gaap_capital_expenditure"] = (
                g(cf, "Purchases related to property and equipment and intangible assets", col=0)
                or g(cf, "Purchases of property and equipment", col=0)
                or g(fcf_tbl, "Purchase of property and equipment and intangible assets", col=0)
            )
            rec["free_cash_flow"] = (
                g(fcf_tbl, "Free cash flow", col=0)
            )
        else:
            rec["gaap_operating_cash_flow"] = (
                g(fcf_tbl, "GAAP net cash provided by operating activities", col=col)
            )
            rec["gaap_capital_expenditure"] = None
            rec["free_cash_flow"] = (
                g(fcf_tbl, "Free cash flow", col=col)
            )

        # ── Segments (col=0 and col=1 from summary-style tables) ──────────
        # Market platforms — new format (FY2024+): Data Center, Edge Computing
        rec["seg_datacenter_revenue"] = (
            g(seg_mkt, "Data Center", col=col)
            or g(seg_mkt, "Data center", col=col)
        )
        rec["seg_edge_computing_revenue"] = g(seg_mkt, "Edge Computing", col=col)

        # Market platforms — old format (pre-FY2024): Gaming, ProViz, DC, Auto, OEM
        rec["seg_gaming_revenue"] = g(seg_mkt, "Gaming", col=col)
        rec["seg_professional_visualization_revenue"] = (
            g(seg_mkt, "Professional Visualization", col=col)
            or g(seg_mkt, "Pro Visualization", col=col)
        )
        rec["seg_automotive_revenue"]  = g(seg_mkt, "Automotive", col=col)
        rec["seg_oem_other_revenue"]   = (
            g(seg_mkt, "OEM & Other", col=col)
            or g(seg_mkt, "OEM and Other", col=col)
        )

        # Reportable segments — new (FY2024+): Compute & Networking, Graphics
        rec["seg_compute_networking_revenue"] = (
            g(seg_rep, "Compute & Networking", col=col)
            or g(seg_rep, "Compute &amp; Networking", col=col)
        )
        rec["seg_graphics_revenue"] = g(seg_rep, "Graphics", col=col)

        return rec
