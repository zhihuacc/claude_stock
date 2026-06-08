"""Multi-company fundamental analysis pipeline.

Usage:
    python -m data.fundamental.pipeline run --company amd
    python -m data.fundamental.pipeline run --all
    python -m data.fundamental.pipeline download --company nvda --latest
    python -m data.fundamental.pipeline parse --company amd --quarter 2024-Q3
    python -m data.fundamental.pipeline validate --company amd
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path

import pandas as pd

BASE_DIR    = Path(__file__).parent
REPORTS_DIR = BASE_DIR / "reports"
OUTPUT_DIR  = BASE_DIR / "output"

# Company registry: ticker → {downloader, builder} dotted class paths
COMPANY_REGISTRY: dict[str, dict[str, str]] = {
    "amd": {
        "downloader": "data.fundamental.companies.amd.downloader.AmdDownloader",
        "builder":    "data.fundamental.companies.amd.metrics_builder.AmdMetricsBuilder",
    },
    "nvda": {
        "downloader": "data.fundamental.companies.nvda.downloader.NvdaDownloader",
        "builder":    "data.fundamental.companies.nvda.metrics_builder.NvdaMetricsBuilder",
    },
    "msft": {
        "downloader": "data.fundamental.companies.msft.downloader.MsftDownloader",
        "builder":    "data.fundamental.companies.msft.metrics_builder.MsftMetricsBuilder",
    },
    "goog": {
        "downloader": "data.fundamental.companies.goog.downloader.GoogDownloader",
        "builder":    "data.fundamental.companies.goog.metrics_builder.GoogMetricsBuilder",
    },
    "circle": {
        "downloader": "data.fundamental.companies.circle.downloader.CircleDownloader",
        "builder":    "data.fundamental.companies.circle.metrics_builder.CircleMetricsBuilder",
    },
    "mu": {
        "downloader": "data.fundamental.companies.mu.downloader.MuDownloader",
    },
    "cohr": {
        "downloader": "data.fundamental.companies.cohr.downloader.CohrDownloader",
    },
    "lite": {
        "downloader": "data.fundamental.companies.lite.downloader.LiteDownloader",
    },
}


def _import_class(dotted_path: str):
    module_path, cls_name = dotted_path.rsplit(".", 1)
    mod = importlib.import_module(module_path)
    return getattr(mod, cls_name)


class Pipeline:
    """Wires together: download → parse → normalize → calculate_indicators → write CSV."""

    def __init__(self, company: str) -> None:
        if company not in COMPANY_REGISTRY:
            raise ValueError(
                f"Unknown company '{company}'. Known: {list(COMPANY_REGISTRY)}"
            )
        self.company     = company
        reg              = COMPANY_REGISTRY[company]
        self.downloader  = _import_class(reg["downloader"])()
        builder_path     = reg.get("builder")
        self.builder     = _import_class(builder_path)() if builder_path else None
        self.reports_dir = REPORTS_DIR / company
        self.output_path = OUTPUT_DIR / f"{company}_fundamentals.csv"

        from .normalizer.name_normalizer import NameNormalizer
        from .indicators.calculator import FundamentalIndicatorCalculator
        self.normalizer  = NameNormalizer()
        self.calculator  = FundamentalIndicatorCalculator()

    def download(
        self,
        force: bool = False,
        latest: bool = False,
        quarter: str | None = None,
    ) -> None:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.downloader.run(self.reports_dir, force=force, latest=latest, quarter=quarter)

    def build(self, run_check: bool = True):
        from .base.metrics_builder import ValidationReport
        if self.builder is None:
            print(f"  No metrics builder configured for {self.company} — skipping.")
            return pd.DataFrame(), ValidationReport(company=self.company)
        if not self.reports_dir.exists() or not any(self.reports_dir.iterdir()):
            print(f"  No reports found in {self.reports_dir}. Run download first.")
            return pd.DataFrame(), ValidationReport(company=self.company)
        return self.builder.build_dataframe(
            reports_dir=self.reports_dir,
            normalizer=self.normalizer,
            run_check=run_check,
            company=self.company,
        )

    def calculate(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        if raw_df.empty:
            return raw_df
        full_df = self.calculator.calculate(raw_df)
        warnings = self.calculator.validate(full_df)
        for w in warnings:
            print(f"  SANITY WARN: {w}")
        return full_df

    def write(self, df: pd.DataFrame) -> None:
        if df.empty:
            print("  Nothing to write.")
            return
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(self.output_path)
        print(f"  Saved {len(df)} quarters × {len(df.columns)} cols → {self.output_path}")

    def run(
        self,
        download: bool = True,
        force: bool = False,
        latest: bool = False,
        quarter: str | None = None,
        run_check: bool = True,
    ) -> pd.DataFrame:
        print(f"\n{'='*60}")
        print(f"  {self.company.upper()} fundamental pipeline")
        print(f"{'='*60}")
        if download:
            print("→ Download …")
            self.download(force=force, latest=latest, quarter=quarter)
        print("→ Build metrics …")
        raw_df, validation_report = self.build(run_check=run_check)
        print("→ Calculate indicators …")
        full_df = self.calculate(raw_df)
        print("→ Write CSV …")
        self.write(full_df)
        print("\n" + validation_report.summary())

        val_path = OUTPUT_DIR / f"{self.company}_validation.txt"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        val_path.write_text(validation_report.summary())

        return full_df

    def parse_debug(self, quarter: str) -> None:
        """Dump parsed tables for a single quarter to stdout (debugging aid)."""
        q_dir = self.reports_dir / quarter
        pr_pdf = q_dir / "press_release.pdf"
        ft_pdf = q_dir / "financial_tables.pdf"

        if pr_pdf.exists():
            print(f"\n{'='*60}\nPRESS RELEASE TABLES\n{'='*60}")
            tables = self.builder.press_release_parser.parse(pr_pdf)
            for k, df in tables.items():
                print(f"\n--- {k} ---")
                print(df.to_string())

        if ft_pdf.exists():
            print(f"\n{'='*60}\nFINANCIAL TABLES\n{'='*60}")
            tables = self.builder.financial_tables_parser.parse(ft_pdf)
            for k, df in tables.items():
                print(f"\n--- {k} ---")
                print(df.to_string())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fundamental analysis pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # run: full pipeline
    p_run = sub.add_parser("run", help="Full pipeline: download → parse → calculate → CSV")
    grp = p_run.add_mutually_exclusive_group(required=True)
    grp.add_argument("--company", choices=list(COMPANY_REGISTRY))
    grp.add_argument("--all", action="store_true")
    p_run.add_argument("--no-download", action="store_true")
    p_run.add_argument("--force", action="store_true")
    p_run.add_argument("--latest", action="store_true")
    p_run.add_argument("--quarter", metavar="YYYY-QN")
    p_run.add_argument("--no-check", action="store_true")

    # download only
    p_dl = sub.add_parser("download", help="Download PDF reports only")
    p_dl.add_argument("--company", required=True, choices=list(COMPANY_REGISTRY))
    p_dl.add_argument("--force", action="store_true")
    p_dl.add_argument("--latest", action="store_true")
    p_dl.add_argument("--quarter", metavar="YYYY-QN")

    # parse debug
    p_parse = sub.add_parser("parse", help="Dump parsed tables for one quarter (debug)")
    p_parse.add_argument("--company", required=True, choices=list(COMPANY_REGISTRY))
    p_parse.add_argument("--quarter", required=True, metavar="YYYY-QN")

    # validate only (re-run validation on existing CSV)
    p_val = sub.add_parser("validate", help="Re-run validation on existing CSV")
    p_val.add_argument("--company", required=True, choices=list(COMPANY_REGISTRY))

    args = parser.parse_args()

    if args.cmd == "run":
        companies = list(COMPANY_REGISTRY) if args.all else [args.company]
        for co in companies:
            Pipeline(co).run(
                download=not args.no_download,
                force=args.force,
                latest=args.latest,
                quarter=getattr(args, "quarter", None),
                run_check=not args.no_check,
            )

    elif args.cmd == "download":
        Pipeline(args.company).download(
            force=args.force,
            latest=args.latest,
            quarter=getattr(args, "quarter", None),
        )

    elif args.cmd == "parse":
        Pipeline(args.company).parse_debug(args.quarter)

    elif args.cmd == "validate":
        p = Pipeline(args.company)
        _, report = p.build(run_check=True)
        print(report.summary())


if __name__ == "__main__":
    main()
